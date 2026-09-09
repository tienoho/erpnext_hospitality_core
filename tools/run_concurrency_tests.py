"""Kịch bản kiểm thử ĐỒNG THỜI (concurrency) — Bước 5 của kế hoạch Docker
(build Docker đầy đủ + test toàn bộ kịch bản). Test nhẹ, có trọng điểm theo
đúng lựa chọn đã xác nhận với người dùng — KHÔNG phải hạ tầng load-test quy
mô lớn, chỉ nhắm đúng 3 điểm khóa/mutex đã xác nhận qua đọc mã nguồn:

1. 2 tiến trình cùng approve_recipe() cho 2 bản nháp MỚI (chưa có dòng để
   khóa riêng) trùng khoảng hiệu lực — outlet() dùng làm mutex nhân tạo.
2. 2 tiến trình cùng start_count() cho CÙNG 1 kho — FNB Warehouse Control's
   FOR UPDATE là mutex tự nhiên (đã có sẵn dòng theo kho).
3. 2 POS Invoice cùng bán đúng 1 đơn vị tồn kho biên (không qua FNB) —
   deduct_stock_items_for_pos_invoice() + Stock Entry.submit()'s khóa Bin
   chuẩn ERPNext.

Mỗi nhánh dùng 1 TIẾN TRÌNH HỆ ĐIỀU HÀNH RIÊNG (frappe.init()/connect() độc
lập) để tạo race điều kiện DB THẬT — không phải giả lập tuần tự trong 1
connection (1 connection không thể tự block chính nó ở FOR UPDATE). Đồng bộ
thời điểm bắt đầu qua mốc thời gian tuyệt đối (start_at) để tối đa hóa khả
năng va chạm thật, bất kể độ trễ setup (frappe.init/connect) khác nhau giữa
2 tiến trình.

QUAN TRỌNG — dữ liệu PHẢI được commit() để tiến trình worker (connection
riêng) nhìn thấy được, khác hẳn mọi script test khác trong thư mục này (chỉ
rollback() cuối mỗi ca). Điều này đã từng gây sự cố THẬT: lần chạy đầu tiên
dùng thẳng accounting_reservation()/setup_control() (helper dùng chung của
run_property_integration.py, vốn CHỈ được thiết kế an toàn khi mỗi lần gọi
đều được rollback() ngay sau — nhiều tên cố định như Price List "Integration
Selling" KHÔNG có kiểm tra tồn tại trước khi insert()) rồi commit() luôn —
làm Ô NHIỄM VĨNH VIỄN site test dùng chung, khiến TOÀN BỘ run_property_
integration.py (10/14 ca) crash "Duplicate entry Integration Selling" ngay
sau đó, phải bench reinstall site để khôi phục. Đã sửa bằng cách: (1) LUÔN
dọn dẹp (best-effort, không phụ thuộc site reinstall) mọi bản ghi kịch bản
này tạo ra trong khối finally, chạy dù thành công hay lỗi; (2) không đụng
tới các fixture nền dùng chung có sẵn (Company/Warehouse Type/Fiscal Year/
Item Group "Services" — đã idempotent-guarded, các script khác phụ thuộc
chúng tồn tại lâu dài).

Chạy: python run_concurrency_tests.py
"""
import json
import subprocess
import sys
import time
from pathlib import Path

SITE = 'localhost'
SITES = Path('/home/frappe/test-bench/sites')
WORKER_TIMEOUT = 90


def _setup_frappe():
    import frappe
    frappe.init(site=SITE, sites_path=str(SITES))
    frappe.connect()
    frappe.set_user('Administrator')
    frappe.flags.in_test = True
    frappe.conf.hospitality_v2_release_verified = 1
    frappe.conf.fnb_release_verified = 1
    return frappe


def _make_pos_sale(frappe, payload):
    from frappe.utils import nowdate
    inv = frappe.get_doc(dict(doctype='POS Invoice', company=payload['company'], customer=payload['customer'],
        pos_profile=payload['pos_profile'], currency='VND', conversion_rate=1,
        selling_price_list=frappe.db.get_single_value('Selling Settings', 'selling_price_list'),
        posting_date=nowdate(), paid_amount=payload['amount'],
        items=[dict(item_code=payload['item'], qty=1, rate=payload['amount'], warehouse=payload['warehouse'])],
        payments=[dict(mode_of_payment=payload['mode_of_payment'], amount=payload['amount'])]))
    inv.insert(ignore_permissions=True)
    inv.submit()
    return inv.name


def _log(msg):
    print(f'[{time.time():.2f}] {msg}', flush=True)


def _worker_main():
    mode = sys.argv[2]
    payload = json.loads(sys.argv[3])
    start_at = float(sys.argv[4])
    _log(f'boot start mode={mode}')
    frappe = _setup_frappe()
    _log('frappe init/connect done')

    def _tid():
        try:
            return frappe.db._conn.thread_id()
        except Exception:
            return '?'

    _log(f'connection thread_id={_tid()}')
    frappe.set_user(payload.get('user', 'Administrator'))
    now = time.time()
    if start_at > now:
        _log(f'sleeping {start_at - now:.2f}s until start_at')
        time.sleep(start_at - now)
    _log(f'calling target function, thread_id={_tid()}')
    result = {'ok': False, 'error': None, 'doc': None}
    try:
        if mode == 'approve_recipe':
            from hospitality_core.hospitality_core.api.fnb.recipes import approve_recipe
            approve_recipe(payload['recipe'])
        elif mode == 'start_count':
            from hospitality_core.hospitality_core.api.fnb.counts import start_count
            start_count(payload['count'])
        elif mode == 'pos_sale':
            result['doc'] = _make_pos_sale(frappe, payload)
        else:
            raise ValueError(f'unknown mode {mode}')
        _log(f'target function returned, thread_id={_tid()}, committing')
        frappe.db.commit()
        result['ok'] = True
    except Exception as e:
        _log(f'target function raised {type(e).__name__}: {e}, thread_id={_tid()}')
        frappe.db.rollback()
        result['error'] = f'{type(e).__name__}: {e}'
    finally:
        frappe.destroy()
    _log('worker done')
    print('RESULT:' + json.dumps(result))


def launch(mode, payload, start_at):
    args = [sys.executable, str(Path(__file__).resolve()), '--worker', mode, json.dumps(payload), str(start_at)]
    return subprocess.Popen(args, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)


def wait_all(procs, timeout=WORKER_TIMEOUT):
    results = []
    deadline = time.time() + timeout
    for p in procs:
        remaining = max(0.1, deadline - time.time())
        try:
            out, _ = p.communicate(timeout=remaining)
            results.append(('DONE', out))
        except subprocess.TimeoutExpired:
            p.kill()
            out, _ = p.communicate()
            results.append(('TIMEOUT', out))
    return results


def parse_result(out):
    for line in reversed(out.strip().splitlines()):
        if line.startswith('RESULT:'):
            return json.loads(line[len('RESULT:'):])
    return {'ok': False, 'error': 'NO_RESULT_LINE: ' + out[-500:]}


def race(label, mode, payload_a, payload_b, expect_regex):
    import re
    start_at = time.time() + 2.5
    procs = [launch(mode, payload_a, start_at), launch(mode, payload_b, start_at)]
    raw = wait_all(procs)
    outcomes = []
    for status, out in raw:
        if status == 'TIMEOUT':
            outcomes.append({'ok': False, 'error': 'TIMEOUT/DEADLOCK', 'raw': out[-1500:]})
        else:
            parsed = parse_result(out)
            parsed['raw'] = out[-1500:]
            outcomes.append(parsed)
    oks = [o for o in outcomes if o.get('ok')]
    fails = [o for o in outcomes if not o.get('ok')]
    problems = []
    if any(o.get('error') == 'TIMEOUT/DEADLOCK' for o in outcomes):
        problems.append('TREO/DEADLOCK — ít nhất 1 nhánh không hoàn tất trong thời gian chờ.')
    if len(oks) != 1 or len(fails) != 1:
        problems.append(f'Kỳ vọng đúng 1 thành công + 1 bị chặn, thực tế: {len(oks)} thành công, {len(fails)} thất bại.')
    elif not re.search(expect_regex, fails[0].get('error') or ''):
        problems.append(f'Nhánh thất bại có lỗi không đúng kỳ vọng (regex {expect_regex!r}): {fails[0].get("error")}')
    status_line = 'OK' if not problems else 'FAIL'
    print(f'[{status_line}] {label}')
    for i, o in enumerate(outcomes):
        print(f'    nhánh {i+1}: ok={o.get("ok")} error={o.get("error")}')
        if o.get('raw'):
            for line in o['raw'].splitlines():
                print(f'        | {line}')
    for p in problems:
        print(f'    !! {p}')
    return not problems, outcomes


def _safe_delete(frappe, doctype, name, cancel=False):
    if not name or not frappe.db.exists(doctype, name):
        return
    try:
        if cancel:
            doc = frappe.get_doc(doctype, name)
            if doc.get('docstatus') == 1:
                doc.cancel()
        frappe.delete_doc(doctype, name, force=True, ignore_permissions=True, ignore_missing=True)
        frappe.db.commit()
    except Exception as e:
        print(f'    (dọn dẹp) không xóa được {doctype} {name}: {type(e).__name__}: {e}')
        frappe.db.rollback()


def cleanup(frappe, state):
    """Best-effort — chạy trong finally, không phụ thuộc site reinstall để
    khôi phục. Chỉ xóa những gì CHÍNH kịch bản này tạo ra (kể cả những gì
    accounting_reservation()/setup_control() tạo bằng tên cố định) — KHÔNG
    đụng tới Company/Warehouse Type/Fiscal Year/Item Group "Services" (fixture
    nền dùng chung, idempotent-guarded, các script khác phụ thuộc tồn tại lâu
    dài)."""
    print('--- dọn dẹp dữ liệu kịch bản concurrency ---')
    for doctype, name in reversed(state.get('pos_docs', [])):
        _safe_delete(frappe, doctype, name, cancel=True)
    for doctype, name in reversed(state.get('scenario3', [])):
        _safe_delete(frappe, doctype, name, cancel=True)
    for doctype, name in reversed(state.get('scenario1_2', [])):
        _safe_delete(frappe, doctype, name, cancel=True)
    company = state.get('company')
    if company:
        for bom in frappe.get_all('BOM', filters={'company': company, 'item': ['like', 'FNB-RACE%']}, pluck='name'):
            _safe_delete(frappe, 'BOM', bom, cancel=True)
        for acc in frappe.get_all('Account', filters={'company': company, 'account_name': ['like', 'Integration%']}, pluck='name'):
            _safe_delete(frappe, 'Account', acc)
        for tmpl in frappe.get_all('Sales Taxes and Charges Template', filters={'company': company, 'title': ['like', 'Integration%']}, pluck='name'):
            _safe_delete(frappe, 'Sales Taxes and Charges Template', tmpl)
    for doctype, name in reversed(state.get('reservation_fixture', [])):
        _safe_delete(frappe, doctype, name, cancel=True)
    if frappe.db.exists('Price List', 'Integration Selling'):
        _safe_delete(frappe, 'Price List', 'Integration Selling')
    print('--- dọn dẹp xong ---')


def main():
    frappe = _setup_frappe()
    from run_fnb_control_integration import CostControlTests
    from frappe.utils import nowdate, add_days, now_datetime

    all_ok = True
    state = {'pos_docs': [], 'scenario3': [], 'scenario1_2': [], 'reservation_fixture': [], 'company': None}

    try:
        # ------------------------------------------------------------------
        # 1) approve_recipe() — 2 bản nháp MỚI, trùng khoảng hiệu lực, đua nhau.
        # ------------------------------------------------------------------
        t = CostControlTests()
        t.setup_control()
        state['company'] = t.company
        # accounting_reservation() (bên trong setup_control()) tạo các bản ghi
        # tên cố định dùng chung — ghi lại để dọn dẹp đúng sau khi commit().
        state['reservation_fixture'] += [
            ('Hotel Reservation', t.reservation.name),
            ('Guest', t.reservation.guest),
            ('Customer', t.reservation.billing_customer),
            ('Hospitality Property Settings', 'HV-A'),
            ('Hospitality Company Accounting Settings', t.company),
        ]
        # Lưu ý: KHÔNG xóa t.warehouse — đó là warehouse chung của company
        # (do accounting_reservation()/setUpClass() tạo idempotent), không
        # phải riêng của kịch bản này.
        state['scenario1_2'] += [
            ('Stock Entry', t.receipt.name), ('BOM', t.bom.name),
            ('Item', t.raw.name), ('Item', t.dish.name),
            ('FNB Settings', t.config.name), ('FNB Outlet', t.out.name),
            ('Warehouse', t.config.main_warehouse), ('Warehouse', t.config.transit_warehouse),
            ('User', t.operator),
        ]

        race_item = frappe.get_doc(dict(doctype='Item', item_code='FNB-RACE-DISH', item_name='FNB race dish',
            item_group='Services', stock_uom='FB portion', is_stock_item=0)).insert()
        state['scenario1_2'].append(('Item', race_item.name))
        frappe.set_user('Administrator')
        future = add_days(nowdate(), 30) + ' 00:00:00'
        drafts = []
        for i in range(2):
            d = frappe.get_doc(dict(doctype='FNB Recipe Version', property=t.reservation.property, outlet=t.out.name,
                item=race_item.name, quantity=1, uom='FB portion', effective_from=future,
                ingredients=[dict(item=t.raw.name, qty=100, uom='FB g')])).insert()
            drafts.append(d.name)
            state['scenario1_2'].append(('FNB Recipe Version', d.name))
        frappe.db.commit()
        ok1, _ = race('approve_recipe() — 2 bản nháp trùng hiệu lực, đua nhau duyệt',
            'approve_recipe', dict(user=t.operator, recipe=drafts[0]), dict(user=t.operator, recipe=drafts[1]),
            r'trùng')
        all_ok = all_ok and ok1

        # ------------------------------------------------------------------
        # 2) start_count() — 2 phiên kiểm kê MỚI, cùng 1 kho, đua nhau start.
        # ------------------------------------------------------------------
        frappe.set_user(t.operator)
        counts = []
        for i in range(2):
            c = frappe.get_doc(dict(doctype='FNB Stock Count', property=t.reservation.property, outlet=t.out.name,
                warehouse=t.warehouse, posting_datetime=now_datetime(), reason=f'Concurrency race {i}')).insert()
            counts.append(c.name)
            state['scenario1_2'].append(('FNB Stock Count', c.name))
        frappe.set_user('Administrator')
        frappe.db.commit()
        ok2, _ = race('start_count() — 2 phiên kiểm kê cùng 1 kho, đua nhau start',
            'start_count', dict(user=t.operator, count=counts[0]), dict(user=t.operator, count=counts[1]),
            r'kiểm kê')
        all_ok = all_ok and ok2

        # ------------------------------------------------------------------
        # 3) 2 POS Invoice cùng bán đúng 1 đơn vị tồn kho biên (không qua FNB).
        # Tái dùng company/warehouse đã có từ kịch bản 1 (t) — KHÔNG gọi lại
        # accounting_reservation() lần 2 (xem docstring đầu file: gọi lần 2
        # trong cùng transaction/site đã từng crash Duplicate Entry).
        # ------------------------------------------------------------------
        company = t.company
        warehouse = t.warehouse
        if not frappe.db.exists('UOM', 'Nos'):
            frappe.get_doc(dict(doctype='UOM', uom_name='Nos')).insert()
        race_stock_item = frappe.get_doc(dict(doctype='Item', item_code='RACE-STOCK-ITEM', item_name='Race stock item',
            item_group='Services', stock_uom='Nos', is_stock_item=1)).insert()
        state['scenario3'].append(('Item', race_stock_item.name))
        receipt = frappe.new_doc('Stock Entry')
        receipt.stock_entry_type = 'Material Receipt'
        receipt.purpose = 'Material Receipt'
        receipt.company = company
        receipt.append('items', dict(item_code=race_stock_item.name, qty=1, uom='Nos', t_warehouse=warehouse,
            basic_rate=50000, cost_center=frappe.get_cached_value('Company', company, 'cost_center')))
        receipt.insert(ignore_permissions=True)
        receipt.submit()
        state['scenario3'].append(('Stock Entry', receipt.name))
        customer = 'Walk in Customer'
        if not frappe.db.exists('Customer', customer):
            frappe.get_doc(dict(doctype='Customer', customer_name=customer, customer_type='Individual',
                customer_group=frappe.db.get_value('Customer Group', {'is_group': 0}),
                territory=frappe.db.get_value('Territory', {'is_group': 0}))).insert(ignore_permissions=True)
        cash = frappe.db.get_value('Account', {'company': company, 'account_type': 'Cash', 'is_group': 0}, 'name')
        if not frappe.db.exists('Mode of Payment', 'Race Cash'):
            frappe.get_doc(dict(doctype='Mode of Payment', mode_of_payment='Race Cash', type='Cash',
                accounts=[dict(company=company, default_account=cash)])).insert()
            state['scenario3'].append(('Mode of Payment', 'Race Cash'))
        pos_profile_name = 'Race POS'
        if not frappe.db.exists('POS Profile', pos_profile_name):
            income = frappe.db.get_value('Hospitality Company Accounting Settings', company, 'income_account')
            expense = frappe.db.get_value('Company', company, 'default_expense_account') or income
            frappe.get_doc(dict(doctype='POS Profile', name=pos_profile_name, company=company, currency='VND',
                warehouse=warehouse, selling_price_list=frappe.db.get_single_value('Selling Settings', 'selling_price_list'),
                income_account=income, expense_account=expense,
                cost_center=frappe.db.get_value('Hospitality Company Accounting Settings', company, 'cost_center'),
                write_off_account=income, write_off_cost_center=frappe.db.get_value('Hospitality Company Accounting Settings', company, 'cost_center'),
                payments=[dict(mode_of_payment='Race Cash', default=1)])).insert(ignore_permissions=True)
            state['scenario3'].append(('POS Profile', pos_profile_name))
        if not frappe.db.exists('POS Opening Entry', {'pos_profile': pos_profile_name, 'status': 'Open'}):
            opening = frappe.get_doc(dict(doctype='POS Opening Entry', company=company, pos_profile=pos_profile_name,
                user='Administrator', period_start_date=now_datetime(), posting_date=nowdate(),
                balance_details=[dict(mode_of_payment='Race Cash', opening_amount=0)]))
            opening.insert(ignore_permissions=True)
            opening.submit()
            state['scenario3'].append(('POS Opening Entry', opening.name))
        frappe.db.commit()
        pos_payload = dict(user='Administrator', company=company, customer=customer, pos_profile=pos_profile_name,
            item=race_stock_item.name, warehouse=warehouse, mode_of_payment='Race Cash', amount=50000)
        ok3, outcomes3 = race('2 POS Invoice cùng bán 1 đơn vị tồn kho biên (tồn=1)',
            'pos_sale', pos_payload, pos_payload,
            r'stock|Stock|kho|negative|Negative|khả dụng')
        for o in outcomes3:
            if o.get('doc'):
                state['pos_docs'].append(('POS Invoice', o['doc']))
                se = frappe.get_all('Stock Entry', filters={'custom_source_invoice': o['doc']}, pluck='name')
                state['pos_docs'] += [('Stock Entry', s) for s in se]
        all_ok = all_ok and ok3

        print()
        print('TỔNG KẾT:', 'TẤT CẢ ĐÚNG KỲ VỌNG' if all_ok else 'CÓ VẤN ĐỀ CẦN XEM LẠI')
    finally:
        frappe.db.rollback()
        cleanup(frappe, state)
        frappe.destroy()
    sys.exit(0 if all_ok else 1)


if __name__ == '__main__':
    if len(sys.argv) > 1 and sys.argv[1] == '--worker':
        _worker_main()
    else:
        main()
