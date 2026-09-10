"""Chạy độc lập: python -m unittest discover -s tests -v.

Quy tắc giá chạy thật; kiểm thử tích hợp dùng DB trong bộ nhớ, không chạm site.
"""
import ast
import copy
import importlib.util
import json
import sys
import types
import unittest
from datetime import date, datetime, timedelta
from pathlib import Path
from unittest.mock import patch

from hospitality_core.hospitality_core.api.rate_calculation import (
    discount_breakdown, quote_day, quote_stay, validate_rules,
)

ROOT = Path(__file__).resolve().parents[1]
CORE = ROOT / 'hospitality_core/hospitality_core'


def rules():
    return dict(rate_plan='P', room_type='Standard', default_rate=150, precision=2,
        seasons=[dict(season_name='Mùa 1', valid_from='2026-01-01', valid_to='2026-12-31',
                      weekday_rate=100, weekend_rate=200)],
        los_discounts=[dict(min_nights=3, discount_percent=10), dict(min_nights=7, discount_percent=20)])


class PricingTests(unittest.TestCase):
    def test_weekday_weekend_and_season_endpoints(self):
        for day, expected in [('2026-09-03', 100), ('2026-09-04', 200), ('2026-09-05', 200),
                              ('2026-09-06', 100), ('2026-01-01', 100), ('2026-12-31', 100)]:
            with self.subTest(day=day):
                self.assertEqual(quote_day(rules(), day)['base_rate'], expected)

    def test_default_rate_still_gets_los_when_nights_qualify(self):
        # QUYẾT ĐỊNH ĐÃ CHỐT (xem rate_calculation.py's quote_day() comment):
        # LOS là chính sách theo TỔNG SỐ ĐÊM của cả kỳ lưu trú, độc lập với
        # việc đêm đó có rơi vào mùa vụ hay không (Season và LOS là 2 trục
        # độc lập) — 1 đêm dùng default_rate (ngoài mọi mùa vụ) VẪN được
        # tính LOS nếu tổng số đêm đủ điều kiện. Trước đây test này (tên cũ
        # "test_default_never_gets_los") khẳng định NGƯỢC LẠI — đã đổi tên +
        # sửa kỳ vọng khớp đúng quyết định đã chốt.
        # nights=8 (25/12 -> 02/01) đủ điều kiện tier min_nights=7 (20%):
        # 150 - 150*20% = 120.
        self.assertEqual(quote_day(rules(), '2027-01-01', '2026-12-25', '2027-01-02')['final_rate'], 120)

    def test_zero_weekend_means_weekday(self):
        r = rules(); r['seasons'][0]['weekend_rate'] = 0
        self.assertEqual(quote_day(r, '2026-09-04')['final_rate'], 100)

    def test_los_unsorted_thresholds_and_missing_dates(self):
        r = rules(); r['los_discounts'].reverse()
        for end, expected in [('2026-09-08', 100), ('2026-09-09', 90), ('2026-09-13', 80), (None, 100)]:
            self.assertEqual(quote_day(r, '2026-09-06', '2026-09-06', end)['final_rate'], expected)

    def test_duplicate_threshold_rejected_in_either_order(self):
        r = rules(); r['los_discounts'].append(dict(min_nights=3, discount_percent=30))
        for _ in range(2):
            with self.assertRaises(ValueError): validate_rules(r['seasons'], r['los_discounts'])
            r['los_discounts'].reverse()

    def test_invalid_rules(self):
        for value in [-1, 101]:
            with self.assertRaises(ValueError): validate_rules([], [dict(min_nights=3, discount_percent=value)])
        for value in [0, -1, 1.5]:
            with self.assertRaises(ValueError): validate_rules([], [dict(min_nights=value, discount_percent=10)])
        for key in ['weekday_rate', 'weekend_rate']:
            r = rules(); r['seasons'][0][key] = -1
            with self.assertRaises(ValueError): validate_rules(r['seasons'], [])

    def test_overlap_including_shared_boundary(self):
        a = rules()['seasons'][0]
        b = dict(a, valid_from='2026-12-31', valid_to='2027-01-01')
        with self.assertRaises(ValueError): validate_rules([a, b], [])
        b['valid_from'] = '2027-01-01'
        validate_rules([a, b], [])

    def test_multi_night_quote(self):
        q = quote_stay(rules(), '2026-09-03', '2026-09-06')
        self.assertEqual([r['final_rate'] for r in q['nightly_rates']], [90, 180, 180])
        self.assertEqual(q['total'], 450)

    def test_cross_season_and_default(self):
        r = rules(); r['seasons'][0]['valid_to'] = '2026-09-03'
        r['seasons'].append(dict(r['seasons'][0], valid_from='2026-09-04', valid_to='2026-09-04', weekend_rate=300))
        # Đêm thứ 3 (09-05) không khớp mùa vụ nào -> dùng default_rate=150,
        # nhưng LOS (tier min_nights=3, 10%) vẫn áp dụng đúng theo quyết định
        # đã chốt (Season và LOS là 2 trục độc lập): 150 - 10% = 135, không
        # còn giữ nguyên 150 như hành vi cũ đã bị bác bỏ.
        self.assertEqual([q['final_rate'] for q in quote_stay(r, '2026-09-03', '2026-09-06')['nightly_rates']], [90, 270, 135])

    def test_discount_capped_after_los(self):
        q = quote_day(rules(), '2026-09-06', '2026-09-06', '2026-09-09', 'Amount', 95)
        self.assertEqual((q['los_discount'], q['manual_discount'], q['final_rate']), (10, 90, 0))

    def test_percentage_and_complimentary(self):
        self.assertEqual(quote_day(rules(), '2026-09-06', '2026-09-06', '2026-09-09', 'Percentage', 10)['final_rate'], 81)
        self.assertEqual(quote_day(rules(), '2026-09-06', '2026-09-06', '2026-09-09', complimentary=True)['final_rate'], 0)

    def test_invalid_manual_discount_and_dates(self):
        for kind, value in [('Amount', -1), ('Percentage', 101)]:
            with self.assertRaises(ValueError): quote_day(rules(), '2026-09-06', discount_type=kind, discount_value=value)
        for end in ['2026-09-06', '2026-09-05']:
            with self.assertRaises(ValueError): quote_stay(rules(), '2026-09-06', end)

    def test_full_los_and_zero_rate(self):
        r = rules(); r['los_discounts'] = [dict(min_nights=1, discount_percent=100)]
        self.assertEqual(quote_stay(r, '2026-09-06', '2026-09-09')['total'], 0)
        r['seasons'][0]['weekday_rate'] = 0
        self.assertEqual(quote_day(r, '2026-09-06')['final_rate'], 0)


class Row(dict):
    def __getattr__(self, key): return self.get(key)
    def __setattr__(self, key, value): self[key] = value


class Doc(Row):
    def insert(self, **kw):
        self.name = self.name or f'T{len(self.env.rows) + 1}'
        self.setdefault('is_void', 0)
        self.setdefault('docstatus', 0)
        self.env.rows.append(self)
        self.env.docs[(self.doctype, self.name)] = self
        return self
    def precision(self, field): return 2
    def is_new(self): return False
    def get_doc_before_save(self): return self.get('_old')
    def check_permission(self, *args): pass
    def save(self, **kw): return self
    def add_comment(self, *args): pass


def matches(row, filters):
    for key, value in filters.items():
        actual = row.get(key)
        if isinstance(value, list):
            op, operand = value
            if op == 'is' and bool(actual) != (operand == 'set'): return False
            if op == '!=' and actual == operand: return False
            if op == 'in' and actual not in operand: return False
        elif actual != value:
            return False
    return True


class Environment:
    def __init__(self):
        self.rows = []; self.docs = {}; self.saved = {}
        self.f = types.ModuleType('frappe'); self.u = types.ModuleType('frappe.utils')
        self.f.db = self; self.f.get_doc = self.get_doc; self.f.get_all = self.get_all
        self.f._ = lambda s: s
        self.f.throw = self.throw; self.f.ValidationError = ValueError
        self.f.get_single = lambda dt: self.docs[(dt, None)]
        self.f.whitelist = lambda **kw: lambda fn: fn
        self.f.validate_and_sanitize_search_inputs = lambda fn: fn
        self.f.msgprint = lambda *a, **kw: None
        self.f.log_error = lambda *a, **kw: None
        self.u.flt = lambda v, p=None: round(float(v or 0), p) if p is not None else float(v or 0)
        self.u.cint = lambda v: int(v or 0)
        self.u.getdate = lambda v: v if isinstance(v, date) else date.fromisoformat(str(v)[:10])
        self.u.nowdate = lambda: '2026-09-06'
        self.u.now_datetime = lambda: datetime(2026, 9, 6, 10)
        self.u.add_days = lambda v, n: str(self.u.getdate(v) + timedelta(days=n))
        self.u.date_diff = lambda a, b: (self.u.getdate(a) - self.u.getdate(b)).days
        self.f.utils = self.u
    def throw(self, message, *a): raise ValueError(message)
    def get_doc(self, dt, name=None, **kw):
        if isinstance(dt, dict): return Doc(dt, env=self, flags=Row())
        return self.docs[(dt, name)]
    def get_all(self, dt, filters=None, **kw):
        return [r for r in self.rows if r.get('doctype') == dt and matches(r, filters or {})]
    def get_value(self, dt, name, field, **kw):
        if dt == 'Account': return 'Hotel Co'
        if dt == 'Guest': return 'Customer'
        if dt == 'Item': return 'Accommodation'
        doc = self.docs.get((dt, name), {})
        return Row({k: doc.get(k) for k in field}) if isinstance(field, list) else doc.get(field)
    def exists(self, dt, filters): return bool(self.get_all(dt, filters)) if isinstance(filters, dict) else True
    def sql(self, sql, args=None, **kw):
        if 'pricing_origin=%s' in sql:
            return [r for r in self.rows if r.get('pricing_origin') == args and not r.get('is_void') and not r.get('mirror_source')]
        if 'FROM `tabGL Entry`' in sql:
            return [r for r in self.rows if r.get('doctype') == 'GL Entry' and r.get('voucher_detail_no') == args[1]]
        return []
    def savepoint(self, name): self.saved[name] = len(self.rows)
    def rollback(self, save_point): del self.rows[self.saved[save_point]:]


class IntegrationTests(unittest.TestCase):
    def setUp(self):
        self.env = Environment()
        self.patch = patch.dict(sys.modules, {'frappe': self.env.f, 'frappe.utils': self.env.u})
        self.patch.start(); self.addCleanup(self.patch.stop)
        self.rate = self.load('api/rate_plan.py')
        self.night = self.load_functions('api/night_audit.py', ['process_single_reservation', 'handle_overstay'])
        self.night.ensure_item_exists = lambda *a: None
        self.night.already_charged_today = lambda folio, day, room: any(
            r.get('parent') == folio and r.get('item') == 'ROOM-RENT' and r.get('posting_date') == str(day)
            and not r.get('is_void') for r in self.env.rows)
        self.aliases = patch.dict(sys.modules, {
            'hospitality_core.hospitality_core.api.night_audit': self.night,
            'hospitality_core.hospitality_core.api.rate_plan': self.rate})
        self.aliases.start(); self.addCleanup(self.aliases.stop)
        self.res = Doc(name='R', room='101', room_type='Standard', rate_plan='P', rate_snapshot=json.dumps(rules()),
            arrival_date='2026-09-06', departure_date='2026-09-08', discount_type='Amount', discount_value=0,
            folio='F', is_company_guest=0, status='Checked In')
        self.env.docs[('Hotel Reservation', 'R')] = self.res
        self.env.docs[('Guest Folio', 'F')] = Doc(name='F', status='Open', guest='G')
    def load(self, rel):
        spec = importlib.util.spec_from_file_location('test_' + Path(rel).stem, CORE / rel)
        module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
        return module
    def load_functions(self, rel, names):
        tree = ast.parse((CORE / rel).read_text(encoding='utf-8'))
        module = types.ModuleType('test_functions')
        module.__dict__.update(frappe=self.env.f, **vars(self.env.u), _=lambda s: s)
        nodes = [n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name in names]
        exec(compile(ast.Module(body=nodes, type_ignores=[]), str(CORE / rel), 'exec'), module.__dict__)
        return module
    def net(self): return sum(r.get('amount', 0) for r in self.env.rows if r.get('doctype') == 'Folio Transaction')

    def test_extend_and_shorten_add_adjustments_without_rewriting(self):
        self.rate.post_daily_charge(self.res, '2026-09-06')
        self.rate.post_daily_charge(self.res, '2026-09-07')
        original = [(r.name, r.amount) for r in self.env.rows]
        self.res.departure_date = '2026-09-09'
        self.rate.reconcile_los(self.res)
        self.rate.post_daily_charge(self.res, '2026-09-08')
        self.assertEqual(self.net(), 270)
        self.assertEqual([(r.name, r.amount) for r in self.env.rows[:2]], original)
        count = len(self.env.rows); self.rate.reconcile_los(self.res)
        self.assertEqual(len(self.env.rows), count)
        self.res.departure_date = '2026-09-08'
        self.rate.reconcile_los(self.res)
        self.assertEqual(self.net(), 300)  # Ba đêm đã phát sinh vẫn giữ, chỉ thu hồi LOS.

    def test_duplicate_post_and_full_discount(self):
        self.res.discount_value = 999
        self.assertTrue(self.rate.post_daily_charge(self.res, '2026-09-06'))
        self.assertFalse(self.rate.post_daily_charge(self.res, '2026-09-06'))
        self.assertEqual(self.net(), 0)

    def test_snapshot_ignores_edited_plan(self):
        self.env.docs[('Room Rate Plan', 'P')] = Doc(active=0, room_type='Other')
        self.assertEqual(self.rate.quote_reservation(self.res, '2026-09-06')['base_rate'], 100)

    def test_wrong_type_and_inactive_plan_rejected(self):
        self.env.docs[('Hotel Room Type', 'Standard')] = Doc(default_rate=150)
        self.env.docs[('Room Rate Plan', 'P')] = Doc(active=0, room_type='Standard')
        with self.assertRaises(ValueError): self.rate.snapshot_for('P', 'Standard')
        self.env.docs[('Room Rate Plan', 'P')].update(active=1, room_type='Suite')
        with self.assertRaises(ValueError): self.rate.snapshot_for('P', 'Standard')

    def test_virtual_no_charge(self):
        self.res.room_type = 'Virtual'
        self.assertFalse(self.rate.post_daily_charge(self.res, '2026-09-06'))
        self.assertEqual(self.env.rows, [])

    def test_before_8_charge_date(self):
        self.assertEqual(self.rate.charge_date_for_checkin(datetime(2026, 9, 6, 7)), '2026-09-05')
        self.assertEqual(self.rate.charge_date_for_checkin(datetime(2026, 9, 6, 8)), '2026-09-06')

    def test_night_audit_uses_fresh_reservation_and_extended_departure(self):
        self.res.arrival_date = '2026-09-04'; self.res.departure_date = '2026-09-06'
        result = self.night.process_single_reservation(Row(name='R', departure_date='1999-01-01'), '2026-09-06')
        self.assertEqual(result, (True, True, None))
        self.assertEqual(self.res.departure_date, '2026-09-07')
        self.assertEqual(self.net(), 90)

    def test_posting_failure_rolls_back_partial_rows(self):
        original = self.rate.post_daily_charge
        def fail(res, day):
            original(res, day); raise ValueError('GL failed')
        with patch.object(self.rate, 'post_daily_charge', fail):
            result = self.night.process_single_reservation(self.res, '2026-09-06')
        self.assertFalse(result[0]); self.assertIn('GL failed', result[2]); self.assertEqual(self.env.rows, [])

    def test_surcharge_date_and_exclusion_of_los(self):
        self.res.departure_date = '2026-09-13'
        self.assertEqual(self.rate.quote_reservation(self.res, '2026-09-11', False, False)['base_rate'], 200)
        self.assertEqual(self.rate.quote_reservation(self.res, '2026-09-06')['final_rate'], 80)

    def test_gl_balanced_idempotent_and_discount_reduces_receivable(self):
        accounting = self.load('api/accounting.py')
        self.env.docs[('Hospitality Accounting Settings', None)] = Row(receivable_account='AR',
            income_suspense_account='Suspense', consumption_tax_account='CT', vat_account='VAT',
            service_charge_account='SC', cost_center='CC')
        txn = Doc(name='FT', parent='F', posting_date='2026-09-06', amount=100, item='ROOM-RENT', description='Room', docstatus=0)
        accounting.make_gl_entries_for_folio_transaction(txn)
        count = len(self.env.rows)
        self.assertEqual(round(sum(r.debit - r.credit for r in self.env.rows), 2), 0)
        accounting.make_gl_entries_for_folio_transaction(txn)
        self.assertEqual(len(self.env.rows), count)

        txn = Doc(txn, name='D', amount=-10, item='DISCOUNT')
        accounting.make_gl_entries_for_folio_transaction(txn)
        self.assertEqual(sum(r.debit - r.credit for r in self.env.rows if r.account == 'AR'), 90)
        self.assertEqual(round(sum(r.debit - r.credit for r in self.env.rows), 2), 0)
        count = len(self.env.rows)
        txn.mirror_source = 'D'
        accounting.make_gl_entries_for_folio_transaction(txn)
        self.assertEqual(len(self.env.rows), count)

    def test_client_cannot_replace_saved_snapshot(self):
        self.res._old = Doc(self.res)
        forged = rules(); forged['seasons'][0]['weekday_rate'] = 1
        self.res.rate_snapshot = json.dumps(forged)
        self.rate.prepare_reservation(self.res)
        self.assertEqual(self.rate.quote_reservation(self.res, '2026-09-06')['base_rate'], 100)

    def test_closed_folio_prevents_repricing(self):
        self.rate.post_daily_charge(self.res, '2026-09-06')
        self.res.departure_date = '2026-09-09'
        self.env.docs[('Guest Folio', 'F')].status = 'Closed'
        with self.assertRaises(ValueError): self.rate.reconcile_los(self.res)

    def test_void_covers_discount_and_preserves_amounts(self):
        self.res.departure_date = '2026-09-09'
        self.rate.post_daily_charge(self.res, '2026-09-06')
        original = [r.amount for r in self.env.rows]
        self.rate.void_pricing_charge(self.env.rows[0], 'TEST')
        self.assertTrue(all(r.is_void for r in self.env.rows))
        self.assertEqual([r.amount for r in self.env.rows], original)

    def test_invoiced_discount_prevents_void_of_entire_charge(self):
        self.res.departure_date = '2026-09-09'
        self.rate.post_daily_charge(self.res, '2026-09-06')
        self.env.rows[1].is_invoiced = 1
        with self.assertRaises(ValueError): self.rate.void_pricing_charge(self.env.rows[0], 'TEST')
        self.assertTrue(all(not r.is_void for r in self.env.rows))

    def test_plan_migration_idempotent_and_preserves_existing_seasons(self):
        spec = importlib.util.spec_from_file_location('migration_test', ROOT / 'hospitality_core/migrations/rate_plan_v2.py')
        migration = importlib.util.module_from_spec(spec); spec.loader.exec_module(migration)
        class Plan(Doc):
            def append(self, key, value): self[key].append(Row(value))
        old = Plan(name='OLD', seasons=[])
        existing = Plan(name='NEW', seasons=[Row(season_name='Không thay đổi')])
        self.env.docs[('Room Rate Plan', 'OLD')] = old
        self.env.docs[('Room Rate Plan', 'NEW')] = existing
        self.env.get_table_columns = lambda dt: ['name', 'rate', 'valid_from', 'valid_to']
        self.env.set_value = lambda *a, **kw: None
        original_sql = self.env.sql
        def sql(query, args=None, **kw):
            if 'SELECT name, rate, valid_from' in query:
                return [Row(name=n, rate=250, valid_from='2026-01-01', valid_to='2026-12-31') for n in ['OLD', 'NEW']]
            return original_sql(query, args, **kw)
        self.env.sql = sql
        migration.execute(); migration.execute()
        self.assertEqual(len(old.seasons), 1)
        self.assertEqual((old.seasons[0].weekday_rate, old.seasons[0].weekend_rate), (250, 250))
        self.assertEqual(existing.seasons[0].season_name, 'Không thay đổi')



if __name__ == '__main__':
    unittest.main()
