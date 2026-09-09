import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import getdate
from hospitality_core.hospitality_core.api.reservation import check_availability

class HotelGroupBooking(Document):
    def validate(self):
        self.validate_dates()
        self.validate_status()
        self.validate_deposit()

    def validate_deposit(self):
        """
        TRƯỚC ĐÂY: không có bất kỳ trường nào theo dõi tiền đặt cọc/tạm ứng
        cho đoàn — toàn bộ việc này phải theo dõi thủ công ngoài hệ thống.
        Không tự động đối chiếu deposit_status với các giao dịch thanh toán
        thật trên Master Folio (cần một cơ chế đánh dấu "đây là khoản đặt
        cọc" riêng trên Folio Transaction mà hiện chưa có) — deposit_status
        vẫn là trường cập nhật thủ công, chỉ tự đồng bộ giá trị mặc định hợp
        lý và cảnh báo (không chặn cứng, vì chính sách đặt cọc tùy resort/mùa)
        khi xác nhận đoàn mà đặt cọc yêu cầu vẫn đang chờ.
        """
        from frappe.utils import flt

        if flt(self.deposit_required) <= 0:
            # TRƯỚC ĐÂY: luôn ghi đè thành "Not Required" bất kể trạng thái
            # hiện tại — nếu đoàn ĐÃ nhận cọc (Received) hoặc đã miễn cọc có
            # ghi chú (Waived), rồi sau đó ai đó sửa deposit_required xuống 0
            # (VD sửa lại số khách/giá), trạng thái thật (đã thu tiền/đã miễn
            # có lý do) bị XÓA MẤT khỏi hệ thống mà kế toán không hề hay biết.
            # Chỉ tự động chuyển về "Not Required" khi trạng thái CHƯA từng
            # được xác nhận thật (Received/Waived).
            if self.deposit_status not in ("Received", "Waived"):
                self.deposit_status = "Not Required"
        elif self.deposit_status == "Not Required":
            self.deposit_status = "Pending"

        if self.status == "Confirmed" and flt(self.deposit_required) > 0 and self.deposit_status == "Pending":
            frappe.msgprint(_(
                "Đoàn {0} yêu cầu đặt cọc {1} nhưng Deposit Status vẫn đang 'Pending'. Nếu đã thực nhận cọc, dùng "
                "hành động 'Ghi Nhận Đặt Cọc' (api/group_booking.py's record_group_deposit()) để tạo Payment Entry "
                "thật trên Master Folio — KHÔNG chỉ đổi Deposit Status thủ công, vì việc đó không trừ tiền vào số "
                "dư folio, khiến City Ledger/AR Aging báo thừa công nợ. Nếu miễn cọc, chuyển Deposit Status thành "
                "'Waived' và ghi rõ lý do vào Deposit Notes."
            ).format(self.group_name or self.name, frappe.format(self.deposit_required, {"fieldtype": "Currency"})),
                indicator="orange", alert=True)


    def on_update(self):
        """
        Trigger creation logic when status changes to confirmed or explicit action?
        Let's trigger on save IF status is Confirmed/In House and no master folio exists.
        """
        if self.status in ["Confirmed", "In House"]:
            if not self.master_folio:
                self.create_group_structure()

    def validate_dates(self):
        if self.arrival_date and self.departure_date:
            if getdate(self.arrival_date) >= getdate(self.departure_date):
                frappe.throw(_("Departure Date must be after Arrival Date."))

    def validate_status(self):
        # Prevent checking in a group without a financial master folio
        if self.status in ["In House", "Checked Out"] and not self.master_folio:
            pass # We create it automatically now, so relax this check or ensure creation happens first.

        # If Status is Confirmed, Master Payer is mandatory
        if self.status == "Confirmed" and not self.master_payer:
            frappe.throw(_("Please select a Master Payer (Customer) to confirm this group booking."))

    def create_group_structure(self):
        # 1. Create Master Payer Reservation
        master_res = self.create_master_payer_reservation()
        
        # 2. Set Master Folio on Group
        self.db_set("master_folio", master_res.folio)
        
        # 3. Create Child Reservations
        self.create_bulk_reservations()

    def create_master_payer_reservation(self):
        # Create a "Virtual" reservation for the Master Payer
        # This acts as the anchor for the Master Folio.
        
        # We need a guest profile for the master payer
        guest_name = self.get_corporate_guest_name(self.master_payer)
        
        # Assuming we need a 'dummy' room or make room optional in Reservation. 
        # For now, let's look for a "Virtual" room type or similar, or just pick the first available if not strict.
        # BETTER: Create a reservation without a room if possible? 
        # The Reservation triggers 'check_availability' which requires a room.
        # Let's SKIP availability check for Master Payer by adding a flag?
        # Or better: Just create the Folio directly?
        # The requirement says: "making a reservation for a room that will act as the master payer"
        
        res = frappe.new_doc("Hotel Reservation")
        res.guest = guest_name
        res.company = self.master_payer
        res.is_group_guest = 1 
        res.group_booking = self.name
        res.arrival_date = self.arrival_date
        res.departure_date = self.departure_date
        res.status = "Reserved"
        if self.get("property"):
            res.property = self.property
            res.operating_company = self.get("operating_company")
            res.currency = self.get("currency")
        
        # TRƯỚC ĐÂY: lọc Hotel Room bằng filters={"room_type": "Virtual"} —
        # SAI HẲN, xác nhận thật khi viết test sống: "Hotel Room Type" dùng
        # autoname="hash" (đọc thẳng hotel_room_type.json), nên TÊN THẬT
        # (docname, giá trị thật sự lưu trong Hotel Room.room_type — 1 Link
        # field) của bản ghi có nhãn "Virtual" luôn là 1 chuỗi hash ngẫu
        # nhiên (VD "a1b2c3d4e5"), KHÔNG BAO GIỜ là chuỗi "Virtual". Hậu quả:
        # dù admin làm ĐÚNG THEO CHỈ DẪN của chính thông báo lỗi bên dưới
        # (tạo Hotel Room Type với room_type_name="Virtual" + 1 Hotel Room
        # thuộc loại đó), virtual_rooms LUÔN rỗng — TOÀN BỘ tính năng xác
        # nhận đặt đoàn (create_group_structure()) không bao giờ hoạt động
        # được trên bất kỳ site nào. Sửa: tra đúng docname thật của Hotel
        # Room Type có nhãn "Virtual" trước, rồi mới lọc Hotel Room theo
        # đúng docname đó.
        virtual_type_filters = {"room_type_name": "Virtual"}
        if self.get("property"):
            virtual_type_filters["property"] = self.property
        virtual_type_names = frappe.get_all("Hotel Room Type", filters=virtual_type_filters, pluck="name")
        virtual_filters = {"room_type": ["in", virtual_type_names or [""]]}
        if self.get("property"):
            virtual_filters["property"] = self.property
        virtual_rooms = frappe.get_all("Hotel Room", filters=virtual_filters, pluck="name")

        # TRƯỚC ĐÂY: nếu chưa cấu hình Hotel Room Type "Virtual", code sẽ tự
        # động CHIẾM một phòng THẬT (self.rooms[0]) để neo Master Folio, chỉ
        # cảnh báo bằng msgprint (không chặn) — nghĩa là phòng đó bị rút khỏi
        # danh sách phòng bán được cho khách thật, một lỗi doanh thu/khả dụng
        # phòng nghiêm trọng mà không ai buộc phải để ý tới cảnh báo đó. Nay
        # bắt buộc phải cấu hình phòng ảo trước — KHÔNG còn tự động mượn phòng
        # thật nữa, dù chỉ 1 lần.
        if not virtual_rooms:
            frappe.throw(_(
                "Chưa cấu hình Loại Phòng 'Virtual' (phòng ảo, không bán được) để neo Master Folio cho đặt đoàn. "
                "Vui lòng tạo một Hotel Room Type tên chính xác 'Virtual' và ít nhất 1 Hotel Room thuộc loại đó "
                "trước khi xác nhận đặt đoàn này — hệ thống không còn tự động mượn phòng thật của khách để neo "
                "Master Payer nữa (từng gây mất 1 phòng bán được thật mỗi lần thiếu cấu hình)."
            ))

        # Dò qua TOÀN BỘ phòng ảo đã cấu hình, chọn phòng đầu tiên còn TRỐNG
        # cho đúng khoảng ngày của đoàn này — TRƯỚC ĐÂY chỉ lấy phòng ảo ĐẦU
        # TIÊN tìm thấy bất kể còn trống hay không (`frappe.db.get_value(...)`
        # không lọc theo ngày): nếu resort chỉ cấu hình 1 phòng ảo, 2 đoàn có
        # khoảng ngày trùng nhau (rất phổ biến ở resort có nhiều đoàn cùng
        # lúc) sẽ khiến đoàn thứ 2 bị `check_availability()` báo xung đột
        # lịch ngay trên chính phòng ảo dùng chung đó — không xác nhận được.
        virtual_room = None
        for candidate in virtual_rooms:
            try:
                check_availability(room=candidate, arrival_date=self.arrival_date, departure_date=self.departure_date)
                virtual_room = candidate
                break
            except Exception:
                continue

        if not virtual_room:
            frappe.throw(_(
                "Cả {0} phòng ảo (Virtual) đã cấu hình đều đang được dùng cho đoàn khác trong cùng khoảng ngày "
                "này. Vui lòng tạo thêm ít nhất 1 Hotel Room thuộc loại 'Virtual' để có thể xác nhận đồng thời "
                "nhiều đoàn."
            ).format(len(virtual_rooms)))

        # Anchor the Master Folio on the non-sellable virtual room instead of
        # taking a real room away from a paying guest.
        res.room = virtual_room
        res.room_type = frappe.db.get_value("Hotel Room", virtual_room, "room_type")
        # hotel_reception là Link bắt buộc (reqd=1) trên Hotel Reservation,
        # không có fetch_from/default nào cả — mọi đường tạo Hotel Reservation
        # tự động (VD channel_manager.py's OTA webhook dùng
        # settings.default_hotel_reception) đều phải tự cấp giá trị này.
        # TRƯỚC ĐÂY hàm này bỏ sót hoàn toàn — res.insert() sẽ luôn crash
        # frappe.MandatoryError ngay khi validate() (bước kiểm tra field ảnh
        # hưởng bởi bug "Virtual" room-type ở trên) qua được, khiến TOÀN BỘ
        # tính năng xác nhận đặt đoàn vẫn không dùng được dù đã cấu hình đúng
        # phòng ảo — chỉ lộ ra khi chạy test sống, không static review nào
        # bắt được vì lỗi này bị lỗi khác che khuất suốt các vòng review trước.
        res.hotel_reception = frappe.db.get_value("Hotel Room", virtual_room, "hotel_reception")
        res.rate_plan = None  # Phòng ảo chỉ neo folio, không áp bảng giá phòng thật.
        res.discount_type = self.discount_type
        res.discount_value = self.discount_value

        res.insert(ignore_permissions=True)

        # create_folio() (api/reservation.py) luôn tạo Guest Folio mới với
        # status="Provisional" — mặc định ĐÚNG cho 1 đặt phòng khách thường
        # (chỉ thành "Open" lúc check-in thật, xem process_check_in() dòng
        # ~220). Nhưng Master Folio của đoàn đóng vai trò THUẦN TÚY là mỏ neo
        # thanh toán/công nợ (giống hệt Master Folio của Company — xem
        # ensure_company_folio() ở trên, luôn ép "Open" ngay lúc tạo với đúng
        # lý do "Company Folios are indefinite... not tied to physical stay"),
        # không phải 1 kỳ lưu trú thật gắn với ngày đến. Nếu để nguyên
        # "Provisional", record_group_deposit() (api/group_booking.py) —
        # được xây riêng để cho phép thu cọc THẬT ngay lúc XÁC NHẬN đoàn,
        # trước ngày đến rất lâu — sẽ luôn bị create_company_folio_payment()
        # chặn "Cannot record a payment on a folio with status: Provisional"
        # cho tới tận lúc mass_check_in() thật sự chạy vào đúng ngày đến —
        # nghĩa là tính năng thu cọc trước hoàn toàn không dùng được, chỉ lộ
        # ra qua chạy test sống (mọi review tĩnh trước đó không phát hiện vì
        # không mô phỏng được đúng thứ tự "confirm rồi thử ghi cọc trước khi
        # check-in"). Set thẳng "Open" ngay đây — an toàn, vì check-in thật
        # sau này (process_check_in()) chỉ set lại "Open" một lần nữa (vô hại,
        # đã idempotent).
        #
        # Lỗi thứ 2, phát hiện ngay sau lỗi status: dù `res.company =
        # self.master_payer` được gán ở trên, HotelReservation.validate()
        # (dòng đầu tiên: "if not self.is_company_guest: self.company =
        # None") XÓA TRẮNG field này ngay lúc insert() vì is_company_guest
        # không được set — CHỦ Ý (không set is_company_guest=1 ở đây, vì làm
        # vậy sẽ kích hoạt luôn `self.ensure_company_folio()` ở validate(),
        # tạo THÊM 1 Master Folio "Company" riêng biệt cho cùng khách hàng,
        # trùng lặp với đúng Guest Folio vừa tạo qua create_folio()). Hệ quả:
        # create_folio()'s `folio.company = reservation_doc.company` luôn ghi
        # rỗng — create_company_folio_payment() (record_group_deposit() gọi
        # tới) từ chối thẳng "This Company Folio has no company linked.",
        # nghĩa là thu cọc đoàn không bao giờ hoạt động được dù đã qua fix
        # status ở trên. Gán lại thẳng vào Guest Folio (không đụng tới Hotel
        # Reservation.company, giữ đúng is_company_guest=0 hiện tại để không
        # vô tình bật lại ensure_company_folio()).
        frappe.db.set_value("Guest Folio", res.folio, {
            "status": "Open",
            "company": self.master_payer,
        })
        return res

    def create_bulk_reservations(self):
        # create_master_payer_reservation() giờ luôn neo vào phòng ảo (bắt
        # buộc phải cấu hình "Virtual" room type, xem hàm đó) nên KHÔNG BAO
        # GIỜ còn mượn phòng thật ở hàng đầu tiên của self.rooms nữa — mọi
        # phòng trong danh sách đều cần một Hotel Reservation riêng.
        if not self.rooms:
            return

        for row in self.rooms:
            # Mặc định lấy tên khách trưởng đoàn (Master Payer) cho mỗi phòng
            # — trong đặt đoàn thực tế thường chưa biết tên từng khách lúc lập
            # bulk reservation, lễ tân sẽ cập nhật lại tên khách thật khi nhận
            # phòng. Không log_error mỗi dòng (trước đây gọi cho CẢ trường
            # hợp thành công, làm rác Error Log không cần thiết).
            from hospitality_core.hospitality_core.doctype.hotel_room.hotel_room import resolve_hotel_room
            res = frappe.new_doc("Hotel Reservation")
            res.guest = self.get_corporate_guest_name(self.master_payer)
            res.room = resolve_hotel_room(row.room, property=self.get("property"))
            res.room_type = row.room_type or frappe.db.get_value("Hotel Room", res.room, "room_type")
            # Cùng lỗi/lý do như create_master_payer_reservation(): hotel_reception
            # là Link bắt buộc, không có default/fetch nào — phải tự lấy từ
            # đúng phòng thật đang đặt cho dòng này.
            res.hotel_reception = frappe.db.get_value("Hotel Room", res.room, "hotel_reception")
            res.rate_plan = row.rate_plan
            res.arrival_date = self.arrival_date
            res.departure_date = self.departure_date
            res.is_group_guest = 1
            res.group_booking = self.name
            res.status = "Reserved"
            if self.get("property"):
                res.property = self.property
                res.operating_company = self.get("operating_company")
                res.currency = self.get("currency")

            # Discount Fallback logic
            res.discount_type = row.discount_type or self.discount_type
            res.discount_value = row.discount_value if row.discount_type else self.discount_value

            # TRƯỚC ĐÂY: res.insert() không được bọc try/except — nếu 1 phòng
            # bất kỳ lỗi (VD rate_plan của dòng đó không khớp room_type thật,
            # sau khi sync_room_type_with_room() tự sửa lại room_type theo
            # phòng thật), toàn bộ vòng lặp dừng ngay, Frappe rollback lại
            # TOÀN BỘ request (an toàn, không tạo dữ liệu dở dang) nhưng người
            # xác nhận đoàn chỉ thấy 1 lỗi CHUNG CHUNG (VD "Bảng giá X không
            # thuộc loại phòng Y"), không biết dòng/phòng nào trong bảng gây
            # lỗi — phải dò từng dòng thủ công. Vẫn giữ nguyên hành vi "1 lỗi
            # thì hủy toàn bộ" (đúng, vì đoàn phải tạo trọn vẹn hoặc không tạo
            # gì), chỉ bổ sung ngữ cảnh phòng/dòng vào thông báo lỗi.
            try:
                res.insert(ignore_permissions=True)
            except Exception as e:
                frappe.throw(_(
                    "Không thể tạo đặt phòng cho Phòng {0} (dòng {1} trong bảng danh sách phòng): {2}"
                ).format(row.room, row.idx, str(e)))
            
    def get_corporate_guest_name(self, customer):
        g_name = frappe.db.get_value("Guest", {"customer": customer}, "name")
        if not g_name:
            cust = frappe.get_doc("Customer", customer)
            g = frappe.new_doc("Guest")
            g.full_name = cust.customer_name + " (Group Rep)"
            g.customer = customer
            g.guest_type = "Corporate"
            g.insert(ignore_permissions=True)
            g_name = g.name
        return g_name