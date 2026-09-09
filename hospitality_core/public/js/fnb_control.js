/* Giao diện F&B dùng dialog chuẩn Desk; server kiểm tra quyền và trạng thái. */
(() => {
    const root = 'hospitality_core.hospitality_core.api.fnb.';
    const call = (frm, method, args = {}) => {
        if (frm.is_dirty()) {
            frappe.msgprint(__('Lưu chứng từ trước khi thao tác.'));
            return;
        }
        const name = frm.doc.name;
        const version = frm._fnb_request = (frm._fnb_request || 0) + 1;
        return frappe.call({method: root + method, type: 'POST', args, freeze: true,
            callback: () => {
                if (frm.doc.name === name && version === frm._fnb_request && !frm.is_dirty()) frm.reload_doc();
            }});
    };
    const requestId = () => window.crypto.randomUUID();
    const promptAction = (frm, fields, method, args = {}) => {
        const name = frm.doc.name, modified = frm.doc.modified;
        frappe.prompt(fields, values => {
            if (frm.doc.name !== name || frm.doc.modified !== modified || frm.is_dirty())
                return frappe.msgprint(__('Chứng từ đã thay đổi; mở lại thao tác.'));
            call(frm, method, {name, ...args, ...values});
        });
    };
    const read = (frm,method,args,callback) => {
        if (frm.is_dirty()) return frappe.msgprint(__('Lưu chứng từ trước khi thao tác.'));
        const name=frm.doc.name, version=frm._fnb_request=(frm._fnb_request || 0)+1;
        return frappe.call({method:root+method,args,callback:r=>{
            if (frm.doc.name===name && version===frm._fnb_request && !frm.is_dirty()) callback(r.message);
        }});
    };
    const action = (frm, label, method, args) => frm.add_custom_button(__(label),
        () => call(frm, method, {name: frm.doc.name, ...args}), __('F&B'));
    const propertyQuery = frm => {
        if (frm.fields_dict.outlet) frm.set_query('outlet', () => ({filters: {property: frm.doc.property}}));
        if (frm.fields_dict.warehouse) frm.set_query('warehouse', () => ({filters: {company: frm.doc.operating_company, is_group: 0, disabled: 0}}));
    };
    const doctypes = ['FNB Settings','FNB Outlet','FNB Recipe Version','FNB Cost Standard','FNB Service Ticket',
        'FNB Production Batch','FNB Service Session','FNB Waste Record','FNB Stock Count','FNB Period Close'];
    for (const dt of doctypes) frappe.ui.form.on(dt, {
        setup: propertyQuery,
        property(frm) {
            frm._fnb_request = (frm._fnb_request || 0) + 1;
            if (frm.is_new() && frm.doc.outlet) frm.set_value('outlet', null);
        },
        refresh(frm) {
            propertyQuery(frm);
            if (frm.is_new()) return;
            const d = frm.doc;
            if (dt === 'FNB Settings' && !d.enabled) action(frm,'Kích hoạt sau nghiệm thu','configuration.activate',{property:d.property});
            if (dt === 'FNB Outlet' && !d.enabled) action(frm,'Kích hoạt outlet','configuration.activate_outlet');
            if (['FNB Settings', 'FNB Outlet'].includes(dt) && d.enabled) {
                frm.add_custom_button(__(d.paused ? 'Mở lại F&B' : 'Tạm dừng F&B'), () => promptAction(frm,
                    [{fieldname:'reason',label:__('Lý do'),fieldtype:'Small Text',reqd:1}],
                    'configuration.set_paused', {doctype:dt,paused:d.paused ? 0 : 1}), __('F&B'));
                if (d.paused) frm.add_custom_button(__('Vô hiệu hóa F&B'), () => promptAction(frm,
                    [{fieldname:'reason',label:__('Lý do'),fieldtype:'Small Text',reqd:1}],
                    'configuration.deactivate', {doctype:dt}), __('F&B'));
            }
            if (dt === 'FNB Recipe Version' && d.status === 'Draft') action(frm,'Duyệt công thức','recipes.approve_recipe');
            if (dt === 'FNB Cost Standard' && d.status === 'Draft') action(frm,'Duyệt giá chuẩn','reports.approve_standard');
            if (dt === 'FNB Production Batch' && d.status === 'Draft') action(frm,'Duyệt và ghi mẻ','service.produce',{request_id:requestId()});
            if (dt === 'FNB Waste Record' && d.status === 'Draft') action(frm,'Duyệt xử lý','service.approve_waste',{request_id:requestId()});
            if (dt === 'FNB Period Close' && d.status === 'Draft') action(frm,'Đối soát và chốt kỳ','reports.close_period');
            if (dt === 'FNB Service Ticket') {
                if (d.status === 'Draft') action(frm,'Gửi bếp','service.send_ticket');
                if (['Sent','Prepared','Served'].includes(d.status)) frm.add_custom_button(__('Xác nhận món'), () => {
                    frappe.prompt([
                        {fieldname:'line',label:__('Dòng món'),fieldtype:'Select',options:d.items.map(r=>({label:`${r.idx}. ${r.item} — ${r.uom}`,value:r.name})),reqd:1},
                        {fieldname:'action',label:__('Thao tác'),fieldtype:'Select',options:[{label:__('Đã chế biến'),value:'Prepare'},{label:__('Đã phục vụ'),value:'Serve'},{label:__('Hủy trước chế biến'),value:'Cancel'}],reqd:1},
                        {fieldname:'quantity',label:__('Số lượng theo đơn vị tồn'),fieldtype:'Float',reqd:1}
                    ], values=>{
                        const send = batches=>call(frm,'service.confirm_ticket',{name:d.name,request_id:requestId(),...values,batches});
                        if (values.action !== 'Prepare') return send({});
                        read(frm,'service.preparation_batches',{name:d.name,line:values.line},result=>{
                            const items=result || [];
                            if (!items.length) return send({});
                            frappe.prompt(items.map((item,i)=>({fieldname:`b${i}`,label:__('Lô: {0}',[item]),fieldtype:'Link',
                                options:'Batch',reqd:1,get_query:()=>({filters:{item,disabled:0}})})),
                                selected=>send(Object.fromEntries(items.map((item,i)=>[item,selected[`b${i}`]]))),__('Chọn lô thực dùng'));
                        });
                    },__('Xác nhận món'));
                },__('F&B'));
            }
            if (dt === 'FNB Service Session') {
                if (d.status === 'Draft') action(frm,'Duyệt phiên','service.session_action',{action:'Approve',request_id:requestId()});
                if (d.status === 'Approved') {
                    frm.add_custom_button(__('Cấp hàng vào phục vụ'),()=>{
                        frappe.prompt([{fieldname:'items',label:__('Hàng thực cấp'),fieldtype:'Table',reqd:1,
                            fields:[{fieldname:'item',label:__('Item'),fieldtype:'Link',options:'Item',in_list_view:1,reqd:1},
                                {fieldname:'qty',label:__('Số lượng'),fieldtype:'Float',in_list_view:1,reqd:1},
                                {fieldname:'uom',label:__('UOM'),fieldtype:'Link',options:'UOM',in_list_view:1,reqd:1},
                                {fieldname:'batch_no',label:__('Lô'),fieldtype:'Link',options:'Batch',in_list_view:1}]}],
                            values=>call(frm,'service.session_action',{name:d.name,action:'Issue',items:values.items,request_id:requestId()}),__('Cấp hàng'));
                    },__('F&B'));
                    frm.add_custom_button(__('Đóng phiên'),()=>frappe.prompt([{fieldname:'actual_covers',label:__('Khách thực dùng'),fieldtype:'Int',reqd:1}],
                        values=>call(frm,'service.session_action',{name:d.name,action:'Close',request_id:requestId(),...values})),__('F&B'));
                }
            }
            if (dt === 'FNB Stock Count') {
                if (d.status === 'Draft') action(frm,'Khóa kho và mở đếm','counts.start_count');
                if (d.status === 'Counting') {
                    frm.add_custom_button(__('Khai báo hàng tìm thấy'), () => promptAction(frm, [
                        {fieldname:'item',label:__('Item'),fieldtype:'Link',options:'Item',reqd:1},
                        {fieldname:'batch_no',label:__('Lô'),fieldtype:'Link',options:'Batch'},
                        {fieldname:'reason',label:__('Lý do (cần đếm lại toàn bộ sau khi thêm)'),fieldtype:'Small Text',reqd:1}
                    ], 'counts.add_found_item'), __('F&B'));
                    for (const recount of [false,true]) frm.add_custom_button(__(recount?'Nhập đếm lại':'Nhập số đếm'),()=>{
                        const fields=d.items.map((r,i)=>({fieldname:`r${i}`,label:`${r.item} (${r.uom}) ${r.batch_no || ''}`,fieldtype:'Float',reqd:1}));
                        frappe.prompt(fields,values=>call(frm,'counts.record_count',{name:d.name,recount,
                            values:Object.fromEntries(d.items.map((r,i)=>[r.name,values[`r${i}`]]))}),__('Kiểm kê'));
                    },__('F&B'));
                    frm.add_custom_button(__('Duyệt chênh lệch'), () => {
                        const name=d.name, modified=d.modified;
                        frappe.prompt(d.items.map((r,i)=>({fieldname:`v${i}`,fieldtype:'Float',
                            label:`${r.item} (${r.uom}) ${r.batch_no || ''} — ${__('Giá bản vị nếu hàng tìm thấy chưa có giá sổ')}`})), values=>{
                            if (frm.doc.name!==name || frm.doc.modified!==modified || frm.is_dirty())
                                return frappe.msgprint(__('Chứng từ đã thay đổi; mở lại thao tác.'));
                            call(frm,'counts.approve_count',{name,request_id:requestId(),valuation_rates:
                                Object.fromEntries(d.items.map((r,i)=>[r.name,values[`v${i}`]]).filter(([,v])=>v>0))});
                        });
                    }, __('F&B'));
                    frm.add_custom_button(__('Hủy phiên và mở khóa'),()=>frappe.prompt([{fieldname:'reason',label:__('Lý do'),fieldtype:'Small Text',reqd:1}],
                        values=>call(frm,'counts.abort_count',{name:d.name,...values})),__('F&B'));
                }
            }
        }
    });
    for (const dt of ['Material Request','Purchase Order','Purchase Receipt','Stock Entry','POS Invoice','Sales Invoice']) frappe.ui.form.on(dt,{
        refresh(frm) {
            if (!frm.is_new() && dt!=='Stock Entry' && frm.doc.docstatus === 0 && frm.doc.fnb_outlet &&
                (!['POS Invoice','Sales Invoice'].includes(dt) || (frm.doc.is_return && frm.doc.fnb_return_disposition === 'Physical Return')))
                action(frm,'Duyệt nội dung F&B','procurement.approve_native',{doctype:dt});
            const d=frm.doc;
            const dispatch=dt==='Material Request' && d.material_request_type==='Material Transfer';
            const receive=dt==='Stock Entry' && d.add_to_transit;
            if (d.docstatus===1 && d.fnb_outlet && (dispatch || receive)) frm.add_custom_button(__(dispatch?'Giao qua kho trung chuyển':'Xác nhận nhận hàng'),()=>{
                read(frm,'procurement.pending_transfer',{doctype:dt,name:d.name},result=>{
                    if (!result.rows.length) return frappe.msgprint(__('Đã xử lý hết số lượng.'));
                    const fields=result.rows.map((r,i)=>({fieldname:`r${i}`,fieldtype:'Float',
                        label:`${r.item} (${r.uom}) · ${__('Còn')}: ${r.remaining}`,default:0}));
                    frappe.prompt(fields,values=>{
                        const quantities=Object.fromEntries(result.rows.map((r,i)=>[r.line,values[`r${i}`]]).filter(([,q])=>q>0));
                        if (!Object.keys(quantities).length) return frappe.msgprint(__('Nhập lượng thực giao/nhận.'));
                        call(frm,dispatch?'procurement.dispatch_request':'procurement.receive_transfer',
                            {...(dispatch?{name:d.name}:{stock_entry:d.name}),quantities,request_id:requestId()});
                    },`${result.from_warehouse} → ${result.to_warehouse}`);
                });
            },__('F&B'));
            if (['POS Invoice','Sales Invoice'].includes(dt) && !frm.is_new() && d.docstatus===0 && d.fnb_version==='FNB v1' && !d.is_return && !d.is_consolidated) {
                frm.add_custom_button(__('Liên kết phiếu bếp'),()=>read(frm,'pos.allocation_candidates',{doctype:dt,name:d.name},rows=>{
                    if (!rows.length) return frappe.msgprint(__('Không có món đã phục vụ chưa thanh toán.'));
                    const choices=rows.map((r,i)=>({value:String(i),label:`${r.ticket} · ${r.item} · ${r.table_number || r.room || ''} · ${__('Còn')} ${r.remaining} ${r.uom}`}));
                    frappe.prompt([
                        {fieldname:'source',label:__('Món đã phục vụ'),fieldtype:'Select',options:choices,reqd:1},
                        {fieldname:'target',label:__('Dòng hóa đơn'),fieldtype:'Select',options:d.items.map(r=>({value:r.name,label:`${r.idx}. ${r.item_code}`})),reqd:1},
                        {fieldname:'quantity',label:__('Lượng theo đơn vị tồn'),fieldtype:'Float',reqd:1}
                    ],values=>{
                        if (frm.doc.name!==d.name || frm.is_dirty()) return frappe.msgprint(__('Chứng từ đã thay đổi; mở lại thao tác liên kết.'));
                        const source=rows[Number(values.source)],target=d.items.find(r=>r.name===values.target);
                        if (!source || !target || source.item!==target.item_code || values.quantity<=0 || values.quantity>source.remaining)
                            return frappe.msgprint(__('Món hoặc số lượng phân bổ không hợp lệ.'));
                        frm.add_child('fnb_allocations',{ticket:source.ticket,ticket_line:source.ticket_line,invoice_line:target.name,stock_qty:values.quantity});
                        frm.refresh_field('fnb_allocations');
                        frm.dirty();
                    },__('Phân bổ phiếu bếp'));
                }),__('F&B'));
            }
        }
    });
})();
