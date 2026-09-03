# -*- coding: utf-8 -*-
"""
Tích Hợp Hóa Đơn Điện Tử (E-Invoice) theo Thông tư 78 / Nghị định 123.

Kiến trúc Adapter: mỗi nhà cung cấp (VNPT, Viettel, MISA meInvoice) là một
class kế thừa `BaseEInvoiceProvider`. Hiện tại chỉ `MockProvider` được cài đặt
đầy đủ để test luồng UI/API mà không cần hợp đồng/API key thật. Khi công ty
đã có tài khoản thật với một nhà cung cấp, chỉ cần điền cấu hình trong
`Hospitality Accounting Settings` và cài đặt phần thân của provider tương ứng
bên dưới (nơi có `NotImplementedError`) — không cần đổi gì ở guest_folio.js
hay hàm `issue_einvoice`.
"""
import frappe
from frappe import _
from frappe.utils import now_datetime, flt


class BaseEInvoiceProvider:
    def __init__(self, settings):
        self.settings = settings

    def issue(self, invoice_doc, payload):
        """Must return dict: {invoice_number, lookup_code, raw_response}"""
        raise NotImplementedError

    def get_status(self, invoice_number):
        raise NotImplementedError


class MockProvider(BaseEInvoiceProvider):
    """
    Local sandbox provider. Generates a deterministic-looking fake invoice
    number/lookup code so the rest of the system (button, status field,
    printout) can be built and tested end-to-end before real credentials
    exist.
    """

    def issue(self, invoice_doc, payload):
        stamp = now_datetime().strftime("%y%m%d%H%M%S")
        is_pos = payload.get("is_cash_register", False)
        prefix = "MTT" if is_pos else "MOCK"
        return {
            "invoice_number": f"{prefix}-{stamp}",
            "lookup_code": f"{prefix}LOOKUP-{invoice_doc.name}-{stamp}",
            "tax_authority_code": f"CQT-QN-{stamp}" if is_pos else "",
            "raw_response": {"mode": "mock", "payload": payload},
        }

    def get_status(self, invoice_number):
        return {"status": "Issued", "raw_response": {"mode": "mock"}}


class VnptProvider(BaseEInvoiceProvider):
    def issue(self, invoice_doc, payload):
        # TODO: call the real VNPT S-Invoice API here using
        # self.settings.einvoice_api_endpoint / get_password("einvoice_api_key").
        raise NotImplementedError(_(
            "VNPT chưa được cấu hình. Vui lòng liên hệ VNPT để lấy API Endpoint/API Key "
            "và điền vào Hospitality Accounting Settings trước khi phát hành."
        ))

    def get_status(self, invoice_number):
        raise NotImplementedError


class ViettelProvider(BaseEInvoiceProvider):
    def issue(self, invoice_doc, payload):
        # TODO: call the real Viettel S-Invoice API here.
        raise NotImplementedError(_(
            "Viettel S-Invoice chưa được cấu hình. Vui lòng liên hệ Viettel để lấy API "
            "credentials và điền vào Hospitality Accounting Settings trước khi phát hành."
        ))

    def get_status(self, invoice_number):
        raise NotImplementedError


class MisaProvider(BaseEInvoiceProvider):
    def issue(self, invoice_doc, payload):
        # TODO: call the real MISA meInvoice API here.
        raise NotImplementedError(_(
            "MISA meInvoice chưa được cấu hình. Vui lòng liên hệ MISA để lấy API "
            "credentials và điền vào Hospitality Accounting Settings trước khi phát hành."
        ))

    def get_status(self, invoice_number):
        raise NotImplementedError


PROVIDERS = {
    "Mock": MockProvider,
    "VNPT": VnptProvider,
    "Viettel": ViettelProvider,
    "MISA meInvoice": MisaProvider,
}


def _get_provider():
    settings = frappe.get_single("Hospitality Accounting Settings")
    provider_name = settings.einvoice_provider or "Mock"
    provider_cls = PROVIDERS.get(provider_name, MockProvider)
    return provider_cls(settings), settings


def _build_payload(invoice_doc, settings):
    """
    Buckets invoice items into tax categories using the flat default VAT
    rate configured in settings. Supports both regular E-Invoices and
    POS Cash Register E-Invoices (Khởi tạo từ máy tính tiền có mã CQT).
    """
    lines = []
    for item in invoice_doc.items:
        lines.append({
            "description": item.description or item.item_name or item.item_code,
            "qty": flt(item.qty),
            "unit_price": flt(item.rate),
            "amount": flt(item.amount),
        })

    is_pos = bool(getattr(settings, "enable_pos_cash_register", 1))
    template_code = getattr(settings, "pos_invoice_template", "1C26MNG") if is_pos else "1C26TAA"

    return {
        "buyer_tax_code": settings.einvoice_tax_code,
        "customer": invoice_doc.customer_name or invoice_doc.customer,
        "invoice_date": str(invoice_doc.posting_date),
        "currency": invoice_doc.currency,
        "vat_rate": flt(settings.einvoice_default_vat_rate or 8),
        "is_cash_register": is_pos,
        "invoice_template": template_code,
        "lines": lines,
        "grand_total": flt(invoice_doc.grand_total),
    }


@frappe.whitelist()
def issue_einvoice(sales_invoice):
    """
    Issues an e-invoice for a submitted Sales Invoice and records the
    result (status/number/lookup code) on the invoice itself.
    """
    invoice_doc = frappe.get_doc("Sales Invoice", sales_invoice)

    if invoice_doc.docstatus != 1:
        frappe.throw(_("The Sales Invoice must be submitted before issuing an E-Invoice."))

    if invoice_doc.get("einvoice_status") == "Issued":
        frappe.throw(_("An E-Invoice has already been issued for {0} (No. {1}).").format(
            sales_invoice, invoice_doc.get("einvoice_number")
        ))

    provider, settings = _get_provider()
    payload = _build_payload(invoice_doc, settings)

    try:
        result = provider.issue(invoice_doc, payload)
    except NotImplementedError as e:
        frappe.throw(str(e) or _("This E-Invoice provider is not yet implemented."))

    frappe.db.set_value("Sales Invoice", sales_invoice, {
        "einvoice_status": "Issued",
        "einvoice_provider": settings.einvoice_provider,
        "einvoice_number": result["invoice_number"],
        "einvoice_lookup_code": result["lookup_code"],
        "einvoice_issued_on": now_datetime(),
    })

    frappe.get_doc("Sales Invoice", sales_invoice).add_comment(
        "Info",
        _("E-Invoice issued via {0}: No. {1}, Lookup Code {2}").format(
            settings.einvoice_provider, result["invoice_number"], result["lookup_code"]
        ),
    )

    return {
        "einvoice_status": "Issued",
        "einvoice_number": result["invoice_number"],
        "einvoice_lookup_code": result["lookup_code"],
    }


@frappe.whitelist()
def get_einvoice_status(sales_invoice):
    invoice_doc = frappe.get_doc("Sales Invoice", sales_invoice)
    return {
        "einvoice_status": invoice_doc.get("einvoice_status") or "Not Issued",
        "einvoice_provider": invoice_doc.get("einvoice_provider"),
        "einvoice_number": invoice_doc.get("einvoice_number"),
        "einvoice_lookup_code": invoice_doc.get("einvoice_lookup_code"),
        "einvoice_issued_on": invoice_doc.get("einvoice_issued_on"),
    }


@frappe.whitelist()
def issue_einvoice_from_folio(folio_name):
    """
    Phát hành Hóa đơn điện tử trực tiếp từ Guest Folio.
    Tự động liên kết hoặc sinh Sales Invoice tương ứng, submit và phát hành E-Invoice.
    """
    from hospitality_core.hospitality_core.api.invoicing import create_invoice_from_folio

    folio_doc = frappe.get_doc("Guest Folio", folio_name)
    
    # Check if there is an existing submitted Sales Invoice for this folio
    existing_si = frappe.db.get_value(
        "Sales Invoice",
        {"custom_guest_folio": folio_name, "docstatus": 1},
        "name"
    ) or frappe.db.get_value(
        "Sales Invoice Item",
        {"guest_folio": folio_name, "docstatus": 1},
        "parent"
    )

    if not existing_si:
        # Create Sales Invoice from unbilled items
        si_name = create_invoice_from_folio(folio_name)
        if not si_name:
            frappe.throw(_("Không thể tạo Hóa đơn bán hàng từ Folio này hoặc không có chi phí chưa lập hóa đơn."))
        
        si_doc = frappe.get_doc("Sales Invoice", si_name)
        if si_doc.docstatus == 0:
            si_doc.submit()
        existing_si = si_name

    # Issue E-Invoice for the submitted Sales Invoice
    result = issue_einvoice(existing_si)
    result["sales_invoice"] = existing_si
    return result

