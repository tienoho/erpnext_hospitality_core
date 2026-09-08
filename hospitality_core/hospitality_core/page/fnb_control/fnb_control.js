frappe.pages['fnb-control'].on_page_load = function(wrapper) {
    const page=frappe.ui.make_app_page({parent:wrapper,title:__('F&B Cost Control'),single_column:true});
    const escape=frappe.utils.escape_html;
    let version=0;
    let ready=false;

    $(`<style>
        .fnb-kpi-grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(170px, 1fr));
            gap: 12px;
            margin-bottom: 24px;
        }
        .fnb-kpi-card {
            background: #fff;
            border: 1px solid #e2e8f0;
            border-radius: 10px;
            padding: 14px 16px;
            box-shadow: 0 1px 3px rgba(0,0,0,0.03);
            transition: all 0.2s ease;
        }
        .fnb-kpi-card:hover {
            transform: translateY(-2px);
            box-shadow: 0 4px 12px rgba(0,0,0,0.06);
        }
        .fnb-kpi-num {
            font-size: 24px;
            font-weight: 800;
            line-height: 1.1;
            margin-top: 4px;
        }
        .fnb-kpi-label {
            font-size: 11px;
            font-weight: 700;
            text-transform: uppercase;
            color: #64748b;
            display: flex;
            align-items: center;
            gap: 6px;
        }
        .fnb-queue-section {
            background: #fff;
            border: 1px solid #e2e8f0;
            border-radius: 12px;
            padding: 20px;
            margin-bottom: 20px;
            box-shadow: 0 1px 4px rgba(0,0,0,0.02);
        }
        .fnb-queue-header {
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 14px;
            padding-bottom: 10px;
            border-bottom: 1px solid #f1f5f9;
        }
        .fnb-queue-title {
            font-size: 15px;
            font-weight: 700;
            color: #1e293b;
            display: flex;
            align-items: center;
            gap: 8px;
            margin: 0;
        }
        .fnb-row-card {
            border: 1px solid #e2e8f0;
            border-radius: 8px;
            padding: 12px 16px;
            margin-bottom: 8px;
            display: flex;
            justify-content: space-between;
            align-items: center;
            background: #f8fafc;
            transition: all 0.15s ease;
            cursor: pointer;
            text-decoration: none !important;
            color: inherit !important;
        }
        .fnb-kpi-card:active {
            transform: scale(0.97);
        }
        .fnb-row-card:hover {
            background: #fff;
            border-color: #cbd5e1;
            transform: translateX(4px);
            box-shadow: 0 2px 8px rgba(0,0,0,0.05);
        }
        .fnb-row-card .fa-chevron-right {
            transition: transform 0.15s ease;
        }
        .fnb-row-card:hover .fa-chevron-right {
            transform: translateX(4px);
        }
        .fnb-row-card:active {
            transform: scale(0.99);
        }
        @keyframes fnb-shimmer {
            0% { background-position: -200% 0; }
            100% { background-position: 200% 0; }
        }
        .fnb-skeleton {
            background: linear-gradient(90deg, #f1f5f9 25%, #e2e8f0 50%, #f1f5f9 75%);
            background-size: 200% 100%;
            animation: fnb-shimmer 1.5s infinite;
            border-radius: 4px;
            display: inline-block;
        }
    </style>`).appendTo(wrapper);

    const body=$('<div class="fnb-control-body" style="padding-top: 10px;"></div>').appendTo(page.body);
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

    const DOCTYPE_META = {
        'FNB Service Ticket': { icon: 'fa-ticket', color: '#2563eb', label: __('Phiếu phục vụ') },
        'FNB Production Batch': { icon: 'fa-cogs', color: '#0891b2', label: __('Lô sơ chế / nấu') },
        'FNB Waste Record': { icon: 'fa-trash-o', color: '#ef4444', label: __('Biên bản hủy') },
        'FNB Stock Count': { icon: 'fa-cubes', color: '#f59e0b', label: __('Phiếu kiểm kê') },
        'FNB Service Session': { icon: 'fa-calendar-check-o', color: '#8b5cf6', label: __('Phiên buffet/tiệc') }
    };

    function get_status_badge(status) {
        let st = String(status || '');
        let bg = '#f1f5f9', color = '#475569';
        if (['Draft', 'Nháp'].includes(st)) { bg = '#fef3c7'; color = '#b45309'; }
        else if (['Submitted', 'Pending', 'In Progress', 'Chờ xử lý', 'Đang thực hiện'].includes(st)) { bg = '#dbeafe'; color = '#1d4ed8'; }
        else if (['Completed', 'Approved', 'Đã duyệt', 'Hoàn tất'].includes(st)) { bg = '#dcfce7'; color = '#15803d'; }
        else if (['Cancelled', 'Hủy'].includes(st)) { bg = '#fee2e2'; color = '#b91c1c'; }
        return `<span class="badge" style="background:${bg}; color:${color}; font-size:11px; padding:3px 8px; border-radius:12px; font-weight:600;">${escape(__(st))}</span>`;
    }

    function render() {
        if (!ready) return;
        const request=++version;
        const selected=property.get_value();
        body.empty();
        if (!selected) {
            body.html(`
                <div style="text-align: center; padding: 60px 20px; background: #fff; border: 1px solid #e2e8f0; border-radius: 12px;">
                    <div style="width: 64px; height: 64px; border-radius: 50%; background: #e0e7ff; display: inline-flex; align-items: center; justify-content: center; margin-bottom: 14px;">
                        <i class="fa fa-cutlery" style="font-size: 28px; color: #4338ca;"></i>
                    </div>
                    <h4 style="font-weight: 700; color: #1e293b; margin-bottom: 6px;">${__('Trung Tâm Kiểm Soát Chi Phí F&B')}</h4>
                    <p style="font-size: 13px; color: #64748b; max-width: 440px; margin: 0 auto;">${__('Vui lòng chọn Cơ sở và Outlet phía trên để theo dõi công việc chờ duyệt, phiếu phục vụ, định mức kho và chi phí tạm tính.')}</p>
                </div>
            `);
            return;
        }

        // Render Shimmer Skeletons
        body.html(`
            <div class="fnb-kpi-grid">
                ${[1,2,3,4,5].map(() => `
                    <div class="fnb-kpi-card">
                        <div class="fnb-skeleton" style="width: 100px; height: 14px; margin-bottom: 8px;"></div>
                        <div class="fnb-skeleton" style="width: 50px; height: 28px;"></div>
                    </div>
                `).join('')}
            </div>
            <div class="fnb-queue-section">
                <div class="fnb-skeleton" style="width: 180px; height: 20px; margin-bottom: 16px;"></div>
                <div class="fnb-skeleton" style="width: 100%; height: 48px; margin-bottom: 8px; border-radius: 8px;"></div>
                <div class="fnb-skeleton" style="width: 100%; height: 48px; border-radius: 8px;"></div>
            </div>
        `);

        frappe.call({method:'hospitality_core.hospitality_core.api.fnb.reports.dashboard',
            args:{property:selected,outlet:outlet.get_value()},callback:r=>{
                if (request!==version) return;
                const data=r.message;
                body.empty();
                const queues = (data && data.queues) || [];

                // 1. KPI Cards Bar
                let kpiHtml = '<div class="fnb-kpi-grid">';
                for (const queue of queues) {
                    const meta = DOCTYPE_META[queue.doctype] || { icon: 'fa-list', color: '#64748b', label: __(queue.doctype) };
                    const count = queue.rows ? queue.rows.length : 0;
                    kpiHtml += `
                        <div class="fnb-kpi-card" style="cursor:pointer;" data-target="${escape(queue.doctype)}" title="${__('Bấm để cuộn đến hàng đợi này')}">
                            <div class="fnb-kpi-label"><i class="fa ${meta.icon}" style="color:${meta.color};"></i> ${meta.label}</div>
                            <div class="fnb-kpi-num" style="color:${count > 0 ? meta.color : '#64748b'};">${count}</div>
                        </div>
                    `;
                }
                kpiHtml += '</div>';
                body.append(kpiHtml);

                body.find('.fnb-kpi-card').on('click', function () {
                    let dt = $(this).data('target');
                    let $targetSec = body.find(`.fnb-queue-section[data-doctype="${escape(dt)}"]`);
                    if ($targetSec.length) {
                        $('html, body').animate({ scrollTop: $targetSec.offset().top - 80 }, 300);
                        $targetSec.css({ 'transition': 'box-shadow 0.3s ease', 'box-shadow': '0 0 0 2px #2563eb' });
                        setTimeout(() => { $targetSec.css('box-shadow', ''); }, 1200);
                    }
                });

                // 2. Queue Sections Grid
                for (const queue of queues) {
                    const meta = DOCTYPE_META[queue.doctype] || { icon: 'fa-list', color: '#64748b', label: __(queue.doctype) };
                    const section=$(`<div class="fnb-queue-section" data-doctype="${escape(queue.doctype)}"></div>`).appendTo(body);
                    const count = queue.rows ? queue.rows.length : 0;

                    const header = $(`
                        <div class="fnb-queue-header">
                            <h4 class="fnb-queue-title">
                                <i class="fa ${meta.icon}" style="color:${meta.color};"></i>
                                <span>${meta.label}</span>
                                <span class="badge" style="background:${count > 0 ? meta.color : '#e2e8f0'}; color:${count > 0 ? '#fff' : '#64748b'}; font-size:11px; border-radius:10px; padding:2px 8px;">${count}</span>
                            </h4>
                            <button class="btn btn-default btn-xs fnb-list-btn" style="font-weight:600; border-radius:6px;">
                                <i class="fa fa-external-link"></i> ${__('Xem danh sách')}
                            </button>
                        </div>
                    `).appendTo(section);

                    header.find('.fnb-list-btn').on('click', () => frappe.set_route('List', queue.doctype));

                    if (!queue.rows || !queue.rows.length) {
                        section.append(`
                            <div style="font-size:13px; color:#94a3b8; padding:12px 4px; display:flex; align-items:center; gap:8px;">
                                <i class="fa fa-check-circle text-success fa-lg"></i>
                                <span>${__('Không có hồ sơ nào đang chờ xử lý.')}</span>
                            </div>
                        `);
                    } else {
                        const listWrap = $('<div></div>').appendTo(section);
                        for (const row of queue.rows) {
                            const link=$(`
                                <div class="fnb-row-card">
                                    <div style="display:flex; align-items:center; gap:12px;">
                                        <span style="font-weight:700; color:#1e293b; font-size:14px;">${escape(row.name)}</span>
                                        ${get_status_badge(row.status)}
                                        ${row.outlet ? `<span class="badge" style="background:#f1f5f9; color:#475569; font-size:11px;"><i class="fa fa-map-marker" style="margin-right:3px;"></i>${escape(row.outlet)}</span>` : ''}
                                    </div>
                                    <div style="display:flex; align-items:center; gap:8px; color:#2563eb; font-size:12px; font-weight:600;">
                                        <span>${__('Xử lý')}</span>
                                        <i class="fa fa-chevron-right" style="font-size:10px;"></i>
                                    </div>
                                </div>
                            `).appendTo(listWrap);
                            link.on('click',()=>frappe.set_route('Form',queue.doctype,row.name));
                        }
                    }
                }

                // 3. Cost Summary Action Card
                if (data && data.can_view_cost) {
                    const costCard = $(`
                        <div class="fnb-queue-section" style="background: linear-gradient(135deg, #f8fafc, #f1f5f9); border: 1px dashed #cbd5e1; display:flex; justify-content:space-between; align-items:center;">
                            <div>
                                <h5 style="margin:0 0 4px 0; font-weight:700; color:#1e293b;"><i class="fa fa-line-chart text-primary" style="margin-right:8px;"></i>${__('Báo Cáo Phân Tích Chi Phí F&B')}</h5>
                                <p style="margin:0; font-size:13px; color:#64748b;">${__('Tra cứu doanh thu thuần, chi phí bán hàng và chi phí nguyên liệu tạm tính theo kỳ.')}</p>
                            </div>
                            <button class="btn btn-primary btn-sm" style="font-weight:600; border-radius:6px;">
                                <i class="fa fa-calendar-check-o" style="margin-right:5px;"></i>${__('Xem chi phí theo kỳ')}
                            </button>
                        </div>
                    `).appendTo(body);

                    costCard.find('button').on('click',()=>{
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
                }
            }});
    }
    ready=true;
    render();
};
