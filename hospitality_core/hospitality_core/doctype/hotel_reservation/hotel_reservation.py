import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import getdate, nowdate, add_days, flt, now_datetime
from hospitality_core.hospitality_core.api.reservation import check_availability, create_folio

class HotelReservation(Document):
    def validate(self):
        if not self.is_company_guest:
            self.company = None

        if self.room:
            from hospitality_core.hospitality_core.doctype.hotel_room.hotel_room import resolve_hotel_room
            self.room = resolve_hotel_room(self.room, property=self.get('property')) or self.room

        self.validate_dates()
        self.validate_occupancy_counts()
        self.validate_blacklist()

        self.sync_room_type_with_room()
        from hospitality_core.hospitality_core.api.rate_plan import prepare_reservation, guard_legacy_repricing
        prepare_reservation(self)
        if not self.is_new() and self.has_value_changed('departure_date'):
            guard_legacy_repricing(self)

        # Only validate availability if status is Reserved or Checked In
        if self.status in ["Reserved", "Checked In"]:
            self.validate_room_availability()
        
        # Requirement: "billing to Company should be set... Folio is opened to the Company"
        # New Requirement: If Is Company Guest is checked, Company is mandatory
        if self.is_company_guest and not self.company:
            frappe.throw(_("Company is mandatory when 'Is Company Guest' is checked."))

        if self.company:
            self.ensure_company_folio()

    def validate_dates(self):
        if getdate(self.arrival_date) >= getdate(self.departure_date):
            frappe.throw(_("Departure Date must be after Arrival Date."))

    def validate_occupancy_counts(self):
        children = int(self.children_count or 0)
        extra_beds = int(self.extra_bed_count or 0)

        if children < 0:
            frappe.throw(_("Số lượng trẻ em không thể là số âm."))
        if children > 15:
            frappe.throw(_("Số lượng trẻ em trong 1 phòng không được vượt quá 15 bé."))

        if extra_beds < 0:
            frappe.throw(_("Số lượng giường phụ (Extra Bed) không thể là số âm."))
        if extra_beds > 4:
            frappe.throw(_("Số lượng giường phụ trong 1 phòng tối đa là 4 giường."))

    def validate_blacklist(self):
        """
        TRƯỚC ĐÂY: Guest.guest_type = "Blacklisted" hoàn toàn chỉ mang tính
        trang trí — không có bất kỳ nơi nào trong luồng đặt phòng/check-in
        kiểm tra và chặn/cảnh báo, khiến nhân viên có thể tin tưởng nhầm rằng
        hệ thống đã tự động chặn khách trong danh sách đen. Nay bắt buộc: chỉ
        Frontdesk Supervisor/Hospitality Manager/System Manager mới lưu được
        đặt phòng cho khách Blacklisted, và phải ghi rõ lý do phê duyệt (tối
        thiểu 10 ký tự) — kiểm tra ở server, không chỉ dựa vào giao diện.

        Chỉ kiểm tra khi tạo mới HOẶC khi trường `guest` vừa bị đổi — quyết
        định phê duyệt được ghi nhận 1 LẦN lúc tạo/gán khách, không bắt lặp
        lại ở mọi lần lưu sau đó (VD: check-in, đổi ngày) — nếu không, một
        lễ tân thường (không phải supervisor) sẽ không thể check-in một đặt
        phòng ĐÃ được supervisor phê duyệt từ trước, chỉ vì validate() chạy
        lại trên mọi save.
        """
        if not self.guest:
            return
        if not (self.is_new() or self.has_value_changed("guest")):
            return

        # TRƯỚC ĐÂY: chỉ check guest_type của CHÍNH self.guest — nếu khách
        # này đã được guest_crm.py's merge_guest() gộp VÀO 1 khách khác đang
        # Blacklisted (merge_guest() KHÔNG đổi guest_type của bên nào, chỉ
        # thêm quan hệ merged_into, đúng triết lý "giữ nguyên nguồn chứng từ"
        # của module), thì self.guest (đã bị gộp) vẫn đọc guest_type "Regular"
        # của chính nó — bỏ lọt hoàn toàn việc khách này (cùng 1 người thật)
        # đã được xác định là Blacklisted dưới định danh khác. Dùng canonical()
        # để resolve đúng danh tính cuối cùng trước khi kiểm tra.
        from hospitality_core.hospitality_core.api.guest_crm import canonical
        guest_type = frappe.db.get_value("Guest", canonical(self.guest), "guest_type")
        if guest_type != "Blacklisted":
            return

        reason = (self.get("blacklist_override_reason") or "").strip()
        if len(reason) < 10:
            frappe.throw(_(
                "Khách {0} đang trong DANH SÁCH ĐEN (Blacklisted). Không thể lưu đặt phòng cho khách này nếu chưa "
                "ghi rõ lý do phê duyệt (tối thiểu 10 ký tự) vào trường 'Lý Do Duyệt Khách Trong Danh Sách Đen'."
            ).format(self.guest))

        allowed_roles = ["Frontdesk Supervisor", "Hospitality Manager", "System Manager"]
        user_roles = frappe.get_roles(frappe.session.user)
        if not any(r in user_roles for r in allowed_roles):
            frappe.throw(_(
                "Khách {0} đang trong DANH SÁCH ĐEN (Blacklisted). Chỉ Quản lý Lễ tân (Frontdesk Supervisor), Quản "
                "lý Khách sạn, hoặc Quản trị hệ thống mới có quyền phê duyệt đặt phòng cho khách này. Vui lòng nhờ "
                "quản lý trực tiếp xử lý."
            ).format(self.guest))

    def sync_room_type_with_room(self):
        if not self.room:
            return

        room_type = frappe.db.get_value("Hotel Room", self.room, "room_type")
        if room_type and self.room_type != room_type:
            self.room_type = room_type

    def validate_room_availability(self):
        check_availability(
            room=self.room, 
            arrival_date=self.arrival_date, 
            departure_date=self.departure_date, 
            ignore_reservation=self.name
        )

    def before_insert(self):
        self.reserved_by = frappe.session.user

    def after_insert(self):
        # Requirement: "And a Folio is also opened for the guest"
        create_folio(self)

    def ensure_company_folio(self):
        """
        Ensures an OPEN Master Folio exists for the Company.
        Company Folios are indefinite and manually closed.
        """
        if not self.company:
            return

        # Khóa mutex đặt tên theo company — TRƯỚC ĐÂY check-then-insert này
        # không khóa gì cả: 2 đặt phòng cho CÙNG 1 công ty MỚI (chưa từng có
        # Master Folio) được tạo gần như đồng thời đều có thể cùng thấy
        # "chưa tồn tại" trước khi bên kia kịp insert, rồi cả 2 cùng tạo ra 2
        # Master Folio (và có thể 2 Guest đại diện công ty khác nhau, xem
        # get_corporate_guest_name()) cho cùng 1 công ty — tách đôi công nợ
        # công ty ra 2 folio riêng biệt, sai lệch số liệu City Ledger.
        lock_key = f"company_folio:{self.company}"
        got_lock = frappe.db.sql("SELECT GET_LOCK(%s, 10)", lock_key)[0][0]
        if not got_lock:
            frappe.throw(_("Hệ thống đang xử lý một đặt phòng khác của cùng công ty này; vui lòng thử lại sau."))
        try:
            # Check for existing Open Master Folio for this Company
            master_filters = {
                "company": self.company,
                "status": "Open",
                "is_company_master": 1
            }
            if self.get('property'):
                master_filters.update(property=self.property, operating_company=self.operating_company, currency=self.currency)
            exists = frappe.db.exists("Guest Folio", master_filters)

            if not exists:
                # Create Master Company Folio
                guest_name = self.get_corporate_guest_name()

                folio = frappe.new_doc("Guest Folio")
                folio.is_company_master = 1 # Flag as Company Folio
                folio.guest = guest_name
                folio.company = self.company
                folio.status = "Open"
                folio.open_date = nowdate()
                for field in ('property', 'operating_company', 'currency', 'billing_customer'):
                    folio.set(field, self.get(field))
                # No specific reservation/room link for Master Folio
                folio.insert(ignore_permissions=True)
                frappe.msgprint(_("Created new Master Folio for Company: {0}").format(self.company))
        finally:
            frappe.db.sql("SELECT RELEASE_LOCK(%s)", lock_key)

    def get_corporate_guest_name(self):
        """
        Gets or creates a Representative Guest record for the Company to attach the Master Folio to.
        """
        g_name = frappe.db.get_value("Guest", {"customer": self.company}, "name")
        if not g_name:
            # Create a placeholder guest for the company
            cust = frappe.get_doc("Customer", self.company)
            g = frappe.new_doc("Guest")
            g.full_name = cust.customer_name + " (Master Rep)"
            g.customer = self.company
            g.guest_type = "Corporate"
            g.insert(ignore_permissions=True)
            g_name = g.name
        return g_name

    def process_check_in(self):
        """
        Transition: Reserved -> Checked In
        Room: Available -> Occupied
        Folio: Provisional -> Open
        Action: CHARGE FIRST NIGHT IMMEDIATELY
        """
        if self.status != "Reserved":
            frappe.throw(_("Only Reserved bookings can be Checked In."))
        
        if getdate(self.arrival_date) > getdate(nowdate()):
            frappe.throw(_("Cannot Check-In before Arrival Date."))

        # 1. Update Reservation and Folio in a single process
        # We use db_set to avoid triggering the full 'save' cycle which might be overkill here
        # but since we have other fields to update (in check-in it's just status), it's fine.
        self.status = "Checked In"
        
        # 2. Update Room Status
        prev_room_status = frappe.db.get_value("Hotel Room", self.room, "status")
        frappe.db.set_value("Hotel Room", self.room, "status", "Occupied")
        from hospitality_core.hospitality_core.api.housekeeping_mobile import log_room_status_change
        log_room_status_change(self.room, prev_room_status, "Occupied")
        
        # 3. Update Folio Status
        if self.folio:
            frappe.db.set_value("Guest Folio", self.folio, "status", "Open")

            from hospitality_core.hospitality_core.api.rate_plan import post_daily_charge, charge_date_for_checkin
            post_daily_charge(self, charge_date_for_checkin(now_datetime()))

        self.save()
        return "Checked In"

    def process_check_out(self):
        """
        Transition: Checked In -> Checked Out
        Room: Occupied -> Available
        Folio: Validate Balance -> Closed -> SUBMITTED (Immutable)
        Reservation: SUBMITTED (Immutable)
        """
        if self.status != "Checked In":
            frappe.throw(_("Guest is not currently Checked In."))

        if getdate(self.departure_date) != getdate(nowdate()):
            frappe.throw(_("Cannot Check Out. Departure date ({0}) must be today ({1}).").format(self.departure_date, nowdate()))

        # Requirement: "When a reservation is part of a group booking, that reservation cannot be checked out until the master folio is cleared."
        if self.is_group_guest and self.group_booking:
            master_folio = frappe.db.get_value("Hotel Group Booking", self.group_booking, "master_folio")
            if master_folio:
                # Sync balance to get latest totals
                master_folio_doc = frappe.get_doc("Guest Folio", master_folio)
                from hospitality_core.hospitality_core.api.folio import sync_folio_balance
                sync_folio_balance(master_folio_doc)
                
                # Re-fetch balance
                master_balance = frappe.db.get_value("Guest Folio", master_folio, "outstanding_balance") or 0.0
                if master_balance > 0.01:
                    frappe.throw(_("Cannot Check Out. The Group Master Folio ({0}) has an outstanding balance of {1}. All group charges must be settled first.").format(master_folio, master_balance))

        # 1. Handle Folio
        if self.folio:
            # Check status first - if Closed, we skip all operations to avoid "Cannot add transactions" error
            folio_status = frappe.db.get_value("Guest Folio", self.folio, "status")
            
            if folio_status == "Closed":
                frappe.msgprint(_("Guest Folio {0} is already Closed. Skipping financial updates.").format(self.folio))
            else:
                folio_doc = frappe.get_doc("Guest Folio", self.folio)
                
                # --- START: AUTOMATIC TRANSFER TO CITY LEDGER ---
                if self.company:
                    # Calculate total amount tagged as 'Bill To Company' on this folio
                    company_liability = frappe.db.sql("""
                        SELECT SUM(amount) FROM `tabFolio Transaction`
                        WHERE parent = %s 
                        AND bill_to = 'Company' 
                        AND is_void = 0
                    """, (self.folio,), as_dict=False)[0][0] or 0.0

                    if company_liability > 0:
                        # Check if we already posted a transfer to avoid double credit if button clicked twice
                        transfer_item = "TRANSFER"
                        from hospitality_core.hospitality_core.api.night_audit import ensure_item_exists
                        ensure_item_exists(transfer_item, "Transfer to City Ledger")
                        
                        transfer_exists = frappe.db.exists("Folio Transaction", {
                            "parent": self.folio,
                            "item": transfer_item,
                            "posting_date": nowdate(),
                            "amount": -1 * flt(company_liability)
                        })

                        if not transfer_exists:
                            # Create the Credit Transaction on Guest Folio
                            # This zeros out the Company portion on the Guest's view
                            # flags.hospitality_service=True — TRƯỚC ĐÂY thiếu, nên
                            # property_scope.py's validate_document() (bắt buộc 1
                            # trong 3 flag nguồn gốc cho MỌI Folio Transaction của
                            # folio Property v2) sẽ THROW ngay khi property cutover
                            # sang Property v2 — chặn đứng checkout của MỌI khách
                            # công ty có công nợ. Đây là giao dịch HỆ THỐNG tự sinh
                            # (không phải charge từ rate plan/mirror), nên
                            # hospitality_service là flag đúng ngữ nghĩa nhất.
                            txn = frappe.get_doc({
                                "doctype": "Folio Transaction",
                                "parent": self.folio,
                                "parenttype": "Guest Folio",
                                "parentfield": "transactions",
                                "posting_date": nowdate(),
                                "item": transfer_item,
                                "description": f"Transfer to Master Folio (City Ledger) - {self.company}",
                                "qty": 1,
                                "amount": -1 * flt(company_liability), # Credit
                                "bill_to": "Company",
                                "is_void": 0
                            })
                            txn.flags.hospitality_service = True
                            txn.insert(ignore_permissions=True)
                            
                            frappe.msgprint(_("Transferred {0} to City Ledger.").format(company_liability))
                # --- END: AUTOMATIC TRANSFER ---

                # --- START: AUTOMATIC TRANSFER TO GROUP MASTER ---
                if self.is_group_guest and self.group_booking:
                    # 1. Get Group Master Folio ID
                    group_master_folio = frappe.db.get_value("Hotel Group Booking", self.group_booking, "master_folio")
                    
                    if group_master_folio and group_master_folio != self.folio:
                        # 2. Calculate total liability on Guest Folio (excluding existing transfers)
                        # Re-sync balance first
                        from hospitality_core.hospitality_core.api.folio import sync_folio_balance
                        sync_folio_balance(folio_doc)
                        current_balance = frappe.db.get_value("Guest Folio", self.folio, "outstanding_balance") or 0.0

                        if current_balance > 0.01:
                            transfer_item = "TRANSFER-GROUP"
                            from hospitality_core.hospitality_core.api.night_audit import ensure_item_exists
                            ensure_item_exists(transfer_item, "Transfer to Group Master")

                            # Check if we already posted a transfer to avoid double
                            # credit if button clicked twice — TRƯỚC ĐÂY khối này là
                            # khối DUY NHẤT trong 3 khối transfer của hàm không có
                            # guard này (khối City Ledger phía trên và khối
                            # REFUND-TRANSFER ở process_cancel() đều đã có), dù
                            # cùng logic ghi giao dịch credit dựa trên check-then-act.
                            transfer_exists = frappe.db.exists("Folio Transaction", {
                                "parent": self.folio,
                                "item": transfer_item,
                                "posting_date": nowdate(),
                                "amount": -1 * flt(current_balance)
                            })

                            if not transfer_exists:
                                # 3. Credit Guest Folio to zero it out for checkout
                                # This transaction will NOT be mirrored to the Master Folio
                                # (handled by skip logic in folio.py)
                                # flags.hospitality_service=True — cùng lý do như khối
                                # City Ledger phía trên: thiếu flag này sẽ khiến
                                # property_scope.py's validate_document() throw ngay
                                # khi property cutover Property v2, chặn đứng checkout
                                # của MỌI khách đoàn còn công nợ cá nhân.
                                txn = frappe.get_doc({
                                    "doctype": "Folio Transaction",
                                    "parent": self.folio,
                                    "parenttype": "Guest Folio",
                                    "parentfield": "transactions",
                                    "posting_date": nowdate(),
                                    "item": transfer_item,
                                    "description": f"Internal Balance Settlement (Group Bill) - {self.group_booking}",
                                    "qty": 1,
                                    "amount": -1 * flt(current_balance), # Credit
                                    "bill_to": "Group",
                                    "is_void": 0
                                })
                                txn.flags.hospitality_service = True
                                txn.insert(ignore_permissions=True)

                                frappe.msgprint(_("Individual balance of {0} settled via Group Master.").format(current_balance))
                # --- END: AUTOMATIC TRANSFER TO GROUP MASTER ---
                
                # Recalculate balance - NOTE: transfer transaction inserts above already triggered sync via hooks!
                from hospitality_core.hospitality_core.api.folio import sync_folio_balance
                sync_folio_balance(folio_doc)
                
                # Get latest balance from DB (sync_folio_balance updates DB directly)
                balance = frappe.db.get_value("Guest Folio", self.folio, "outstanding_balance") or 0.0
                
                # Requirement: "folio once opened cannot be closed until all payments are made... enforced... for private guests"
                # Updated Requirement: Company Guests can check out with balance.
                
                if not self.is_company_guest:
                    if balance > 0.01:
                        frappe.throw(_("Cannot Check Out. Outstanding balance of {0} remains on Folio {1}. Please settle payment.").format(balance, self.folio))
                else:
                    if balance > 0.01:
                        frappe.msgprint(_("Company Guest Checkout: Outstanding balance of {0}. Liability remains on Company Master Folio.").format(balance))
                
                # Close Folio using db_set to avoid timestamp conflicts
                # (Transaction inserts trigger sync_folio_balance hooks which update DB timestamps)
                frappe.db.set_value("Guest Folio", self.folio, {
                    "status": "Closed",
                    "close_date": nowdate()
                })
                
                # Record guest balance if there's a credit balance
                # (after_save hook handles this, but we call it explicitly to ensure it runs)
                from hospitality_core.hospitality_core.api.folio import record_guest_balance
                record_guest_balance(folio_doc)

        # 2. Update Reservation Status
        # Use db_set to avoid "Document has been modified" errors caused by background updates 
        # (e.g. from Folio/Room logic) triggering optimistic locking failures during full save.
        self.db_set("status", "Checked Out")
        
        # 3. Update Room Status to Dirty (needs housekeeping turnover cleaning)
        prev_room_status = frappe.db.get_value("Hotel Room", self.room, "status")
        frappe.db.set_value("Hotel Room", self.room, "status", "Dirty")
        from hospitality_core.hospitality_core.api.housekeeping_mobile import log_room_status_change
        log_room_status_change(self.room, prev_room_status, "Dirty")

        # 4. No self.save() needed - db_set handles the status update safely.

        return "Checked Out"
    
    def process_cancel(self):
        """
        Transition: Reserved -> Cancelled
        """
        if self.status not in ["Reserved", "Checked In"]:
            frappe.throw(_("Only Reserved or Checked In bookings can be Cancelled."))
        
        self.db_set("status", "Cancelled")
        
        # If there's a folio, cancel it as well if it's not already closed
        if self.folio:
            folio_status = frappe.db.get_value("Guest Folio", self.folio, "status")
            if folio_status not in ["Closed", "Cancelled"]:
                folio_doc = frappe.get_doc("Guest Folio", self.folio)
                from hospitality_core.hospitality_core.api.folio import sync_folio_balance
                sync_folio_balance(folio_doc)
                
                if folio_doc.outstanding_balance < -0.01: # Guest has excess payment (credit)
                    # Reuse record_guest_balance()'s existing dedup guard instead of
                    # inserting inline, so a retried/double-fired cancel can't credit
                    # the guest twice for the same folio.
                    amount_to_transfer = abs(folio_doc.outstanding_balance)
                    already_recorded = frappe.db.exists("Guest Balance Ledger", {"folio": self.folio})

                    from hospitality_core.hospitality_core.api.folio import record_guest_balance
                    record_guest_balance(folio_doc)

                    if not already_recorded:
                        # Create a debit transaction to zero out the folio
                        transfer_item = "REFUND-TRANSFER"
                        from hospitality_core.hospitality_core.api.night_audit import ensure_item_exists
                        ensure_item_exists(transfer_item, "Transfer to Balance Ledger")

                        # flags.hospitality_service=True — TRƯỚC ĐÂY thiếu, khiến
                        # property_scope.py's validate_document() throw ngay khi
                        # property cutover Property v2 — chặn đứng hủy đặt phòng
                        # có tiền cọc/thanh toán dư (kể cả no-show tự động, xem
                        # night_audit.py's cancel_no_shows() nay gọi lại đúng hàm
                        # này).
                        txn = frappe.get_doc({
                            "doctype": "Folio Transaction",
                            "parent": self.folio,
                            "parenttype": "Guest Folio",
                            "parentfield": "transactions",
                            "posting_date": frappe.utils.nowdate(),
                            "item": transfer_item,
                            "description": "Transfer to Guest Balance Ledger on Cancellation",
                            "qty": 1,
                            "amount": amount_to_transfer, # Debit
                            "bill_to": "Guest",
                            "is_void": 0
                        })
                        txn.flags.hospitality_service = True
                        txn.insert(ignore_permissions=True)

                        sync_folio_balance(folio_doc)

                frappe.db.set_value("Guest Folio", self.folio, "status", "Cancelled")
                frappe.msgprint(_("Linked Guest Folio {0} has been cancelled.").format(self.folio))
        
        return "Cancelled"

    def on_update(self):
        if self.status == 'Checked In' and self.has_value_changed('departure_date'):
            from hospitality_core.hospitality_core.api.rate_plan import reconcile_los
            reconcile_los(self)

        # Requirement: "make it possible for everybody to edit the is company and company field"
        # We handle the impact on billing and folio management here.
        if self.folio:
            folio_doc = frappe.get_doc("Guest Folio", self.folio)
            
            if folio_doc.company != self.company:
                folio_doc.db_set("company", self.company)
                
                if self.is_company_guest and self.company:
                    self.ensure_company_folio()
                    # Transition existing 'Guest' transactions to 'Company'
                    self.sync_transactions_to_company(folio_doc)
                elif not self.is_company_guest:
                    # Transition existing 'Company' transactions back to 'Guest'
                    self.sync_transactions_from_company(folio_doc)
            
            if folio_doc.room != self.room:
                folio_doc.db_set("room", self.room)

    def sync_transactions_to_company(self, folio_doc):
        from hospitality_core.hospitality_core.api.folio import mirror_to_company_folio, sync_folio_balance
        
        updated = False
        for txn in folio_doc.transactions:
            if txn.bill_to == "Guest" and not txn.is_void:
                txn.db_set("bill_to", "Company")
                mirror_to_company_folio(txn)
                updated = True
        
        if updated:
            sync_folio_balance(folio_doc)

    def sync_transactions_from_company(self, folio_doc):
        from hospitality_core.hospitality_core.api.folio import sync_folio_balance
        
        updated = False
        for txn in folio_doc.transactions:
            if txn.bill_to == "Company" and not txn.is_void:
                txn.db_set("bill_to", "Guest")
                # Remove mirrored transaction from Company Folio
                self.remove_mirrored_transaction(txn)
                updated = True
        
        if updated:
            sync_folio_balance(folio_doc)

    def remove_mirrored_transaction(self, original_txn):
        # TRƯỚC ĐÂY: tìm mirror qua reference_doctype='Folio Transaction' —
        # field này bị GHI ĐÈ thành 'Sales Invoice' ngay khi giao dịch được
        # xuất hóa đơn (invoicing.py's create_invoice_from_folio()), nên
        # mirror ĐÃ xuất hóa đơn sẽ không bao giờ được tìm thấy ở đây nữa —
        # dùng mirror_source (field bền hơn, không bị ghi đè khi xuất hóa đơn,
        # xem folio.py's mirror_to_company_folio/mirror_to_group_folio) làm
        # nguồn chân lý chính, giữ lại check reference_doctype cũ làm chốt
        # chặn phụ cho dữ liệu lịch sử trước khi có mirror_source.
        mirrored_names = set(frappe.get_all("Folio Transaction",
            filters={"mirror_source": original_txn.name}, pluck="name"))
        mirrored_names |= set(frappe.get_all("Folio Transaction", filters={
            "reference_doctype": "Folio Transaction",
            "reference_name": original_txn.name,
            "mirror_source": ["is", "not set"]
        }, pluck="name"))

        from hospitality_core.hospitality_core.api.folio import sync_folio_balance
        for m_name in mirrored_names:
            m_doc = frappe.get_doc("Folio Transaction", m_name)
            if m_doc.is_void:
                continue
            if m_doc.is_invoiced:
                # Đã lên hóa đơn — không thể tự động gỡ bỏ âm thầm, cần xử lý
                # điều chỉnh hóa đơn thủ công trước khi hủy khoản này.
                frappe.msgprint(_(
                    "Giao dịch mirror {0} trên Master Folio {1} đã được xuất hóa đơn — không thể tự động gỡ bỏ "
                    "khi chuyển về billing Guest. Vui lòng xử lý điều chỉnh hóa đơn thủ công."
                ).format(m_doc.name, m_doc.parent), indicator="orange")
                continue
            # TRƯỚC ĐÂY: frappe.delete_doc() — nhưng on_trash() (folio_transaction.py)
            # giờ CHẶN xóa bất kỳ giao dịch nào có pricing_details/pricing_origin
            # — mirror của charge/giảm giá do rate plan quản lý luôn có 1 trong
            # 2 field này (sao chép từ giao dịch gốc lúc tạo mirror), khiến
            # TOÀN BỘ việc lưu đặt phòng thất bại ngay khi bỏ tick "Is Company
            # Guest" cho khách đã có charge phòng qua engine mới. Đổi sang HỦY
            # (is_void=1, giữ lại để kiểm toán) thay vì xóa — khớp đúng triết
            # lý "không xóa lịch sử tính giá" của engine, và set
            # flags.from_folio_mirror để vượt qua validate_pricing_evidence()
            # (khớp đúng cờ mirror_to_company_folio()/mirror_to_group_folio()
            # đã dùng lúc TẠO mirror này).
            parent_folio = m_doc.parent
            m_doc.flags.from_folio_mirror = True
            m_doc.is_void = 1
            m_doc.void_reason = _("Đổi billing về Guest — gỡ bản mirror khỏi Master Folio")
            m_doc.save(ignore_permissions=True)
            sync_folio_balance(frappe.get_doc("Guest Folio", parent_folio))

# Whitelisted methods for client-side buttons
@frappe.whitelist()
def check_in_guest(name):
    # TRƯỚC ĐÂY: khóa FOR UPDATE bằng 1 câu SQL thô RIÊNG BIỆT, rồi mới
    # frappe.get_doc() BÌNH THƯỜNG (không khóa) để đọc trạng thái — dưới
    # REPEATABLE READ (mặc định MariaDB), câu get_doc() phía sau vẫn là một
    # plain SELECT, có thể trả về snapshot CŨ (status="Reserved") dù transaction
    # kia vừa check-in và commit xong ngay trước khi khóa được giải phóng cho
    # request này — process_check_in() vẫn thấy "Reserved" nên chạy tiếp,
    # tính tiền đêm đầu tiên LẦN THỨ HAI (double-click, hoặc 2 lễ tân thao tác
    # cùng lúc). Đây CHÍNH XÁC là lỗi snapshot-staleness đã từng sửa cho
    # sync_folio_balance()/create_invoice_from_folio() (xem folio.py/
    # invoicing.py) — sửa bằng cách biến chính câu ĐỌC DOC thành locking read
    # (for_update=True, khớp mẫu đã dùng ở night_audit.py's
    # process_single_reservation), thay vì tách rời khóa và đọc dữ liệu.
    doc = frappe.get_doc("Hotel Reservation", name, for_update=True)
    doc.check_permission("write")
    return doc.process_check_in()

@frappe.whitelist()
def check_out_guest(name):
    # Cùng lỗi snapshot-staleness đã sửa cho check_in_guest() (xem comment ở
    # đó) — check-out double-click/2 lễ tân thao tác cùng lúc trước đây vẫn
    # có thể cùng thấy status="Checked In" và cùng chạy process_check_out(),
    # có nguy cơ ghi 2 lần các giao dịch transfer sang City Ledger/Group
    # Master. Khóa read bằng for_update=True để tuần tự hóa, khớp mẫu đã
    # dùng ở check_in_guest().
    doc = frappe.get_doc("Hotel Reservation", name, for_update=True)
    doc.check_permission("write")
    return doc.process_check_out()

@frappe.whitelist()
def cancel_reservation(name):
    # Cùng lý do như check_out_guest() — hủy 2 lần gần như đồng thời trước
    # đây có thể cùng thấy already_recorded=False (process_cancel()'s guard
    # chống double-credit) và cùng ghi REFUND-TRANSFER, credit trùng khoản
    # tiền cọc dư vào Guest Balance Ledger.
    doc = frappe.get_doc("Hotel Reservation", name, for_update=True)
    doc.check_permission("write")
    return doc.process_cancel()
