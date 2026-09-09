"""Chạy riêng trên hospitality-v2.test; dữ liệu mỗi ca rollback."""
import sys
import unittest
import frappe
from frappe.utils import now_datetime, nowdate, add_days
from run_fb_integration import FBTests, get_stock_balance


class CostControlTests(FBTests):
    def setup_control(self):
        self.setup_stock()
        self.operator='fnb.operator@example.test'
        if not frappe.db.exists('User',self.operator):
            frappe.get_doc(dict(doctype='User',email=self.operator,first_name='FNB Test',send_welcome_email=0,
                roles=[dict(role=r) for r in ['System Manager','Stock Manager','Stock User','Sales User','Accounts User']])).insert(ignore_permissions=True)
        account=frappe.db.get_value('Account',{'company':self.company,'root_type':'Expense','is_group':0},'name')
        main=frappe.get_doc(dict(doctype='Warehouse',warehouse_name='FNB Main',company=self.company)).insert()
        transit=frappe.get_doc(dict(doctype='Warehouse',warehouse_name='FNB Transit',company=self.company,warehouse_type='Transit')).insert()
        self.config=frappe.get_doc(dict(doctype='FNB Settings',property=self.reservation.property,
            main_warehouse=main.name,transit_warehouse=transit.name,cost_center=self.settings.cost_center,
            cogs_account=account,staff_account=account,complimentary_account=account,waste_account=account,
            variance_account=account,price_tolerance_percent=1,quantity_tolerance_percent=1,
            cutover_at=add_days(nowdate(),-1)+' 00:00:00')).insert()
        self.out=frappe.get_doc(dict(doctype='FNB Outlet',property=self.reservation.property,outlet_name='Test Kitchen',
            warehouse=self.warehouse,responsible_user=self.operator,enabled=1,
            menu=[dict(item=self.dish.name,stock_mode='Recipe',cost_group='Food'),
                  dict(item=self.raw.name,stock_mode='Stock',cost_group='Food',par_qty=20)])).insert()
        frappe.conf.fnb_release_verified=1
        from hospitality_core.hospitality_core.api.fnb.configuration import activate
        activate(self.config.name)
        frappe.set_user(self.operator)
        self.recipe=frappe.get_doc(dict(doctype='FNB Recipe Version',property=self.reservation.property,outlet=self.out.name,
            item=self.dish.name,quantity=2,uom='FB portion',effective_from=add_days(nowdate(),-1)+' 00:00:00',
            ingredients=[dict(item=self.raw.name,qty=500,uom='FB g')])).insert()
        frappe.set_user('Administrator')
        from hospitality_core.hospitality_core.api.fnb.recipes import approve_recipe
        approve_recipe(self.recipe.name)
        self.recipe.reload()

    def ticket(self,qty=2):
        frappe.set_user(self.operator)
        ticket=frappe.get_doc(dict(doctype='FNB Service Ticket',property=self.reservation.property,outlet=self.out.name,
            posting_datetime=now_datetime(),purpose='Sale',items=[dict(item=self.dish.name,qty=qty,uom='FB portion')])).insert()
        from hospitality_core.hospitality_core.api.fnb.service import send_ticket
        send_ticket(ticket.name)
        frappe.set_user('Administrator')
        ticket.reload()
        return ticket

    def test_prepare_partial_retry_and_pos_allocation(self):
        self.setup_control()
        ticket=self.ticket()
        from hospitality_core.hospitality_core.api.fnb.service import confirm_ticket
        args=dict(name=ticket.name,line=ticket.items[0].name,quantity=2,action='Prepare',request_id='prepare-1')
        event=confirm_ticket(**args)
        self.assertEqual(get_stock_balance(self.raw.name,self.warehouse),9.5)
        self.assertEqual(confirm_ticket(**args),event)
        with self.assertRaises(frappe.ValidationError):
            confirm_ticket(**dict(args,quantity=1))
        confirm_ticket(ticket.name,ticket.items[0].name,2,'Serve','serve-1')
        inv=self.invoice()
        inv.set('items',[inv.items[0]])
        inv.fnb_outlet=self.out.name
        inv.save()
        inv.append('fnb_allocations',dict(ticket=ticket.name,ticket_line=ticket.items[0].name,
            invoice_line=inv.items[0].name,stock_qty=2))
        inv.save()
        inv.submit()
        self.assertEqual(get_stock_balance(self.raw.name,self.warehouse),9.5)
        inv.cancel()
        self.assertEqual(get_stock_balance(self.raw.name,self.warehouse),9.5)
        ticket.reload()
        self.assertEqual(ticket.items[0].billed_qty,0)

    def test_recipe_self_approval_and_overlap(self):
        self.setup_control()
        recipe=frappe.copy_doc(self.recipe)
        recipe.status='Draft'
        recipe.approved_by=None
        recipe.approved_at=None
        recipe.snapshot=None
        recipe.bom=None
        recipe.insert()
        from hospitality_core.hospitality_core.api.fnb.recipes import approve_recipe
        with self.assertRaisesRegex(frappe.ValidationError,'tự duyệt'):
            approve_recipe(recipe.name)
        frappe.set_user(self.operator)
        with self.assertRaisesRegex(frappe.ValidationError,'trùng'):
            approve_recipe(recipe.name)

    def test_staff_stock_partial_service(self):
        self.setup_control()
        frappe.set_user(self.operator)
        ticket=frappe.get_doc(dict(doctype='FNB Service Ticket',property=self.reservation.property,outlet=self.out.name,
            posting_datetime=now_datetime(),purpose='Staff',beneficiary='Bếp ca sáng',
            items=[dict(item=self.raw.name,qty=2,uom='FB kg')])).insert()
        from hospitality_core.hospitality_core.api.fnb.service import send_ticket,confirm_ticket,reserved_stock
        with self.assertRaisesRegex(frappe.ValidationError,'tự duyệt'):
            send_ticket(ticket.name)
        frappe.set_user('Administrator')
        send_ticket(ticket.name)
        self.assertEqual(reserved_stock(self.warehouse,self.raw.name),2)
        event=confirm_ticket(ticket.name,ticket.items[0].name,1,'Prepare','staff-1')
        self.assertEqual(confirm_ticket(ticket.name,ticket.items[0].name,1,'Prepare','staff-1'),event)
        self.assertEqual(get_stock_balance(self.raw.name,self.warehouse),9)
        self.assertEqual(reserved_stock(self.warehouse,self.raw.name),1)
        confirm_ticket(ticket.name,ticket.items[0].name,1,'Prepare','staff-2')
        confirm_ticket(ticket.name,ticket.items[0].name,2,'Serve','staff-serve')
        ticket.reload()
        self.assertEqual(ticket.status,'Reconciled')
        self.assertEqual(get_stock_balance(self.raw.name,self.warehouse),8)
        self.assertEqual(reserved_stock(self.warehouse,self.raw.name),0)

    def test_recipe_import_is_idempotent(self):
        self.setup_control()
        frappe.set_user(self.operator)
        template=frappe.get_doc(dict(doctype='FNB Recipe Version',property=self.reservation.property,is_group_template=1,
            item=self.dish.name,quantity=2,uom='FB portion',effective_from=now_datetime(),
            ingredients=[dict(item=self.raw.name,qty=500,uom='FB g')])).insert()
        frappe.set_user('Administrator')
        from hospitality_core.hospitality_core.api.fnb.recipes import approve_recipe,import_recipe
        approve_recipe(template.name)
        at=add_days(nowdate(),10)+' 00:00:00'
        first=import_recipe('FNB Recipe Version',template.name,self.out.name,at)
        second=import_recipe('FNB Recipe Version',template.name,self.out.name,at)
        self.assertEqual(first,second)
        self.assertEqual(frappe.db.count('FNB Recipe Version',{'template':template.name,'outlet':self.out.name}),1)
        imported=frappe.get_doc('FNB Recipe Version',first)
        self.assertEqual(imported.status,'Draft')
        self.assertAlmostEqual(imported.ingredients[0].stock_qty,0.5,places=6)

    def test_operator_cannot_read_other_property(self):
        self.setup_control()
        user='fnb.scope@example.test'
        frappe.get_doc(dict(doctype='User',email=user,first_name='Scoped FNB',send_welcome_email=0,
            roles=[dict(role=r) for r in ['FNB Operator','Stock User']])).insert(ignore_permissions=True)
        frappe.get_doc(dict(doctype='Hospitality Property Access',user=user,property='HV-B',enabled=1)).insert()
        ticket=self.ticket()
        frappe.set_user(user)
        self.assertFalse(frappe.has_permission('FNB Service Ticket','read',ticket))
        self.assertFalse(frappe.has_permission('Warehouse','read',self.warehouse))
        self.assertNotIn(ticket.name,frappe.get_list('FNB Service Ticket',pluck='name'))
        self.assertNotIn(self.warehouse,frappe.get_list('Warehouse',pluck='name'))
        from hospitality_core.hospitality_core.api.fnb.service import send_ticket
        with self.assertRaises(frappe.PermissionError):
            send_ticket(ticket.name)

    def test_child_recipe_uses_approved_conversion(self):
        self.setup_control()
        child_item=frappe.get_doc(dict(doctype='Item',item_code='FNB-CHILD',item_name='Child recipe',
            item_group='Services',is_stock_item=0,stock_uom='FB portion')).insert()
        frappe.set_user(self.operator)
        child=frappe.get_doc(dict(doctype='FNB Recipe Version',property=self.reservation.property,outlet=self.out.name,
            item=child_item.name,quantity=1,uom='FB portion',effective_from=now_datetime(),
            ingredients=[dict(item=self.raw.name,qty=100,uom='FB g')])).insert()
        frappe.set_user('Administrator')
        from hospitality_core.hospitality_core.api.fnb.recipes import approve_recipe
        approve_recipe(child.name)
        raw=frappe.get_doc('Item',self.raw.name)
        next(r for r in raw.uoms if r.uom=='FB g').conversion_factor=0.002
        raw.save()
        parent_item=frappe.copy_doc(child_item)
        parent_item.item_code='FNB-PARENT';parent_item.item_name='Parent recipe';parent_item.insert()
        frappe.set_user(self.operator)
        parent=frappe.get_doc(dict(doctype='FNB Recipe Version',property=self.reservation.property,outlet=self.out.name,
            item=parent_item.name,quantity=1,uom='FB portion',effective_from=now_datetime(),
            ingredients=[dict(item=child_item.name,qty=1,uom='FB portion',child_recipe=child.name)])).insert()
        frappe.set_user('Administrator')
        approve_recipe(parent.name)
        parent.reload()
        self.assertAlmostEqual(frappe.parse_json(parent.snapshot)['ingredients'][0]['qty'],0.1,places=6)

    def test_stock_reservations_block_unallocated_sale(self):
        self.setup_control()
        ticket=frappe.get_doc(dict(doctype='FNB Service Ticket',property=self.reservation.property,outlet=self.out.name,
            posting_datetime=now_datetime(),purpose='Sale',
            items=[dict(item=self.raw.name,qty=6,uom='FB kg'),dict(item=self.raw.name,qty=6,uom='FB kg')])).insert()
        from hospitality_core.hospitality_core.api.fnb.service import send_ticket
        with self.assertRaisesRegex(frappe.ValidationError,'khả dụng'):
            send_ticket(ticket.name)
        ticket.items[1].qty=3
        ticket.save()
        send_ticket(ticket.name)
        inv=self.invoice()
        inv.set('items',[inv.items[0]])
        inv.items[0].update(dict(item_code=self.raw.name,qty=2,uom='FB kg',stock_uom='FB kg',conversion_factor=1))
        inv.fnb_outlet=self.out.name
        inv.save()
        with self.assertRaisesRegex(frappe.ValidationError,'khả dụng'):
            inv.submit()
        self.assertEqual(get_stock_balance(self.raw.name,self.warehouse),10)

    def test_count_lock_and_two_people(self):
        self.setup_control()
        frappe.set_user(self.operator)
        count=frappe.get_doc(dict(doctype='FNB Stock Count',property=self.reservation.property,outlet=self.out.name,
            warehouse=self.warehouse,posting_datetime=now_datetime(),reason='Kiểm kê test')).insert()
        from hospitality_core.hospitality_core.api.fnb.counts import start_count,record_count,approve_count
        start_count(count.name)
        count.reload()
        with self.assertRaisesRegex(frappe.ValidationError,'kiểm kê'):
            self.stock_entry(1,nowdate())
        values={r.name:9 for r in count.items}
        record_count(count.name,values)
        with self.assertRaises(frappe.ValidationError):
            record_count(count.name,values,recount=True)
        frappe.set_user('Administrator')
        record_count(count.name,values,recount=True)
        approve_count(count.name,'count-1')
        self.assertEqual(get_stock_balance(self.raw.name,self.warehouse),9)
        self.assertFalse(frappe.db.get_value('FNB Warehouse Control',self.warehouse,'active_count'))

    def test_production_and_prepared_waste(self):
        self.setup_control()
        sauce=frappe.get_doc(dict(doctype='Item',item_code='FNB-SAUCE',item_name='Sauce',item_group='Services',
            stock_uom='FB kg',is_stock_item=1)).insert()
        frappe.set_user(self.operator)
        recipe=frappe.get_doc(dict(doctype='FNB Recipe Version',property=self.reservation.property,outlet=self.out.name,
            item=sauce.name,quantity=2,uom='FB kg',effective_from=add_days(nowdate(),-1)+' 00:00:00',
            ingredients=[dict(item=self.raw.name,qty=3,uom='FB kg')])).insert()
        from hospitality_core.hospitality_core.api.fnb.recipes import approve_recipe
        frappe.set_user('Administrator')
        approve_recipe(recipe.name)
        frappe.set_user(self.operator)
        batch=frappe.get_doc(dict(doctype='FNB Production Batch',property=self.reservation.property,outlet=self.out.name,
            posting_datetime=now_datetime(),recipe=recipe.name,output_qty=2,
            items=[dict(item=self.raw.name,qty=3,uom='FB kg')])).insert()
        frappe.set_user('Administrator')
        from hospitality_core.hospitality_core.api.fnb.service import produce,confirm_ticket,approve_waste
        produce(batch.name,'produce-1')
        self.assertEqual(get_stock_balance(self.raw.name,self.warehouse),7)
        self.assertEqual(get_stock_balance(sauce.name,self.warehouse),2)
        ticket=self.ticket()
        event=confirm_ticket(ticket.name,ticket.items[0].name,2,'Prepare','prep')
        self.assertEqual(get_stock_balance(self.raw.name,self.warehouse),6.5)
        frappe.set_user(self.operator)
        waste=frappe.get_doc(dict(doctype='FNB Waste Record',property=self.reservation.property,outlet=self.out.name,
            posting_datetime=now_datetime(),disposition='Prepared Waste',source_event=event,reason='Khách hủy sau chế biến',
            items=[dict(item=self.dish.name,qty=1,uom='FB portion')])).insert()
        frappe.set_user('Administrator')
        approve_waste(waste.name,'waste')
        self.assertEqual(get_stock_balance(self.raw.name,self.warehouse),6.5)
        from hospitality_core.hospitality_core.api.fnb.reports import cost_summary
        summary=cost_summary(self.reservation.property,nowdate(),nowdate())
        self.assertAlmostEqual(summary['categories']['Waste']['cost'],25000,places=2)
        self.assertAlmostEqual(summary['categories']['Sale']['cost'],25000,places=2)
        self.assertAlmostEqual(summary['cost'],50000,places=2)

    def test_session_issue_return_limit(self):
        self.setup_control()
        frappe.set_user(self.operator)
        session=frappe.get_doc(dict(doctype='FNB Service Session',property=self.reservation.property,outlet=self.out.name,
            posting_datetime=now_datetime(),service_type='Buffet',expected_covers=10,budget=1000000,
            menu=[dict(item=self.dish.name,qty=1,uom='FB portion')])).insert()
        frappe.set_user('Administrator')
        from hospitality_core.hospitality_core.api.fnb.service import session_action,approve_waste
        session_action(session.name,'Approve','approve')
        event=session_action(session.name,'Issue','issue',items=[dict(item=self.raw.name,qty=2,uom='FB kg')])
        self.assertEqual(get_stock_balance(self.raw.name,self.warehouse),8)
        frappe.set_user(self.operator)
        returned=frappe.get_doc(dict(doctype='FNB Waste Record',property=self.reservation.property,outlet=self.out.name,
            posting_datetime=now_datetime(),disposition='Physical Return',source_event=event,reason='Hàng chưa dùng',
            items=[dict(item=self.raw.name,qty=1,uom='FB kg')])).insert()
        frappe.set_user('Administrator')
        approve_waste(returned.name,'return')
        self.assertEqual(get_stock_balance(self.raw.name,self.warehouse),9)
        self.assertEqual(approve_waste(returned.name,'return'),frappe.db.get_value('FNB Inventory Event',
            {'source_doctype':'FNB Waste Record','source_name':returned.name},'name'))
        frappe.set_user(self.operator)
        too_many=frappe.copy_doc(returned)
        too_many.status='Draft'; too_many.approved_by=None; too_many.approved_at=None; too_many.stock_entry=None
        too_many.items[0].qty=2
        too_many.insert()
        frappe.set_user('Administrator')
        with self.assertRaisesRegex(frappe.ValidationError,'vượt'):
            approve_waste(too_many.name,'excess')
        self.assertEqual(get_stock_balance(self.raw.name,self.warehouse),9)
        session_action(session.name,'Close','close',actual_covers=10)
        from hospitality_core.hospitality_core.api.fnb.reports import session_cost,cost_summary
        costs=session_cost(session.name)
        self.assertAlmostEqual(costs['actual_cost'],100000,places=2)
        self.assertAlmostEqual(costs['cost_per_cover'],10000,places=2)
        self.assertAlmostEqual(costs['ingredients'][0]['theoretical'],2.5,places=4)
        self.assertAlmostEqual(costs['ingredients'][0]['actual'],1,places=4)
        summary=cost_summary(self.reservation.property,nowdate(),nowdate())
        self.assertAlmostEqual(summary['categories']['Buffet']['cost'],100000,places=2)

    def test_material_request_approval_hash(self):
        self.setup_control()
        from hospitality_core.hospitality_core.api.fnb.procurement import create_request,approve_native
        frappe.set_user(self.operator)
        name=create_request(self.out.name,[dict(item=self.raw.name,qty=2,uom='FB kg')],nowdate(),'Cấp bếp','request-1')
        self.assertEqual(create_request(self.out.name,[dict(item=self.raw.name,qty=2,uom='FB kg')],nowdate(),'Cấp bếp','request-1'),name)
        request=frappe.get_doc('Material Request',name)
        with self.assertRaisesRegex(frappe.ValidationError,'duyệt'):
            request.submit()
        frappe.set_user('Administrator')
        approve_native('Material Request',name)
        request.reload()
        request.submit()
        self.assertEqual(request.docstatus,1)

    def test_transfer_partial_receive(self):
        self.setup_control()
        from erpnext.stock.doctype.stock_entry.stock_entry_utils import make_stock_entry
        # Tồn đầu kho tổng của fixture, không qua giao diện vận hành.
        seed=make_stock_entry(item_code=self.raw.name,qty=5,to_warehouse=self.config.main_warehouse,
            company=self.company,basic_rate=100000,do_not_submit=True)
        seed.flags.fnb_service=True
        seed.submit()
        from hospitality_core.hospitality_core.api.fnb.procurement import create_request,approve_native,dispatch_request,receive_transfer
        frappe.set_user(self.operator)
        name=create_request(self.out.name,[dict(item=self.raw.name,qty=3,uom='FB kg')],nowdate(),'Cấp hàng','request-1')
        frappe.set_user('Administrator')
        approve_native('Material Request',name)
        request=frappe.get_doc('Material Request',name)
        request.submit()
        event=dispatch_request(name,{request.items[0].name:3},'dispatch')
        entry=frappe.get_doc('Stock Entry',frappe.db.get_value('FNB Inventory Event',event,'stock_entry'))
        self.assertEqual(get_stock_balance(self.raw.name,self.config.transit_warehouse),3)
        frappe.set_user(self.operator)
        event=receive_transfer(entry.name,{entry.items[0].name:1},'receive-1')
        self.assertEqual(get_stock_balance(self.raw.name,self.config.transit_warehouse),2)
        self.assertEqual(get_stock_balance(self.raw.name,self.warehouse),11)
        self.assertEqual(receive_transfer(entry.name,{entry.items[0].name:1},'receive-1'),event)

    def test_batch_count(self):
        self.setup_control()
        frappe.db.set_single_value('Stock Settings','enable_serial_and_batch_no_for_item',1)
        frappe.clear_document_cache('Stock Settings','Stock Settings')
        item=frappe.get_doc(dict(doctype='Item',item_code='FNB-BATCHED',item_name='Batch test',item_group='Services',
            stock_uom='FB kg',is_stock_item=1,has_batch_no=1,create_new_batch=0)).insert()
        batch=frappe.get_doc(dict(doctype='Batch',batch_id='FNB-LOT-TEST',item=item.name,expiry_date=add_days(nowdate(),10))).insert()
        from erpnext.stock.doctype.stock_entry.stock_entry_utils import make_stock_entry
        seed=make_stock_entry(item_code=item.name,qty=5,to_warehouse=self.warehouse,company=self.company,
            basic_rate=100000,batch_no=batch.name,use_serial_batch_fields=1,do_not_submit=True)
        seed.flags.fnb_service=True
        seed.submit()
        frappe.set_user(self.operator)
        count=frappe.get_doc(dict(doctype='FNB Stock Count',property=self.reservation.property,outlet=self.out.name,
            warehouse=self.warehouse,posting_datetime=now_datetime(),reason='Chênh lệch theo lô')).insert()
        from hospitality_core.hospitality_core.api.fnb.counts import start_count,record_count,approve_count
        start_count(count.name)
        count.reload()
        batched=[r for r in count.items if r.item==item.name]
        self.assertEqual(len(batched),1)
        self.assertEqual(batched[0].batch_no,batch.name)
        values={r.name:(4 if r.item==item.name else 10) for r in count.items}
        record_count(count.name,values)
        frappe.set_user('Administrator')
        record_count(count.name,values,recount=True)
        approve_count(count.name,'batch-count')
        self.assertEqual(get_stock_balance(item.name,self.warehouse),4)

    def test_transfer_purchase_uom_partial_receive(self):
        self.setup_control()
        from erpnext.stock.doctype.stock_entry.stock_entry_utils import make_stock_entry
        seed=make_stock_entry(item_code=self.raw.name,qty=1,to_warehouse=self.config.main_warehouse,
            company=self.company,basic_rate=100000,do_not_submit=True)
        seed.flags.fnb_service=True;seed.submit()
        from hospitality_core.hospitality_core.api.fnb.procurement import create_request,approve_native,dispatch_request,receive_transfer,pending_transfer
        frappe.set_user(self.operator)
        name=create_request(self.out.name,[dict(item=self.raw.name,qty=500,uom='FB g')],nowdate(),'Cấp gram','gram-request')
        frappe.set_user('Administrator')
        approve_native('Material Request',name)
        request=frappe.get_doc('Material Request',name);request.submit()
        event=dispatch_request(name,{request.items[0].name:500},'gram-dispatch')
        entry=frappe.get_doc('Stock Entry',frappe.db.get_value('FNB Inventory Event',event,'stock_entry'))
        self.assertEqual(entry.items[0].uom,'FB kg')
        self.assertAlmostEqual(entry.items[0].qty,0.5,places=6)
        frappe.set_user(self.operator)
        receive_transfer(entry.name,{entry.items[0].name:0.2},'gram-receive')
        self.assertAlmostEqual(get_stock_balance(self.raw.name,self.config.transit_warehouse),0.3,places=6)
        remaining=pending_transfer('Stock Entry',entry.name)
        self.assertAlmostEqual(remaining['rows'][0]['remaining'],0.3,places=6)

    def test_physical_return_requires_approval(self):
        self.setup_control()
        inv=self.invoice()
        inv.set('items',[inv.items[0]])
        inv.items[0].update(dict(item_code=self.raw.name,qty=2,uom='FB kg',stock_uom='FB kg',conversion_factor=1))
        inv.fnb_outlet=self.out.name
        inv.save(); inv.submit()
        self.assertEqual(get_stock_balance(self.raw.name,self.warehouse),8)
        from erpnext.accounts.doctype.sales_invoice.sales_invoice import make_sales_return
        returned=make_sales_return(inv.name)
        returned.fnb_return_disposition='Physical Return'
        frappe.set_user(self.operator)
        returned.insert()
        with self.assertRaisesRegex(frappe.ValidationError,'duyệt'):
            returned.submit()
        frappe.set_user('Administrator')
        from hospitality_core.hospitality_core.api.fnb.procurement import approve_native
        approve_native('Sales Invoice',returned.name)
        returned.reload(); returned.submit()
        self.assertEqual(get_stock_balance(self.raw.name,self.warehouse),10)

    def test_native_pos_issues_once_with_native_tax(self):
        self.setup_control()
        frappe.db.set_single_value('POS Settings','invoice_type','POS Invoice')
        # Idempotent: 'Walk in Customer' la ten CU THE ma pos_bridge.py's
        # enforce_payment_mode_rules() nhan dien rieng (payment-mode rule cho
        # khach khong gan phong) — cac file test KHAC (run_docker_verification.py,
        # run_concurrency_tests.py) cung tao ban ghi nay tren CUNG site
        # 'localhost' dung chung, khong rollback duoc neu file do da thuc su
        # commit that (VD qua POS Invoice submit). Truoc day insert() vo dieu
        # kien o day se tao ban ghi TRUNG TEN, bi Frappe tu doi thanh "Walk in
        # Customer - 1" — mot customer KHONG duoc enforce_payment_mode_rules()
        # nhan dien dung, lam sai ca test. Dung lai ban ghi da co neu ton tai.
        if frappe.db.exists('Customer','Walk in Customer'):
            customer=frappe.get_doc('Customer','Walk in Customer')
        else:
            customer=frappe.copy_doc(frappe.get_doc('Customer',self.reservation.billing_customer))
            customer.customer_name='Walk in Customer'
            customer.insert()
        cash=frappe.db.get_value('Account',{'company':self.company,'account_type':'Cash','is_group':0},'name')
        mode=frappe.get_doc(dict(doctype='Mode of Payment',mode_of_payment='FNB Cash Test',type='Cash',
            accounts=[dict(company=self.company,default_account=cash)])).insert()
        profile=frappe.get_doc(dict(doctype='POS Profile',name='FNB Test POS',company=self.company,currency='VND',
            warehouse=self.warehouse,hospitality_property=self.reservation.property,selling_price_list='Integration Selling',
            income_account=self.settings.income_account,expense_account=self.config.cogs_account,cost_center=self.settings.cost_center,
            write_off_account=self.config.cogs_account,write_off_cost_center=self.settings.cost_center,
            taxes_and_charges=self.settings.tax_template,payments=[dict(mode_of_payment=mode.name,default=1)])).insert()
        from hospitality_core.hospitality_core.api.fnb.common import save
        self.out.reload()
        self.out.append('pos_profiles',dict(pos_profile=profile.name))
        save(self.out)
        opening=frappe.get_doc(dict(doctype='POS Opening Entry',company=self.company,pos_profile=profile.name,
            user='Administrator',period_start_date=nowdate()+' 00:00:00',posting_date=nowdate(),
            balance_details=[dict(mode_of_payment=mode.name,opening_amount=0)])).insert()
        opening.submit()
        inv=frappe.get_doc(dict(doctype='POS Invoice',company=self.company,customer=customer.name,pos_profile=profile.name,
            currency='VND',conversion_rate=1,selling_price_list='Integration Selling',posting_date=nowdate(),
            taxes_and_charges=self.settings.tax_template,items=[dict(item_code=self.raw.name,qty=1,rate=100000,
                warehouse=self.warehouse,income_account=self.settings.income_account,cost_center=self.settings.cost_center)],
            payments=[dict(mode_of_payment=mode.name,account=cash,amount=100000)])).insert()
        inv.payments[0].amount=inv.grand_total
        inv.save(); inv.submit()
        self.assertEqual(get_stock_balance(self.raw.name,self.warehouse),9)
        self.assertEqual(inv.fnb_version,'FNB v1')
        from hospitality_core.api.composite_item_utils import process_composite_items_in_invoice
        process_composite_items_in_invoice(inv)
        self.assertEqual(get_stock_balance(self.raw.name,self.warehouse),9)
        self.assertEqual(frappe.db.count('GL Entry',{'voucher_type':'POS Invoice','voucher_no':inv.name}),0)
        self.assertEqual(frappe.db.count('FNB Inventory Event',{'source_doctype':'POS Invoice','source_name':inv.name,'event_type':'Issue'}),1)
        merge=frappe.get_doc(dict(doctype='POS Invoice Merge Log',company=self.company,customer=customer.name,
            posting_date=nowdate(),posting_time=inv.posting_time,merge_invoices_based_on='Customer',
            pos_invoices=[dict(pos_invoice=inv.name,customer=customer.name,grand_total=inv.grand_total,
                posting_date=inv.posting_date,is_return=0)])).insert()
        merge.submit()
        consolidated=frappe.get_doc('Sales Invoice',merge.consolidated_invoice)
        self.assertEqual(consolidated.docstatus,1)
        self.assertEqual(consolidated.fnb_version,'FNB v1')
        self.assertEqual(consolidated.update_stock,0)
        self.assertEqual(get_stock_balance(self.raw.name,self.warehouse),9)
        self.assertEqual(frappe.db.count('Stock Ledger Entry',{'voucher_type':'Sales Invoice','voucher_no':consolidated.name}),0)
        gl=frappe.db.sql('''SELECT SUM(credit-debit) FROM `tabGL Entry`
            WHERE voucher_type='Sales Invoice' AND voucher_no=%s AND account=%s AND is_cancelled=0''',
            (consolidated.name,self.settings.income_account))[0][0]
        self.assertAlmostEqual(float(gl),float(inv.base_net_total),places=2)


if __name__=='__main__':
    names=[name for name in CostControlTests.__dict__ if name.startswith('test_')]
    if len(sys.argv)>1:
        names=sys.argv[1:]
    try:
        result=unittest.TextTestRunner(verbosity=2).run(unittest.TestSuite(CostControlTests(n) for n in names))
        raise SystemExit(0 if result.wasSuccessful() else 1)
    finally:
        frappe.db.rollback()
        frappe.destroy()
