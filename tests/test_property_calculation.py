import importlib.util
from pathlib import Path
import unittest
import ast
import json
from datetime import datetime, timedelta
from types import SimpleNamespace

ROOT=Path(__file__).resolve().parents[1]/'hospitality_core/hospitality_core/api'


def load(name):
    spec=importlib.util.spec_from_file_location(name,ROOT/(name+'.py'))
    module=importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


pricing=load('rate_calculation')
loyalty=load('loyalty_calculation')


class PropertyCalculationTests(unittest.TestCase):
    def test_v2_never_posts_through_legacy_gl_hooks(self):
        for filename, function, marker, args in [
            ('accounting.py','make_gl_entries_for_folio_transaction','accounting_version',()),
            ('accounting.py','handle_payment_income_realization','hospitality_accounting_version',('F',100)),
            ('payment_bridge.py','process_payment_entry','hospitality_accounting_version',())]:
            tree=ast.parse((ROOT/filename).read_text(encoding='utf-8'))
            func=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name==function)
            ctx={}
            exec(compile(ast.Module(body=[func],type_ignores=[]),filename,'exec'),ctx)
            # Không cấp database: bất kỳ đường ghi legacy nào cũng khiến test thất bại.
            self.assertIsNone(ctx[function]({marker:'Property v2'},*args))

    def test_non_finite_money_is_rejected(self):
        for value in ['NaN','Infinity','-Infinity']:
            with self.assertRaises(ValueError):
                pricing.money(value)
            with self.assertRaises(ValueError):
                pricing.discount_breakdown(100,[],1,discount_type='Amount',discount_value=value)

    def test_read_balance_excludes_expired_points_before_cron(self):
        source=ast.parse((ROOT/'guest_loyalty.py').read_text(encoding='utf-8'))
        nodes=[n for n in source.body if isinstance(n,ast.FunctionDef) and n.name in ('balances','_lot_remaining')]
        context={'json':json,'get_datetime':lambda x:x,'now_datetime':datetime.now}
        exec(compile(ast.Module(body=nodes,type_ignores=[]),'guest_loyalty.py','exec'),context)
        at=datetime(2026,9,7)
        rows=[SimpleNamespace(name='E',event_type='Earn',points=100,expires_at=at-timedelta(seconds=1),source_entry=None),
              SimpleNamespace(name='R',event_type='Redeem',points=-60,source_entry=None,
                evidence=json.dumps({'lots':[{'entry':'E','points':60}]}))]
        self.assertEqual(context['balances'](rows,at)['available'],0)

    def test_refund_cannot_spend_another_hold(self):
        self.assertEqual(loyalty.redemption_capacity(70,100,60),30)

    def test_own_hold_does_not_block_redemption(self):
        self.assertEqual(loyalty.redemption_capacity(100,100,60),60)

    def test_refund_expired_unused_points_does_not_create_debt(self):
        delta,expiry=loyalty.qualification_delta(100,50,0,100,True)
        self.assertEqual((delta,expiry),(-50,50))
        self.assertEqual(100-100+delta+expiry,0)

    def test_refund_spent_points_creates_real_debt(self):
        self.assertEqual(loyalty.qualification_delta(100,50,100,0,True),(-50,0))

    def test_payment_reinstatement_does_not_extend_expiry(self):
        self.assertEqual(loyalty.qualification_delta(50,100,0,50,True),(50,-50))

    def test_discount_order_and_floor(self):
        quote=pricing.discount_breakdown(100,[{'min_nights':3,'discount_percent':10}],3,
            discount_type='Percentage',discount_value=10,vip_percent=20)
        self.assertEqual(quote['final_rate'],64.8)
        self.assertEqual(quote['vip_discount'],18)
        self.assertEqual(pricing.discount_breakdown(100,[],1,discount_type='Amount',discount_value=200,vip_percent=20)['final_rate'],0)

    def test_default_rate_gets_los_then_vip(self):
        # QUYẾT ĐỊNH ĐÃ CHỐT: LOS áp dụng theo TỔNG SỐ ĐÊM, không phụ thuộc
        # mùa vụ — kể cả khi seasons=[] (mọi đêm đều dùng default_rate).
        # nights=4 (01/09 -> 05/09) đủ điều kiện tier min_nights=3 (10%):
        # 100 - 10% = 90 (after_los), rồi VIP 20% trên 90 = 18 -> final 72.
        # Tên test cũ "test_default_excludes_los_but_allows_vip" khẳng định
        # hành vi CŨ (đã bị bác bỏ) — đã đổi tên + sửa kỳ vọng.
        result=pricing.quote_day(dict(default_rate=100,seasons=[],los_discounts=[{'min_nights':3,'discount_percent':10}],
            vip_percent=20,currency='USD'),'2026-09-01','2026-09-01','2026-09-05')
        self.assertEqual(result['final_rate'],72)
        self.assertEqual(result['los_discount'],10)
        self.assertEqual(result['currency'],'USD')


if __name__=='__main__':
    unittest.main()
