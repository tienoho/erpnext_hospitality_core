import frappe
from frappe import _
from frappe.utils import flt
from frappe.model.document import Document
from frappe.model.naming import make_autoname

class GuestFolio(Document):
    def autoname(self):
        # Different Naming for Company Master Folios
        if self.is_company_master:
            # e.g., MASTER-GOOGLE
            # We sanitize the company name
            company_key = self.company.replace(" ", "")[:10].upper()
            self.name = make_autoname(f"MASTER-{company_key}-.#####")
        else:
            # Standard Guest Folio: FOLIO-RES-GUEST
            if self.reservation:
                self.name = make_autoname("FOLIO-.#####")
            else:
                self.name = make_autoname("FOLIO-.#####")

    def validate(self):
        # Child table lưu qua parent không tự chạy validate() của controller con.
        for row in self.transactions or []:
            row.validate_pricing_evidence()
        if not self.is_new():
            protected = frappe.get_all('Folio Transaction', filters={'parent': self.name},
                fields=['name', 'pricing_details', 'pricing_origin'])
            remaining = {r.name for r in self.transactions or []}
            if any(r.name not in remaining and (r.pricing_details or r.pricing_origin) for r in protected):
                frappe.throw(_('Không được xóa dòng có lịch sử tính giá; hãy hủy tiền phòng gốc.'))

        # Enforce chronological order of transactions
        if self.transactions:
            self.transactions.sort(key=lambda x: (x.posting_date or "", x.posting_time or "", x.creation or ""))
            for i, d in enumerate(self.transactions):
                d.idx = i + 1
            
        self.validate_status_change()
        self.validate_master_folio()

    def validate_master_folio(self):
        if self.is_company_master and not self.company:
            frappe.throw(_("Company is mandatory for a Company Master Folio."))
        
        if not self.is_company_master and not self.reservation:
            # Regular guest folios usually need a reservation
            pass

    def validate_status_change(self):
        if self.status == "Closed":
            # Check if this folio belongs to a Company or Group Guest
            is_company_guest = False
            is_group_guest = False
            if self.reservation:
                res_flags = frappe.db.get_value("Hotel Reservation", self.reservation,
                    ["is_company_guest", "is_group_guest"], as_dict=True)
                if res_flags:
                    is_company_guest = res_flags.is_company_guest
                    is_group_guest = res_flags.is_group_guest

            # Nếu là khách Company HOẶC Group, chỉ phần bill_to="Guest" (VD
            # minibar cá nhân) mới cần khách tự thanh toán trước khi đóng
            # folio — phần bill_to="Company"/"Group" thuộc trách nhiệm của
            # công ty/đoàn (đã/sẽ chuyển sang Master Folio riêng).
            # TRƯỚC ĐÂY: chỉ is_company_guest được miễn trừ — khách ĐOÀN
            # (is_group_guest) rơi vào nhánh strict enforcement (kiểm tra
            # TOÀN BỘ outstanding_balance, kể cả phần bill_to="Group"), có
            # thể chặn đóng folio dù phần nợ đó đã/sẽ do đoàn chịu trách
            # nhiệm — nhất quán với is_company_guest.
            if not is_company_guest and not is_group_guest:
                # Only prevent closure if there is a DEBIT balance (guest owes money)
                # CREDIT balances (guest is owed money) are recorded in the Guest Balance Ledger.
                if self.outstanding_balance > 0.01:
                    frappe.throw(
                        _("Cannot Close Folio. Outstanding Balance is {0}. Please settle payments or post allowances.").format(self.outstanding_balance)
                    )
            else:
                guest_billed_outstanding = sum(
                    flt(t.amount) for t in (self.transactions or [])
                    if not t.is_void and t.bill_to == "Guest"
                )
                if guest_billed_outstanding > 0.01:
                    frappe.throw(
                        _("Cannot Close Folio. Guest-billed Outstanding Balance is {0}. Please settle payments or post allowances.").format(guest_billed_outstanding)
                    )

    def after_save(self):
        if self.status == "Closed":
            from hospitality_core.hospitality_core.api.folio import record_guest_balance
            record_guest_balance(self)

    def on_trash(self):
        if self.transactions:
            frappe.throw(_("Cannot delete a Folio that has transactions. Cancel it instead."))
    
