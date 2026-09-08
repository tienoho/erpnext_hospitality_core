frappe.pages['guest-360'].on_page_load = function(wrapper) {
    const page = frappe.ui.make_app_page({parent: wrapper, title: __('Hồ sơ khách 360°'), single_column: true});
    wrapper.guest_content = $('<div class="guest-360-wrapper p-3"></div>').appendTo($(wrapper).find('.layout-main-section'));
    wrapper.guest_request = 0;
    
    $(`<style>
        @keyframes g360-fade-in {
            from { opacity: 0; transform: translateY(6px); }
            to { opacity: 1; transform: translateY(0); }
        }
        .guest-360-dashboard .tab-pane.active {
            animation: g360-fade-in 0.22s cubic-bezier(0.16, 1, 0.3, 1);
        }
        @keyframes g360-shimmer {
            0% { background-position: -200% 0; }
            100% { background-position: 200% 0; }
        }
        .g360-skeleton {
            background: linear-gradient(90deg, #f1f5f9 25%, #e2e8f0 50%, #f1f5f9 75%);
            background-size: 200% 100%;
            animation: g360-shimmer 1.5s infinite;
            border-radius: 4px;
            display: inline-block;
        }
        .g360-copyable {
            cursor: pointer;
            padding: 3px 7px;
            border-radius: 6px;
            transition: all 0.15s ease;
            background: rgba(99, 102, 241, 0.06);
            display: inline-flex;
            align-items: center;
        }
        .g360-copyable:hover {
            background: rgba(99, 102, 241, 0.15);
            color: #4338ca !important;
        }
        .g360-copyable:active {
            transform: scale(0.96);
        }
        .g360-action-btn {
            transition: transform 0.12s ease, box-shadow 0.15s ease;
        }
        .g360-action-btn:active {
            transform: scale(0.95);
        }
        .nav-tabs > li > a {
            transition: background 0.15s ease, color 0.15s ease;
            font-weight: 600;
        }
        .nav-tabs > li > a:hover {
            background: #f8fafc;
        }
    </style>`).appendTo(wrapper);

    // Add Guest Link selector
    const guest_field = page.add_field({
        fieldname: 'guest', 
        label: __('Khách Hàng'), 
        fieldtype: 'Link', 
        options: 'Guest', 
        change() {
            render_guest_profile(wrapper, page.fields_dict.guest.get_value());
        }
    });

    // Check URL query parameter 'guest' if opened with route options
    if (frappe.route_options && frappe.route_options.guest) {
        guest_field.set_value(frappe.route_options.guest);
    } else {
        wrapper.guest_content.html(`
            <div style="text-align: center; padding: 60px 20px; color: var(--text-muted, #6b7280);">
                <div style="font-size: 48px; margin-bottom: 16px;">👤</div>
                <h4 style="color: var(--text-color, #374151); font-weight: 600;">${__('Chưa Chọn Hồ Sơ Khách Hàng')}</h4>
                <p style="max-width: 460px; margin: 0 auto; font-size: 13px;">${__('Vui lòng chọn một khách hàng từ ô tìm kiếm phía trên để tra cứu toàn diện hồ sơ CRM, sở thích lưu trú, công nợ và điểm thưởng.')}</p>
            </div>
        `);
    }
};

function render_guest_profile(wrapper, guest) {
    const request = ++wrapper.guest_request;
    const body = wrapper.guest_content;
    body.empty();
    if (!guest) return;
    
    body.html(`
        <div class="guest-360-dashboard" style="opacity:0.85;">
            <div class="card mb-4" style="background: #ffffff; border-radius: 12px; border: 1px solid #e5e7eb; padding: 20px;">
                <div style="display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap; gap: 16px;">
                    <div style="display: flex; gap: 16px; align-items: center;">
                        <div class="g360-skeleton" style="width: 56px; height: 56px; border-radius: 50%;"></div>
                        <div>
                            <div class="g360-skeleton" style="width: 180px; height: 22px; margin-bottom: 8px;"></div>
                            <div class="g360-skeleton" style="width: 320px; height: 16px;"></div>
                        </div>
                    </div>
                    <div style="display: flex; gap: 8px;">
                        <div class="g360-skeleton" style="width: 90px; height: 32px; border-radius: 6px;"></div>
                        <div class="g360-skeleton" style="width: 110px; height: 32px; border-radius: 6px;"></div>
                    </div>
                </div>
                <div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(170px, 1fr)); gap: 12px; margin-top: 20px; padding-top: 16px; border-top: 1px solid #f3f4f6;">
                    <div class="g360-skeleton" style="height: 65px; border-radius: 8px;"></div>
                    <div class="g360-skeleton" style="height: 65px; border-radius: 8px;"></div>
                    <div class="g360-skeleton" style="height: 65px; border-radius: 8px;"></div>
                    <div class="g360-skeleton" style="height: 65px; border-radius: 8px;"></div>
                </div>
            </div>
            <div class="card p-4" style="background: #ffffff; border-radius: 12px; border: 1px solid #e5e7eb;">
                <div class="g360-skeleton" style="width: 240px; height: 24px; margin-bottom: 16px;"></div>
                <div class="g360-skeleton" style="width: 100%; height: 28px; margin-bottom: 10px;"></div>
                <div class="g360-skeleton" style="width: 100%; height: 28px; margin-bottom: 10px;"></div>
                <div class="g360-skeleton" style="width: 85%; height: 28px;"></div>
            </div>
        </div>
    `);
    
    const escape = value => frappe.utils.escape_html(String(value ?? ''));
    
    frappe.call({
        method: 'hospitality_core.hospitality_core.page.guest_360.guest_360.get_guest_details',
        args: { guest },
        callback(r) {
            if (request !== wrapper.guest_request) return;
            const d = r.message;
            if (!d || !d.guest) {
                body.html(`<div class="alert alert-warning">${__('Không tìm thấy thông tin hồ sơ cho khách hàng này.')}</div>`);
                return;
            }
            const to_flt = (val) => (typeof flt !== 'undefined' ? flt(val) : (parseFloat(val) || 0));

            // Calculations & formatting
            const initials = (d.guest.full_name || 'G').split(' ').map(n => n[0]).slice(0, 2).join('').toUpperCase();
            
            // VIP / Guest Type Badge
            let badgeHtml = '';
            if (d.guest.guest_type === 'VIP') {
                badgeHtml = `<span class="badge" style="background: #fef3c7; color: #b45309; border: 1px solid #fde68a; font-weight: 700; font-size: 12px; padding: 4px 8px;">🌟 VIP</span>`;
            } else if (d.guest.guest_type === 'Blacklisted') {
                badgeHtml = `<span class="badge" style="background: #fee2e2; color: #b91c1c; border: 1px solid #fca5a5; font-weight: 700; font-size: 12px; padding: 4px 8px;">🚫 Blacklisted</span>`;
            } else if (d.guest.guest_type === 'Corporate') {
                badgeHtml = `<span class="badge" style="background: #e0e7ff; color: #4338ca; border: 1px solid #c7d2fe; font-weight: 700; font-size: 12px; padding: 4px 8px;">🏢 Doanh nghiệp</span>`;
            } else {
                badgeHtml = `<span class="badge" style="background: #f3f4f6; color: #4b5563; border: 1px solid #e5e7eb; font-weight: 600; font-size: 12px; padding: 4px 8px;">Khách lẻ</span>`;
            }

            // Spend formatting
            const spendEntries = Object.entries(d.spend_by_currency || {});
            const spendSummary = spendEntries.length ? spendEntries.map(([curr, val]) => format_currency(val, curr)).join('<br>') : '0 ₫';

            // Balance formatting
            const balanceEntries = Object.entries(d.balances_by_currency || {});
            const hasOutstanding = balanceEntries.some(([_, val]) => to_flt(val) > 0);
            const balanceSummary = balanceEntries.length ? balanceEntries.map(([curr, val]) => format_currency(val, curr)).join('<br>') : '0 ₫';

            // Status Badge Helper
            const getStatusBadge = (st) => {
                if (st === 'Reserved') return `<span class="badge badge-info" style="background:#dbeafe; color:#1e40af; border:none; padding:4px 8px;">${__('Đặt trước')}</span>`;
                if (st === 'Checked In') return `<span class="badge badge-success" style="background:#dcfce7; color:#166534; border:none; padding:4px 8px;">${__('Đang ở')}</span>`;
                if (st === 'Checked Out') return `<span class="badge badge-default" style="background:#f3f4f6; color:#4b5563; border:none; padding:4px 8px;">${__('Đã trả')}</span>`;
                if (st === 'Cancelled') return `<span class="badge badge-danger" style="background:#fee2e2; color:#991b1b; border:none; padding:4px 8px;">${__('Đã hủy')}</span>`;
                return `<span class="badge">${escape(st)}</span>`;
            };

            const stats = d.stats || {};
            const format_user_date = (dt) => {
                if (!dt) return '—';
                return (frappe.datetime && frappe.datetime.str_to_user) ? frappe.datetime.str_to_user(dt) : dt;
            };

            // Build HTML
            let html = `
            <div class="guest-360-dashboard">
                <!-- 1. HEADER PROFILE CARD -->
                <div class="card mb-4" style="background: var(--card-bg, #ffffff); border-radius: 12px; border: 1px solid var(--border-color, #e5e7eb); box-shadow: 0 2px 6px rgba(0,0,0,0.03); padding: 20px;">
                    <div style="display: flex; flex-wrap: wrap; justify-content: space-between; align-items: center; gap: 16px;">
                        <div style="display: flex; align-items: center; gap: 16px;">
                            <div style="width: 56px; height: 56px; border-radius: 50%; background: linear-gradient(135deg, #4f46e5, #7c3aed); color: white; display: flex; align-items: center; justify-content: center; font-size: 22px; font-weight: 700; flex-shrink: 0; box-shadow: 0 4px 10px rgba(79,70,229,0.3);">
                                ${escape(initials)}
                            </div>
                            <div>
                                <div style="display: flex; align-items: center; gap: 10px; flex-wrap: wrap;">
                                    <h3 style="margin: 0; font-size: 20px; font-weight: 700; color: var(--text-color, #111827);">${escape(d.guest.full_name)}</h3>
                                    ${badgeHtml}
                                </div>
                                <div style="margin-top: 6px; font-size: 13px; color: var(--text-muted, #6b7280); display: flex; gap: 10px; flex-wrap: wrap;">
                                    ${d.guest.mobile_no ? `<span class="g360-copyable" data-copy-val="${escape(d.guest.mobile_no)}" title="${__('Nhấn để sao chép SĐT')}"><i class="fa fa-phone" style="color: #6366f1; margin-right: 5px;"></i>${escape(d.guest.mobile_no)} <i class="fa fa-clone" style="font-size: 10px; margin-left: 4px; opacity: 0.6;"></i></span>` : `<span><i class="fa fa-phone" style="color: #6366f1; margin-right: 5px;"></i>—</span>`}
                                    ${d.guest.email_id ? `<span class="g360-copyable" data-copy-val="${escape(d.guest.email_id)}" title="${__('Nhấn để sao chép Email')}"><i class="fa fa-envelope" style="color: #6366f1; margin-right: 5px;"></i>${escape(d.guest.email_id)} <i class="fa fa-clone" style="font-size: 10px; margin-left: 4px; opacity: 0.6;"></i></span>` : `<span><i class="fa fa-envelope" style="color: #6366f1; margin-right: 5px;"></i>—</span>`}
                                    ${(d.guest.identification_no || d.guest.id_passport_number) ? `<span class="g360-copyable" data-copy-val="${escape(d.guest.identification_no || d.guest.id_passport_number)}" title="${__('Nhấn để sao chép CCCD/Hộ chiếu')}"><i class="fa fa-id-card" style="color: #6366f1; margin-right: 5px;"></i>${escape(d.guest.identification_type ? d.guest.identification_type + ': ' : '')}${escape(d.guest.identification_no || d.guest.id_passport_number)} <i class="fa fa-clone" style="font-size: 10px; margin-left: 4px; opacity: 0.6;"></i></span>` : ''}
                                    ${d.guest.date_of_birth ? `<span><i class="fa fa-birthday-cake" style="color: #6366f1; margin-right: 5px;"></i>${format_user_date(d.guest.date_of_birth)}</span>` : ''}
                                    ${d.guest.nationality ? `<span><i class="fa fa-globe" style="color: #6366f1; margin-right: 5px;"></i>${escape(d.guest.nationality)}</span>` : ''}
                                </div>
                            </div>
                        </div>
                        <div style="display: flex; gap: 8px;">
                            <button class="btn btn-default btn-sm g360-action-btn" data-guest-edit style="font-weight: 600; border-radius: 6px;">
                                <i class="fa fa-pencil" style="margin-right: 4px;"></i>${__('Sửa Hồ Sơ')}
                            </button>
                            <button class="btn btn-primary btn-sm g360-action-btn" data-new-res style="font-weight: 600; border-radius: 6px;">
                                <i class="fa fa-calendar-plus-o" style="margin-right: 4px;"></i>${__('Đặt Phòng Mới')}
                            </button>
                        </div>
                    </div>

                    <!-- KPI CARDS -->
                    <div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(170px, 1fr)); gap: 12px; margin-top: 20px; padding-top: 16px; border-top: 1px solid var(--border-color, #f3f4f6);">
                        <div style="background: var(--bg-color, #f9fafb); border-radius: 8px; padding: 12px 14px; border: 1px solid var(--border-color, #f3f4f6);">
                            <div style="font-size: 11px; text-transform: uppercase; color: var(--text-muted, #6b7280); font-weight: 700;">🏨 ${__('Tổng Lượt Ở')}</div>
                            <div style="font-size: 20px; font-weight: 700; color: #2563eb; margin-top: 4px;">${stats.total_stays || 0} <span style="font-size: 12px; font-weight: 500; color: #6b7280;">lượt</span></div>
                        </div>
                        <div style="background: var(--bg-color, #f9fafb); border-radius: 8px; padding: 12px 14px; border: 1px solid var(--border-color, #f3f4f6);">
                            <div style="font-size: 11px; text-transform: uppercase; color: var(--text-muted, #6b7280); font-weight: 700;">💰 ${__('Tổng Chi Tiêu')}</div>
                            <div style="font-size: 16px; font-weight: 700; color: #059669; margin-top: 4px;">${spendSummary}</div>
                        </div>
                        <div style="background: var(--bg-color, #f9fafb); border-radius: 8px; padding: 12px 14px; border: 1px solid var(--border-color, #f3f4f6);">
                            <div style="font-size: 11px; text-transform: uppercase; color: var(--text-muted, #6b7280); font-weight: 700;">💳 ${__('Dư Nợ Hiện Tại')}</div>
                            <div style="font-size: 16px; font-weight: 700; color: ${hasOutstanding ? '#e11d48' : '#10b981'}; margin-top: 4px;">${balanceSummary}</div>
                        </div>
                        <div style="background: var(--bg-color, #f9fafb); border-radius: 8px; padding: 12px 14px; border: 1px solid var(--border-color, #f3f4f6);">
                            <div style="font-size: 11px; text-transform: uppercase; color: var(--text-muted, #6b7280); font-weight: 700;">🗓️ ${__('Lần Đến Gần Nhất')}</div>
                            <div style="font-size: 14px; font-weight: 700; color: var(--text-color, #374151); margin-top: 4px;">
                                ${format_user_date(stats.last_visit)}
                                ${stats.last_room ? `<span class="badge badge-info" style="margin-left: 4px;">P.${escape(stats.last_room)}</span>` : ''}
                            </div>
                        </div>
                    </div>
                </div>

                <!-- 2. TABBED NAVIGATION -->
                <ul class="nav nav-tabs" style="border-bottom: 2px solid var(--border-color, #e5e7eb); margin-bottom: 20px;">
                    <li class="active">
                        <a data-toggle="tab" href="#tab-overview" style="font-weight: 700; padding: 10px 18px; border-radius: 8px 8px 0 0;">
                            <i class="fa fa-star text-warning" style="margin-right: 6px;"></i>${__('Tổng Quan & Sở Thích')}
                        </a>
                    </li>
                    <li>
                        <a data-toggle="tab" href="#tab-stays" style="font-weight: 700; padding: 10px 18px; border-radius: 8px 8px 0 0;">
                            <i class="fa fa-history text-info" style="margin-right: 6px;"></i>${__('Lịch Sử Lưu Trú')} <span class="badge" style="background:#e0f2fe; color:#0369a1; font-weight:700;">${(d.history || []).length}</span>
                        </a>
                    </li>
                    <li>
                        <a data-toggle="tab" href="#tab-finance" style="font-weight: 700; padding: 10px 18px; border-radius: 8px 8px 0 0;">
                            <i class="fa fa-credit-card text-success" style="margin-right: 6px;"></i>${__('Tài Chính & Công Nợ')}
                        </a>
                    </li>
                    <li>
                        <a data-toggle="tab" href="#tab-loyalty" style="font-weight: 700; padding: 10px 18px; border-radius: 8px 8px 0 0;">
                            <i class="fa fa-id-badge text-primary" style="margin-right: 6px;"></i>${__('Hội Viên & Tích Điểm')} <span class="badge" style="background:#ede9fe; color:#6d28d9; font-weight:700;">${(d.memberships || []).length}</span>
                        </a>
                    </li>
                </ul>

                <!-- 3. TAB CONTENT PANES -->
                <div class="tab-content">
                    <!-- TAB 1: OVERVIEW & PREFERENCES -->
                    <div id="tab-overview" class="tab-pane active">
                        <div class="row">
                            <div class="col-md-7">
                                <div class="card p-3 mb-3" style="background: var(--card-bg, #ffffff); border: 1px solid var(--border-color, #e5e7eb); border-radius: 8px;">
                                    <h5 style="margin-top: 0; font-weight: 700; color: var(--text-color, #111827);"><i class="fa fa-heart text-danger" style="margin-right: 6px;"></i>${__('Sở Thích & Ghi Chú Phục Vụ')}</h5>
                                    ${(d.preferences && d.preferences.length) ? `
                                        <div class="table-responsive">
                                            <table class="table table-hover table-striped" style="margin-bottom: 0;">
                                                <thead>
                                                    <tr>
                                                        <th>${__('Phân Loại')}</th>
                                                        <th>${__('Sở Thích Chi Tiết')}</th>
                                                        <th>${__('Phạm Vi Áp Dụng')}</th>
                                                    </tr>
                                                </thead>
                                                <tbody>
                                                    ${d.preferences.map(p => `
                                                        <tr>
                                                            <td><span class="badge badge-default" style="font-weight: 600;">${escape(p.preference_type)}</span></td>
                                                            <td style="font-weight: 600; color: #1e40af;">${escape(p.preference_value)}</td>
                                                            <td>${p.sharing_scope === 'Group' ? `<span class="badge badge-info">${__('Dùng chung toàn chuỗi')}</span>` : `<span class="badge badge-light">${escape(p.property || 'Cơ sở')}</span>`}</td>
                                                        </tr>
                                                    `).join('')}
                                                </tbody>
                                            </table>
                                        </div>
                                    ` : `
                                        <div style="text-align: center; padding: 24px; color: var(--text-muted, #9ca3af);">
                                            <i class="fa fa-info-circle fa-lg" style="margin-bottom: 6px;"></i>
                                            <div>${__('Chưa có sở thích nào được lưu cho khách này.')}</div>
                                        </div>
                                    `}
                                </div>
                            </div>
                            <div class="col-md-5">
                                <div class="card p-3 mb-3" style="background: var(--card-bg, #ffffff); border: 1px solid var(--border-color, #e5e7eb); border-radius: 8px;">
                                    <h5 style="margin-top: 0; font-weight: 700; color: var(--text-color, #111827);"><i class="fa fa-comments text-primary" style="margin-right: 6px;"></i>${__('Yêu Cầu & Phản Hồi Đang Xử Lý')}</h5>
                                    ${(d.interactions && d.interactions.length) ? `
                                        <div class="table-responsive">
                                            <table class="table table-hover" style="margin-bottom: 0;">
                                                <thead>
                                                    <tr>
                                                        <th>${__('Nội Dung')}</th>
                                                        <th>${__('Trạng Thái')}</th>
                                                        <th>${__('Phụ Trách')}</th>
                                                    </tr>
                                                </thead>
                                                <tbody>
                                                    ${d.interactions.map(i => `
                                                        <tr>
                                                            <td style="font-weight: 600;">${escape(i.subject)}</td>
                                                            <td><span class="badge badge-warning">${escape(i.status)}</span></td>
                                                            <td>${escape(i.assigned_to || '—')}</td>
                                                        </tr>
                                                    `).join('')}
                                                </tbody>
                                            </table>
                                        </div>
                                    ` : `
                                        <div style="text-align: center; padding: 24px; color: var(--text-muted, #9ca3af);">
                                            <i class="fa fa-check-circle text-success fa-lg" style="margin-bottom: 6px;"></i>
                                            <div>${__('Không có yêu cầu hay sự vụ nào đang chờ xử lý.')}</div>
                                        </div>
                                    `}
                                </div>
                                <div class="card p-3 mb-3" style="background: var(--card-bg, #ffffff); border: 1px solid var(--border-color, #e5e7eb); border-radius: 8px;">
                                    <h5 style="margin-top: 0; font-weight: 700; color: var(--text-color, #111827);"><i class="fa fa-map-marker text-danger" style="margin-right: 6px;"></i>${__('Địa Chỉ & Liên Hệ')}</h5>
                                    <p style="margin-bottom: 6px; color: var(--text-muted, #4b5563);">${escape(d.guest.address || __('Chưa cập nhật địa chỉ'))}</p>
                                </div>
                            </div>
                        </div>
                    </div>

                    <!-- TAB 2: STAY HISTORY -->
                    <div id="tab-stays" class="tab-pane">
                        <div class="card p-3" style="background: var(--card-bg, #ffffff); border: 1px solid var(--border-color, #e5e7eb); border-radius: 8px;">
                            <h5 style="margin-top: 0; font-weight: 700; color: var(--text-color, #111827); margin-bottom: 14px;"><i class="fa fa-list-alt text-info" style="margin-right: 6px;"></i>${__('Danh Sách Đặt Phòng & Lịch Sử Lưu Trú')}</h5>
                            ${(d.history && d.history.length) ? `
                                <div class="table-responsive">
                                    <table class="table table-hover table-striped" style="margin-bottom: 0;">
                                        <thead>
                                            <tr>
                                                <th>${__('Mã Đặt Phòng')}</th>
                                                <th>${__('Cơ Sở')}</th>
                                                <th>${__('Phòng')}</th>
                                                <th>${__('Ngày Đến')}</th>
                                                <th>${__('Ngày Đi')}</th>
                                                <th>${__('Trạng Thái')}</th>
                                                <th style="text-align: right;">${__('Số Dư Folio')}</th>
                                                <th style="text-align: center;">${__('Thao Tác')}</th>
                                            </tr>
                                        </thead>
                                        <tbody>
                                            ${d.history.map(h => `
                                                <tr>
                                                    <td>
                                                        <a href="/app/hotel-reservation/${encodeURIComponent(h.name)}" onclick="frappe.set_route('Form', 'Hotel Reservation', '${escape(h.name)}'); return false;" style="font-weight: 700; color: #2563eb;">
                                                            ${escape(h.name)}
                                                        </a>
                                                    </td>
                                                    <td>${escape(h.property || '—')}</td>
                                                    <td><span class="badge badge-info" style="font-weight: 700;">${escape(h.room_number || h.room || 'Chưa gán')}</span></td>
                                                    <td>${format_user_date(h.arrival_date)}</td>
                                                    <td>${format_user_date(h.departure_date)}</td>
                                                    <td>${getStatusBadge(h.status)}</td>
                                                    <td style="text-align: right; font-weight: 700; color: ${to_flt(h.balance) > 0 ? '#e11d48' : '#059669'};">
                                                        ${h.balance === null ? '—' : format_currency(h.balance, h.currency)}
                                                    </td>
                                                    <td style="text-align: center;">
                                                        ${h.folio ? `
                                                            <a href="/app/guest-folio/${encodeURIComponent(h.folio)}" onclick="frappe.set_route('Form', 'Guest Folio', '${escape(h.folio)}'); return false;" class="btn btn-xs btn-default" style="font-weight: 600;">
                                                                <i class="fa fa-folder-open-o"></i> ${__('Folio')}
                                                            </a>
                                                        ` : '—'}
                                                    </td>
                                                </tr>
                                            `).join('')}
                                        </tbody>
                                    </table>
                                </div>
                            ` : `
                                <div style="text-align: center; padding: 40px; color: var(--text-muted, #9ca3af);">
                                    <i class="fa fa-bed fa-2x" style="margin-bottom: 8px;"></i>
                                    <div>${__('Khách hàng chưa có lịch sử đặt phòng nào trong hệ thống.')}</div>
                                </div>
                            `}
                        </div>
                    </div>

                    <!-- TAB 3: FINANCE & BALANCES -->
                    <div id="tab-finance" class="tab-pane">
                        <div class="row">
                            <div class="col-md-6">
                                <div class="card p-3 mb-3" style="background: var(--card-bg, #ffffff); border: 1px solid var(--border-color, #e5e7eb); border-radius: 8px;">
                                    <h5 style="margin-top: 0; font-weight: 700; color: #059669;"><i class="fa fa-money" style="margin-right: 6px;"></i>${__('Tổng Doanh Thu Chi Tiêu Đã Chốt')}</h5>
                                    ${spendEntries.length ? `
                                        <div class="table-responsive">
                                            <table class="table table-bordered" style="margin-bottom: 0;">
                                                <thead><tr><th>${__('Loại Tiền Tệ')}</th><th style="text-align: right;">${__('Doanh Số')}</th></tr></thead>
                                                <tbody>
                                                    ${spendEntries.map(([c, val]) => `
                                                        <tr>
                                                            <td style="font-weight: 700;">${escape(c)}</td>
                                                            <td style="text-align: right; font-weight: 700; font-size: 15px; color: #059669;">${format_currency(val, c)}</td>
                                                        </tr>
                                                    `).join('')}
                                                </tbody>
                                            </table>
                                        </div>
                                    ` : `<div class="text-muted">${__('Chưa có chi tiêu phát sinh.')}</div>`}
                                </div>
                            </div>
                            <div class="col-md-6">
                                <div class="card p-3 mb-3" style="background: var(--card-bg, #ffffff); border: 1px solid var(--border-color, #e5e7eb); border-radius: 8px;">
                                    <h5 style="margin-top: 0; font-weight: 700; color: #e11d48;"><i class="fa fa-exclamation-circle" style="margin-right: 6px;"></i>${__('Công Nợ Chưa Thanh Toán')}</h5>
                                    ${balanceEntries.length ? `
                                        <div class="table-responsive">
                                            <table class="table table-bordered" style="margin-bottom: 0;">
                                                <thead><tr><th>${__('Loại Tiền Tệ')}</th><th style="text-align: right;">${__('Dư Nợ Hiện Tại')}</th></tr></thead>
                                                <tbody>
                                                    ${balanceEntries.map(([c, val]) => `
                                                        <tr>
                                                            <td style="font-weight: 700;">${escape(c)}</td>
                                                            <td style="text-align: right; font-weight: 700; font-size: 15px; color: ${to_flt(val) > 0 ? '#e11d48' : '#10b981'};">${format_currency(val, c)}</td>
                                                        </tr>
                                                    `).join('')}
                                                </tbody>
                                            </table>
                                        </div>
                                    ` : `<div class="text-muted">${__('Không có công nợ.')}</div>`}
                                </div>
                            </div>
                        </div>
                    </div>

                    <!-- TAB 4: MEMBERSHIPS & LOYALTY -->
                    <div id="tab-loyalty" class="tab-pane">
                        <div class="card p-3" style="background: var(--card-bg, #ffffff); border: 1px solid var(--border-color, #e5e7eb); border-radius: 8px;">
                            <h5 style="margin-top: 0; font-weight: 700; color: #7c3aed; margin-bottom: 14px;"><i class="fa fa-trophy text-warning" style="margin-right: 6px;"></i>${__('Thẻ Thành Viên & Điểm Thưởng')}</h5>
                            ${(d.memberships && d.memberships.length) ? `
                                <div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(280px, 1fr)); gap: 16px;">
                                    ${d.memberships.map(m => `
                                        <div style="border: 1px solid #e0e7ff; border-radius: 10px; padding: 16px; background: linear-gradient(145deg, #ffffff, #f8fafc); box-shadow: 0 2px 5px rgba(0,0,0,0.02);">
                                            <div style="display: flex; justify-content: space-between; align-items: flex-start;">
                                                <div>
                                                    <div style="font-weight: 700; font-size: 15px; color: #1e1b4b;">${escape(m.program)}</div>
                                                    <div style="font-size: 12px; color: #6b7280;">${escape(m.operating_company)}</div>
                                                </div>
                                                <span class="badge" style="background: #e0e7ff; color: #4338ca; font-size: 12px; font-weight: 700; padding: 4px 10px; border-radius: 20px;">
                                                    👑 ${escape(m.tier || 'Thành viên')}
                                                </span>
                                            </div>
                                            <div style="display: flex; justify-content: space-between; margin-top: 16px; padding-top: 12px; border-top: 1px dashed #e2e8f0;">
                                                <div>
                                                    <div style="font-size: 11px; text-transform: uppercase; color: #64748b; font-weight: 700;">${__('Điểm Khả Dụng')}</div>
                                                    <div style="font-size: 18px; font-weight: 800; color: #4f46e5; margin-top: 2px;">${Number(m.available || 0).toLocaleString()}</div>
                                                </div>
                                                <div>
                                                    <div style="font-size: 11px; text-transform: uppercase; color: #64748b; font-weight: 700;">${__('Đang Giữ')}</div>
                                                    <div style="font-size: 16px; font-weight: 700; color: #94a3b8; margin-top: 2px;">${Number(m.held || 0).toLocaleString()}</div>
                                                </div>
                                                <div>
                                                    <div style="font-size: 11px; text-transform: uppercase; color: #64748b; font-weight: 700;">${__('Chi Tiêu Xét Hạng')}</div>
                                                    <div style="font-size: 14px; font-weight: 700; color: #334155; margin-top: 4px;">${format_currency(m.qualifying_spend || 0, m.currency)}</div>
                                                </div>
                                            </div>
                                        </div>
                                    `).join('')}
                                </div>
                            ` : `
                                <div style="text-align: center; padding: 40px; color: var(--text-muted, #9ca3af);">
                                    <i class="fa fa-id-card-o fa-2x" style="margin-bottom: 8px;"></i>
                                    <div>${__('Khách chưa đăng ký tham gia chương trình khách hàng thân thiết nào.')}</div>
                                </div>
                            `}
                        </div>
                    </div>
                </div>
            </div>
            `;

            body.html(html);

            // Prevent tab links from altering window.location.hash and triggering Frappe Desk SPA route changes
            body.find('.nav-tabs a').on('click', function (e) {
                e.preventDefault();
                $(this).tab('show');
            });

            // Bind actions
            body.find('.g360-copyable').on('click', function (e) {
                e.preventDefault();
                let $chip = $(this);
                let val = $chip.attr('data-copy-val');
                if (!val) return;

                // In-place tactile visual feedback
                let $icon = $chip.find('.fa-clone');
                $icon.removeClass('fa-clone').addClass('fa-check text-success');
                $chip.css({ 'background': 'rgba(16, 185, 129, 0.15)', 'color': '#047857' });
                setTimeout(() => {
                    $icon.removeClass('fa-check text-success').addClass('fa-clone');
                    $chip.css({ 'background': '', 'color': '' });
                }, 1400);

                const fallback_copy = () => {
                    let ta = document.createElement("textarea");
                    ta.value = val;
                    ta.style.position = "fixed";
                    ta.style.left = "-9999px";
                    document.body.appendChild(ta);
                    ta.focus();
                    ta.select();
                    try {
                        document.execCommand('copy');
                        frappe.show_alert({ message: __('✓ Đã sao chép: {0}', [val]), indicator: 'green' });
                    } catch (err) {
                        frappe.show_alert({ message: __('Không thể sao chép tự động'), indicator: 'orange' });
                    }
                    ta.remove();
                };

                if (navigator.clipboard && window.isSecureContext) {
                    navigator.clipboard.writeText(val).then(() => {
                        frappe.show_alert({ message: __('✓ Đã sao chép: {0}', [val]), indicator: 'green' });
                    }).catch(fallback_copy);
                } else {
                    fallback_copy();
                }
            });

            body.find('[data-guest-edit]').on('click', () => frappe.set_route('Form', 'Guest', d.guest.name));
            body.find('[data-new-res]').on('click', () => frappe.new_doc('Hotel Reservation', { guest: d.guest.name }));
        },
        error() {
            if (request === wrapper.guest_request) {
                body.html(`<div class="alert alert-danger">${__('Không thể tải hồ sơ khách hàng. Vui lòng kiểm tra kết nối mạng hoặc thử lại.')}</div>`);
            }
        }
    });
}
