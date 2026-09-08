frappe.pages['fnb-control'].on_page_load = function(wrapper) {
    const page=frappe.ui.make_app_page({parent:wrapper,title:__('F&B Cost Control'),single_column:true});
    const escape=frappe.utils.escape_html;
    let version=0;
    let ready=false;
    const body=$('<div class="fnb-control-body"></div>').appendTo(page.body);
    const property=page.add_field({fieldname:'property',label:__('Cơ sở'),fieldtype:'Link',options:'Hospitality Property',reqd:1,
        change:()=>{if (ready) {outlet.set_value(''); render();}}});
    const outlet=page.add_field({fieldname:'outlet',label:__('Outlet'),fieldtype:'Link',options:'FNB Outlet',
        get_query:()=>({filters:{property:property.get_value()}}),change:render});
    page.add_inner_button(__('Phiếu phục vụ mới'),()=>frappe.new_doc('FNB Service Ticket',{property:property.get_value(),outlet:outlet.get_value()}));
    page.add_inner_button(__('Cấu hình'),()=>frappe.set_route('List','FNB Settings'));
    page.add_inner_button(__('Công thức'),()=>frappe.set_route('List','FNB Recipe Version'));
    page.add_inner_button(__('Lập nhu cầu hàng'),()=>{
        const selected=property.get_value(),selectedOutlet=outlet.get_value(),request=version;
        if (!selected || !selectedOutlet) return frappe.msgprint(__('Chọn cơ sở và outlet trước khi lập nhu cầu.'));
        frappe.prompt([{fieldname:'session',label:__('Phiên buffet/tiệc (nếu có)'),fieldtype:'Link',options:'FNB Service Session',
            get_query:()=>({filters:{property:selected,outlet:selectedOutlet,status:['in',['Draft','Approved']]}})}],selection=>{
            frappe.call({method:'hospitality_core.hospitality_core.api.fnb.procurement.suggest_request',
                args:{outlet_name:selectedOutlet,session:selection.session},callback:r=>{
                    if (request!==version) return;
                    const rows=r.message;
                    if (!rows.length) return frappe.msgprint(__('Chưa có định mức tồn hoặc thực đơn để tính nhu cầu.'));
                    const items=rows.map(row=>({...row,qty:row.required_qty}));
                    frappe.prompt([
                        {fieldname:'required_date',fieldtype:'Date',label:__('Ngày cần hàng'),reqd:1,default:frappe.datetime.get_today()},
                        {fieldname:'request_type',fieldtype:'Select',label:__('Loại yêu cầu'),options:['Material Transfer','Purchase'],reqd:1},
                        {fieldname:'purpose',fieldtype:'Small Text',label:__('Mục đích'),reqd:1},
                        {fieldname:'items',fieldtype:'Table',label:__('Xác nhận lượng cần; mua hàng nhận vào kho tổng'),data:items,reqd:1,
                            fields:[{fieldname:'item',fieldtype:'Link',options:'Item',label:__('Item'),in_list_view:1,read_only:1},
                                {fieldname:'uom',fieldtype:'Link',options:'UOM',label:__('UOM'),in_list_view:1,read_only:1},
                                {fieldname:'available',fieldtype:'Float',label:__('Khả dụng bếp'),in_list_view:1,read_only:1},
                                {fieldname:'main_available',fieldtype:'Float',label:__('Tồn kho tổng'),in_list_view:1,read_only:1},
                                {fieldname:'qty',fieldtype:'Float',label:__('Yêu cầu'),in_list_view:1,reqd:1}]}
                    ],values=>{
                        if (request!==version) return frappe.msgprint(__('Cơ sở/outlet đã thay đổi; tính lại nhu cầu.'));
                        const selectedItems=values.items.filter(row=>row.qty>0).map(({item,qty,uom})=>({item,qty,uom}));
                        if (!selectedItems.length) return frappe.msgprint(__('Cần ít nhất một dòng có lượng dương.'));
                        frappe.call({method:'hospitality_core.hospitality_core.api.fnb.procurement.create_request',type:'POST',freeze:true,
                            args:{outlet_name:selectedOutlet,...values,items:selectedItems,request_id:window.crypto.randomUUID()},
                            callback:result=>{if (request===version) frappe.set_route('Form','Material Request',result.message);}});
                    },__('Yêu cầu hàng F&B'));
                }});
        },__('Nhu cầu theo định mức và kế hoạch phục vụ'));
    });
    function render() {
        if (!ready) return;
        const request=++version;
        const selected=property.get_value();
        body.empty();
        if (!selected) return body.text(__('Chọn cơ sở để xem công việc cần xử lý.'));
        frappe.call({method:'hospitality_core.hospitality_core.api.fnb.reports.dashboard',
            args:{property:selected,outlet:outlet.get_value()},callback:r=>{
                if (request!==version) return;
                const data=r.message;
                body.empty();
                for (const queue of data.queues) {
                    const section=$('<section class="mb-4"></section>').appendTo(body);
                    $('<h4></h4>').text(__(queue.doctype)).appendTo(section);
                    if (!queue.rows.length) $('<p class="text-muted"></p>').text(__('Không có hồ sơ chờ xử lý.')).appendTo(section);
                    for (const row of queue.rows) {
                        const link=$('<a class="list-row"></a>').appendTo(section);
                        link.text(`${row.name} · ${__(row.status)} · ${row.outlet || ''}`);
                        link.on('click',()=>frappe.set_route('Form',queue.doctype,row.name));
                    }
                }
                if (data.can_view_cost) $('<button class="btn btn-default"></button>').text(__('Xem chi phí theo kỳ')).appendTo(body).on('click',()=>{
                    frappe.prompt([{fieldname:'from_date',label:__('Từ ngày'),fieldtype:'Date',reqd:1},
                        {fieldname:'to_date',label:__('Đến ngày'),fieldtype:'Date',reqd:1}],values=>{
                        frappe.call({method:'hospitality_core.hospitality_core.api.fnb.reports.cost_summary',
                            args:{property:selected,outlet:outlet.get_value(),...values},callback:result=>{
                                if (request!==version) return;
                                const s=result.message;
                                frappe.msgprint({title:__('Chi phí F&B tạm tính'),message:
                                    `${__('Doanh thu thuần')}: ${format_currency(s.revenue,s.currency)}<br>`+
                                    `${__('Chi phí bán hàng')}: ${format_currency(s.selling_cost,s.currency)}<br>`+
                                    `${__('Tổng chi phí đã ghi')}: ${format_currency(s.cost,s.currency)}<br>${escape(s.notice)}`});
                            }});
                    },__('Kỳ báo cáo'));
                });
            }});
    }
    ready=true;
    render();
};
