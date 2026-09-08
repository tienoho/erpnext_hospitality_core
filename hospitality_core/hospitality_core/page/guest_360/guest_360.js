frappe.pages['guest-360'].on_page_load = function(wrapper) {
    const page = frappe.ui.make_app_page({parent: wrapper, title: __('Hồ sơ khách 360°'), single_column: true});
    wrapper.guest_content = $('<div class="guest-360-wrapper p-3"></div>').appendTo($(wrapper).find('.layout-main-section'));
    wrapper.guest_request = 0;
    
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
    if (!guest) {
        body.html(`
            <div style="text-align: center; padding: 60px 20px; color: var(--text-muted, #6b7280);">
                <div style="font-size: 48px; margin-bottom: 16px;">👤</div>
                <h4 style="color: var(--text-color, #374151); font-weight: 600;">${__('Chưa Chọn Hồ Sơ Khách Hàng')}</h4>
                <p style="max-width: 460px; margin: 0 auto; font-size: 13px;">${__('Vui lòng chọn một khách hàng từ ô tìm kiếm phía trên.')}</p>
            </div>
        `);
        return;
    }
    
    body.html(`
        <div style="text-align: center; padding: 40px; color: var(--text-muted, #6b7280);">
            <i class="fa fa-spinner fa-spin fa-2x"></i>
            <div style="margin-top: 10px; font-weight: 600;">${__('Đang tải hồ sơ 360°…')}</div>
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
            const hasOutstanding = balanceEntries.some(([_, val]) => flt(val) > 0);
            const balanceSummary = balanceEntries.length ? balanceEntries.map(([curr, val]) => format_currency(val, curr)).join('<br>') : '0 ₫';

            // Status Badge Helper
            const getStatusBadge = (st) => {
                if (st === 'Reserved') return `<span class="badge badge-info" style="background:#dbeafe; color:#1e40af; border:none; padding:4px 8px;">${__('Đặt trước')}</span>`;
                if (st === 'Checked In') return `<span class="badge badge-success" style="background:#dcfce7; color:#166534; border:none; padding:4px 8px;">${__('Đang ở')}</span>`;
                if (st === 'Checked Out') return `<span class="badge badge-default" style="background:#f3f4f6; color:#4b5563; border:none; padding:4px 8px;">${__('Đã trả')}</span>`;
                if (st === 'Cancelled') return `<span class="badge badge-danger" style="background:#fee2e2; color:#991b1b; border:none; padding:4px 8px;">${__('Đã hủy')}</span>`;
                return `<span class="badge">${escape(st)}</span>`;
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
                                <div style="margin-top: 6px; font-size: 13px; color: var(--text-muted, #6b7280); display: flex; gap: 18px; flex-wrap: wrap;">
                                    <span><i class="fa fa-phone" style="color: #6366f1; margin-right: 5px;"></i>${escape(d.guest.mobile_no || '—')}</span>
                                    <span><i class="fa fa-envelope" style="color: #6366f1; margin-right: 5px;"></i>${escape(d.guest.email_id || '—')}</span>
                                    ${(d.guest.identification_no || d.guest.id_passport_number) ? `<span><i class="fa fa-id-card" style="color: #6366f1; margin-right: 5px;"></i>${escape(d.guest.identification_type ? d.guest.identification_type + ': ' : '')}${escape(d.guest.identification_no || d.guest.id_passport_number)}</span>` : ''}
                                    ${d.guest.date_of_birth ? `<span><i class="fa fa-birthday-cake" style="color: #6366f1; margin-right: 5px;"></i>${frappe.datetime.str_to_user(d.guest.date_of_birth)}</span>` : ''}
                                    ${d.guest.nationality ? `<span><i class="fa fa-globe" style="color: #6366f1; margin-right: 5px;"></i>${escape(d.guest.nationality)}</span>` : ''}
                                </div>
                            </div>
                        </div>
                        <div style="display: flex; gap: 8px;">
                            <button class="btn btn-default btn-sm" data-guest-edit style="font-weight: 600; border-radius: 6px;">
                                <i class="fa fa-pencil" style="margin-right: 4px;"></i>${__('Sửa Hồ Sơ')}
                            </button>
                            <button class="btn btn-primary btn-sm" data-new-res style="font-weight: 600; border-radius: 6px;">
                                <i class="fa fa-calendar-plus-o" style="margin-right: 4px;"></i>${__('Đặt Phòng Mới')}
                            </button>
                        </div>
                    </div>

                    <!-- KPI CARDS -->
                    <div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(170px, 1fr)); gap: 12px; margin-top: 20px; padding-top: 16px; border-top: 1px solid var(--border-color, #f3f4f6);">
                        <div style="background: var(--bg-color, #f9fafb); border-radius: 8px; padding: 12px 14px; border: 1px solid var(--border-color, #f3f4f6);">
                            <div style="font-size: 11px; text-transform: uppercase; color: var(--text-muted, #6b7280); font-weight: 700;">🏨 ${__('Tổng Lượt Ở')}</div>
                            <div style="font-size: 20px; font-weight: 700; color: #2563eb; margin-top: 4px;">${d.stats.total_stays || 0} <span style="font-size: 12px; font-weight: 500; color: #6b7280;">lượt</span></div>
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
                                ${d.stats.last_visit ? frappe.datetime.str_to_user(d.stats.last_visit) : '—'}
                                ${d.stats.last_room ? `<span class="badge badge-info" style="margin-left: 4px;">P.${escape(d.stats.last_room)}</span>` : ''}
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
                                                    <td>${h.arrival_date ? frappe.datetime.str_to_user(h.arrival_date) : '—'}</td>
                                                    <td>${h.departure_date ? frappe.datetime.str_to_user(h.departure_date) : '—'}</td>
                                                    <td>${getStatusBadge(h.status)}</td>
                                                    <td style="text-align: right; font-weight: 700; color: ${flt(h.balance) > 0 ? '#e11d48' : '#059669'};">
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
                                                            <td style="text-align: right; font-weight: 700; font-size: 15px; color: ${flt(val) > 0 ? '#e11d48' : '#10b981'};">${format_currency(val, c)}</td>
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
