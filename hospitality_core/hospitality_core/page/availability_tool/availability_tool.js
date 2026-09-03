frappe.pages['availability-tool'].on_page_load = function (wrapper) {
    var page = frappe.ui.make_app_page({
        parent: wrapper,
        title: __('Tra Cứu Phòng Trống & Công Suất OCC%'),
        single_column: true
    });

    page.add_field({
        fieldname: 'date_range',
        label: __('Khoảng Ngày Lưu Trú'),
        fieldtype: 'DateRange',
        default: [frappe.datetime.now_date(), frappe.datetime.add_days(frappe.datetime.now_date(), 1)],
        reqd: 1,
        change: function () {
            load_availability(wrapper, page);
        }
    });

    page.set_primary_action(__('Kiểm Tra Phòng'), function () {
        load_availability(wrapper, page);
    });

    page.add_inner_button(__('Sơ Đồ Tape Chart'), function () {
        frappe.set_route('tape-chart');
    });

    page.add_inner_button(__('Quầy Lễ Tân'), function () {
        frappe.set_route('front-desk-console');
    });

    // Main layout container
    $(wrapper).find('.layout-main-section').html(`
        <div id="avail-app-container" style="padding: 10px 0;">
            <div id="avail-stats-section"></div>
            <div id="avail-summary-section" style="margin-bottom: 25px;"></div>
            <div id="avail-controls-section" style="margin-bottom: 15px;"></div>
            <div id="avail-rooms-section"></div>
        </div>
    `);

    // Inject CSS
    $(`<style>
        .room-card-box {
            border: 1px solid #d1d8dd;
            border-radius: 8px;
            padding: 12px 10px;
            text-align: center;
            background: #fff;
            transition: all 0.2s ease-in-out;
            min-height: 96px;
            position: relative;
            display: flex;
            flex-direction: column;
            justify-content: space-between;
        }
        .room-card-box:hover {
            transform: translateY(-3px);
            box-shadow: 0 6px 16px rgba(0,0,0,0.12);
        }
        .room-card-avail {
            background: #f0faf4;
            border-color: #27ae60;
            cursor: pointer;
        }
        .room-card-avail:hover {
            border-color: #1e8449;
            background: #e8f8f0;
        }
        .room-card-occ {
            background: #fef9e7;
            border-color: #f39c12;
            cursor: pointer;
        }
        .room-card-res {
            background: #ebf5fb;
            border-color: #2980b9;
            cursor: pointer;
        }
        .room-card-ooo {
            background: #fdedec;
            border-color: #e74c3c;
            opacity: 0.85;
        }
        .filter-pill-btn {
            border: 1px solid #d1d8dd;
            background: #fff;
            color: #495057;
            padding: 6px 14px;
            border-radius: 20px;
            font-size: 13px;
            font-weight: 500;
            cursor: pointer;
            transition: all 0.15s;
            display: inline-flex;
            align-items: center;
            gap: 6px;
        }
        .filter-pill-btn:hover {
            background: #f8f9fa;
            border-color: #adb5bd;
        }
        .filter-pill-btn.active {
            background: #1f272e;
            color: #fff;
            border-color: #1f272e;
            font-weight: 600;
        }
        .view-switch-btn {
            border: 1px solid #d1d8dd;
            background: #fff;
            color: #495057;
            padding: 6px 12px;
            font-size: 13px;
            cursor: pointer;
            transition: all 0.15s;
        }
        .view-switch-btn:first-child { border-radius: 6px 0 0 6px; }
        .view-switch-btn:last-child { border-radius: 0 6px 6px 0; border-left: none; }
        .view-switch-btn.active {
            background: #2f80ed;
            color: #fff;
            border-color: #2f80ed;
            font-weight: 600;
        }
    </style>`).appendTo(wrapper);

    // Initial load
    load_availability(wrapper, page);
};

// Global state
var _avail_state = {
    data: null,
    view: 'grid',          // 'grid' | 'table'
    status_filter: 'all',  // 'all' | 'Available' | 'Occupied' | 'Reserved' | 'Out of Order'
    search_query: '',
    start_date: '',
    end_date: ''
};

function load_availability(wrapper, page) {
    let dates = page.fields_dict.date_range.get_value();
    if (!dates) return;

    let start = Array.isArray(dates) ? dates[0] : dates.split(' to ')[0];
    let end = Array.isArray(dates) ? (dates[1] || start) : (dates.split(' to ')[1] || start);

    _avail_state.start_date = start;
    _avail_state.end_date = end;

    frappe.call({
        method: "hospitality_core.hospitality_core.page.availability_tool.availability_tool.check_availability_counts",
        args: { start_date: start, end_date: end },
        freeze: true,
        callback: function (r) {
            if (r.message) {
                _avail_state.data = r.message;
                render_all(wrapper);
            }
        }
    });
}

function render_all(wrapper) {
    let data = _avail_state.data;
    if (!data) return;

    render_stats_cards(data.stats);
    render_summary_table(data.summary);
    render_controls_bar(data);
    render_rooms_view(data.room_details);
}

function render_stats_cards(stats) {
    stats = stats || {};
    let occ_pct = stats.occupancy_pct || 0;
    let occ_color = occ_pct >= 80 ? '#eb5757' : (occ_pct >= 50 ? '#f2994a' : '#27ae60');

    let html = `
        <div class="row" style="margin-bottom: 20px;">
            <div class="col-md-3 col-xs-6" style="margin-bottom: 10px;">
                <div style="background:#fff; border:1px solid #d1d8dd; border-radius:8px; padding:15px; text-align:center; box-shadow:0 2px 5px rgba(0,0,0,0.04);">
                    <div style="font-size:12px; color:#8d99a6; text-transform:uppercase; font-weight:600;">${__('Tổng Số Phòng')}</div>
                    <div style="font-size:28px; font-weight:700; color:#1f272e; margin:4px 0;">${stats.total_rooms || 0}</div>
                    <small class="text-muted">${__('Toàn khách sạn')}</small>
                </div>
            </div>
            <div class="col-md-3 col-xs-6" style="margin-bottom: 10px;">
                <div style="background:#fff; border:1px solid #d1d8dd; border-radius:8px; padding:15px; text-align:center; box-shadow:0 2px 5px rgba(0,0,0,0.04);">
                    <div style="font-size:12px; color:#8d99a6; text-transform:uppercase; font-weight:600;">${__('Phòng Khả Dụng (Trống)')}</div>
                    <div style="font-size:28px; font-weight:700; color:#27ae60; margin:4px 0;">${stats.available || 0}</div>
                    <small style="color:#27ae60; font-weight:600;">${__('Sẵn sàng đón khách')}</small>
                </div>
            </div>
            <div class="col-md-3 col-xs-6" style="margin-bottom: 10px;">
                <div style="background:#fff; border:1px solid #d1d8dd; border-radius:8px; padding:15px; text-align:center; box-shadow:0 2px 5px rgba(0,0,0,0.04);">
                    <div style="font-size:12px; color:#8d99a6; text-transform:uppercase; font-weight:600;">${__('Phòng Bận / Đã Đặt')}</div>
                    <div style="font-size:28px; font-weight:700; color:#f39c12; margin:4px 0;">${stats.occupied || 0}</div>
                    <small class="text-muted">${__('Đang ở hoặc giữ chỗ')}</small>
                </div>
            </div>
            <div class="col-md-3 col-xs-6" style="margin-bottom: 10px;">
                <div style="background:#fff; border:1px solid #d1d8dd; border-radius:8px; padding:15px; text-align:center; box-shadow:0 2px 5px rgba(0,0,0,0.04);">
                    <div style="font-size:12px; color:#8d99a6; text-transform:uppercase; font-weight:600;">${__('Công Suất Lấp Đầy (OCC%)')}</div>
                    <div style="font-size:28px; font-weight:700; color:${occ_color}; margin:4px 0;">${occ_pct}%</div>
                    <div style="background:#e9ecef; border-radius:4px; height:6px; overflow:hidden; margin-top:6px;">
                        <div style="width:${Math.min(100, occ_pct)}%; background:${occ_color}; height:100%; border-radius:4px;"></div>
                    </div>
                </div>
            </div>
        </div>
    `;
    $('#avail-stats-section').html(html);
}

function render_summary_table(summary) {
    if (!summary || summary.length === 0) {
        $('#avail-summary-section').empty();
        return;
    }

    let html = `
        <div style="background:#fff; border:1px solid #d1d8dd; border-radius:8px; padding:15px; box-shadow:0 2px 5px rgba(0,0,0,0.04);">
            <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:12px;">
                <h5 style="margin:0; font-weight:600; color:#1f272e;">${__('Tổng Hợp Trạng Thái Theo Hạng Phòng')}</h5>
                <span class="text-muted" style="font-size:12px;">${summary.length} ${__('hạng phòng')}</span>
            </div>
            <div class="table-responsive">
                <table class="table table-bordered table-hover" style="margin-bottom:0; font-size:13px;">
                    <thead>
                        <tr style="background:#f8f9fa;">
                            <th>${__('Hạng Phòng (Room Type)')}</th>
                            <th style="text-align:center; width:110px;">${__('Tổng Phòng')}</th>
                            <th style="text-align:center; width:110px;">${__('Đã Đặt / Ở')}</th>
                            <th style="text-align:center; width:120px;">${__('Còn Trống')}</th>
                            <th style="width:240px;">${__('Tỷ Lệ Lấp Đầy (OCC%)')}</th>
                        </tr>
                    </thead>
                    <tbody>
    `;

    summary.forEach(row => {
        let occ = row.occupancy_pct || 0;
        let bar_color = occ >= 80 ? '#eb5757' : (occ >= 50 ? '#f39c12' : '#27ae60');
        let avail_color = row.available > 0 ? '#27ae60' : '#eb5757';

        html += `
            <tr>
                <td><b>${row.room_type}</b></td>
                <td style="text-align:center;">${row.total}</td>
                <td style="text-align:center; color:#f39c12; font-weight:600;">${row.occupied}</td>
                <td style="text-align:center; color:${avail_color}; font-weight:700; font-size:14px;">${row.available}</td>
                <td>
                    <div style="display:flex; align-items:center; gap:8px;">
                        <div style="flex:1; background:#e9ecef; border-radius:4px; height:8px; overflow:hidden;">
                            <div style="width:${Math.min(100, occ)}%; background:${bar_color}; height:100%; border-radius:4px;"></div>
                        </div>
                        <span style="font-size:12px; font-weight:600; min-width:42px; text-align:right;">${occ}%</span>
                    </div>
                </td>
            </tr>
        `;
    });

    html += `</tbody></table></div></div>`;
    $('#avail-summary-section').html(html);
}

function render_controls_bar(data) {
    let rooms = data.room_details || [];
    let count_all = rooms.length;
    let count_avail = rooms.filter(r => r.status === 'Available').length;
    let count_occ = rooms.filter(r => r.status === 'Occupied').length;
    let count_res = rooms.filter(r => r.status === 'Reserved').length;
    let count_ooo = rooms.filter(r => r.status === 'Out of Order').length;

    let filter = _avail_state.status_filter;
    let view = _avail_state.view;

    let html = `
        <div style="display:flex; flex-wrap:wrap; justify-content:space-between; align-items:center; gap:10px; background:#fff; border:1px solid #d1d8dd; border-radius:8px; padding:12px 15px; box-shadow:0 2px 5px rgba(0,0,0,0.04);">
            <!-- Left: Filter Pills -->
            <div style="display:flex; flex-wrap:wrap; gap:8px; align-items:center;">
                <span style="font-size:12px; color:#8d99a6; font-weight:600; text-transform:uppercase; margin-right:4px;">${__('Lọc Nhanh:')}</span>
                <button class="filter-pill-btn ${filter === 'all' ? 'active' : ''}" onclick="change_status_filter('all')">
                    ${__('Tất cả')} (${count_all})
                </button>
                <button class="filter-pill-btn ${filter === 'Available' ? 'active' : ''}" onclick="change_status_filter('Available')">
                    <span style="display:inline-block; width:8px; height:8px; border-radius:50%; background:#27ae60;"></span>
                    ${__('Phòng Trống')} (${count_avail})
                </button>
                <button class="filter-pill-btn ${filter === 'Occupied' ? 'active' : ''}" onclick="change_status_filter('Occupied')">
                    <span style="display:inline-block; width:8px; height:8px; border-radius:50%; background:#f39c12;"></span>
                    ${__('Đang Ở')} (${count_occ})
                </button>
                <button class="filter-pill-btn ${filter === 'Reserved' ? 'active' : ''}" onclick="change_status_filter('Reserved')">
                    <span style="display:inline-block; width:8px; height:8px; border-radius:50%; background:#2980b9;"></span>
                    ${__('Giữ Chỗ')} (${count_res})
                </button>
                <button class="filter-pill-btn ${filter === 'Out of Order' ? 'active' : ''}" onclick="change_status_filter('Out of Order')">
                    <span style="display:inline-block; width:8px; height:8px; border-radius:50%; background:#e74c3c;"></span>
                    ${__('Bảo Trì')} (${count_ooo})
                </button>
            </div>

            <!-- Right: Search & View Toggle -->
            <div style="display:flex; align-items:center; gap:12px;">
                <div style="position:relative; width:220px;">
                    <input type="text" id="avail-search-input" class="form-control input-sm" 
                           placeholder="${__('Tìm số phòng, tên khách...')}" 
                           value="${_avail_state.search_query}"
                           style="border-radius:20px; padding-left:12px; font-size:12px;">
                </div>
                <div style="display:inline-flex;">
                    <button class="view-switch-btn ${view === 'grid' ? 'active' : ''}" onclick="change_view_mode('grid')" title="${__('Xem dạng lưới ô thẻ')}">
                        <i class="fa fa-th"></i> ${__('Lưới')}
                    </button>
                    <button class="view-switch-btn ${view === 'table' ? 'active' : ''}" onclick="change_view_mode('table')" title="${__('Xem dạng bảng danh sách')}">
                        <i class="fa fa-list"></i> ${__('Bảng')}
                    </button>
                </div>
            </div>
        </div>
    `;

    $('#avail-controls-section').html(html);

    // Bind real-time search input
    $('#avail-search-input').on('keyup', function () {
        _avail_state.search_query = $(this).val().toLowerCase().trim();
        render_rooms_view(_avail_state.data.room_details);
    });
}

function change_status_filter(status) {
    _avail_state.status_filter = status;
    render_controls_bar(_avail_state.data);
    render_rooms_view(_avail_state.data.room_details);
}

function change_view_mode(mode) {
    _avail_state.view = mode;
    render_controls_bar(_avail_state.data);
    render_rooms_view(_avail_state.data.room_details);
}

function render_rooms_view(rooms) {
    rooms = rooms || [];
    let filter = _avail_state.status_filter;
    let query = _avail_state.search_query;

    // Apply Filter
    let filtered = rooms.filter(r => {
        if (filter !== 'all' && r.status !== filter) return false;
        if (query) {
            let match_num = (r.room_number || '').toLowerCase().includes(query);
            let match_name = (r.room || '').toLowerCase().includes(query);
            let match_type = (r.room_type || '').toLowerCase().includes(query);
            let match_details = (r.details || '').toLowerCase().includes(query);
            if (!match_num && !match_name && !match_type && !match_details) return false;
        }
        return true;
    });

    if (_avail_state.view === 'grid') {
        render_matrix_grid(filtered);
    } else {
        render_table_view(filtered);
    }
}

function render_matrix_grid(rooms) {
    if (rooms.length === 0) {
        $('#avail-rooms-section').html(`
            <div style="background:#fff; border:1px solid #d1d8dd; border-radius:8px; padding:40px; text-align:center; color:#8d99a6;">
                <i class="fa fa-bed" style="font-size:32px; margin-bottom:10px;"></i>
                <div>${__('Không tìm thấy phòng nào phù hợp với bộ lọc hiện tại.')}</div>
            </div>
        `);
        return;
    }

    // Group by Room Type
    let groups = {};
    rooms.forEach(r => {
        let type = r.room_type || __('Khác');
        if (!groups[type]) groups[type] = [];
        groups[type].push(r);
    });

    let html = '';
    Object.keys(groups).forEach(type => {
        let list = groups[type];
        let avail_count = list.filter(r => r.status === 'Available').length;
        let total = list.length;

        html += `
            <div style="background:#fff; border:1px solid #d1d8dd; border-radius:8px; padding:15px; margin-bottom:15px; box-shadow:0 2px 5px rgba(0,0,0,0.03);">
                <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:12px; border-bottom:1px solid #f0f4f7; padding-bottom:8px;">
                    <div style="font-weight:600; font-size:14px; color:#1f272e;">
                        <i class="fa fa-tag" style="color:#2f80ed; margin-right:6px;"></i> ${type}
                    </div>
                    <div>
                        <span class="badge" style="background:#27ae60; color:#fff; font-size:11px; margin-right:4px;">${avail_count} ${__('Trống')}</span>
                        <span class="badge" style="background:#f0f4f7; color:#495057; font-size:11px;">${total} ${__('Phòng')}</span>
                    </div>
                </div>
                <div style="display:grid; grid-template-columns: repeat(auto-fill, minmax(130px, 1fr)); gap:10px;">
        `;

        list.forEach(r => {
            let card_class = 'room-card-avail';
            let badge_bg = '#27ae60';
            let status_text = __('Trống');
            let click_action = `quick_create_reservation('${r.room}', '${r.room_type}')`;
            let tooltip = __('Bấm để tạo Đặt Phòng ngay');

            if (r.status === 'Occupied') {
                card_class = 'room-card-occ';
                badge_bg = '#f39c12';
                status_text = __('Đang ở');
                click_action = `open_room_reservation('${r.details}')`;
                tooltip = r.details || __('Đang có khách ở');
            } else if (r.status === 'Reserved') {
                card_class = 'room-card-res';
                badge_bg = '#2980b9';
                status_text = __('Giữ chỗ');
                click_action = `open_room_reservation('${r.details}')`;
                tooltip = r.details || __('Đã đặt trước');
            } else if (r.status === 'Out of Order') {
                card_class = 'room-card-ooo';
                badge_bg = '#e74c3c';
                status_text = __('Bảo trì');
                click_action = ``;
                tooltip = __('Phòng đang sửa chữa/bảo trì');
            }

            html += `
                <div class="room-card-box ${card_class}" onclick="${click_action}" title="${tooltip}">
                    <div style="display:flex; justify-content:space-between; align-items:center;">
                        <span style="font-size:18px; font-weight:700; color:#1f272e;">${r.room_number || r.room}</span>
                        <span style="background:${badge_bg}; color:#fff; font-size:9px; font-weight:600; padding:2px 6px; border-radius:10px;">${status_text}</span>
                    </div>
                    <div style="font-size:11px; color:#6c757d; white-space:nowrap; overflow:hidden; text-overflow:ellipsis; margin-top:4px;">
                        ${r.status === 'Available' ? `<span style="color:#27ae60; font-weight:600;"><i class="fa fa-plus-circle"></i> ${__('Đặt phòng')}</span>` : (r.details || '-')}
                    </div>
                    <div style="font-size:10px; color:#8d99a6; text-align:right; margin-top:4px;">
                        ${r.floor || ''}
                    </div>
                </div>
            `;
        });

        html += `</div></div>`;
    });

    $('#avail-rooms-section').html(html);
}

function render_table_view(rooms) {
    if (rooms.length === 0) {
        $('#avail-rooms-section').html(`
            <div style="background:#fff; border:1px solid #d1d8dd; border-radius:8px; padding:40px; text-align:center; color:#8d99a6;">
                ${__('Không tìm thấy phòng nào phù hợp.')}
            </div>
        `);
        return;
    }

    let html = `
        <div style="background:#fff; border:1px solid #d1d8dd; border-radius:8px; padding:15px; box-shadow:0 2px 5px rgba(0,0,0,0.04);">
            <div class="table-responsive">
                <table class="table table-bordered table-hover" style="margin-bottom:0; font-size:13px;">
                    <thead>
                        <tr style="background:#f8f9fa;">
                            <th style="width:120px;">${__('Số Phòng')}</th>
                            <th>${__('Hạng Phòng')}</th>
                            <th style="width:100px;">${__('Tầng')}</th>
                            <th style="width:140px; text-align:center;">${__('Trạng Thái')}</th>
                            <th>${__('Thông Tin Khách / Đặt Phòng')}</th>
                            <th style="width:130px; text-align:center;">${__('Thao Tác')}</th>
                        </tr>
                    </thead>
                    <tbody>
    `;

    rooms.forEach(r => {
        let badge_bg = '#27ae60';
        let status_text = __('Trống (Sẵn sàng)');
        if (r.status === 'Occupied') { badge_bg = '#f39c12'; status_text = __('Đang ở'); }
        if (r.status === 'Reserved') { badge_bg = '#2980b9'; status_text = __('Giữ chỗ'); }
        if (r.status === 'Out of Order') { badge_bg = '#e74c3c'; status_text = __('Bảo trì'); }

        let action_btn = '';
        if (r.status === 'Available') {
            action_btn = `<button class="btn btn-xs btn-primary" onclick="quick_create_reservation('${r.room}', '${r.room_type}')">
                <i class="fa fa-plus"></i> ${__('Đặt phòng')}
            </button>`;
        } else if (r.details) {
            action_btn = `<button class="btn btn-xs btn-default" onclick="open_room_reservation('${r.details}')">
                <i class="fa fa-eye"></i> ${__('Chi tiết')}
            </button>`;
        }

        html += `
            <tr>
                <td><b>${r.room_number || r.room}</b></td>
                <td>${r.room_type}</td>
                <td>${r.floor || '-'}</td>
                <td style="text-align:center;">
                    <span style="background:${badge_bg}; color:#fff; padding:3px 10px; border-radius:12px; font-size:11px; font-weight:600;">
                        ${status_text}
                    </span>
                </td>
                <td><small class="text-muted">${r.details || '-'}</small></td>
                <td style="text-align:center;">${action_btn}</td>
            </tr>
        `;
    });

    html += `</tbody></table></div></div>`;
    $('#avail-rooms-section').html(html);
}

// 1-Click Quick Booking from Available Room Card
window.quick_create_reservation = function (room, room_type) {
    frappe.new_doc('Hotel Reservation', {
        room: room,
        room_type: room_type,
        arrival_date: _avail_state.start_date,
        departure_date: _avail_state.end_date,
        status: 'Reserved'
    });
};

// Open Existing Reservation from Occupied/Reserved Room Card
window.open_room_reservation = function (details) {
    if (!details) return;
    let match = details.match(/RES-[0-9]+/);
    if (match) {
        frappe.set_route('Form', 'Hotel Reservation', match[0]);
    } else {
        frappe.set_route('List', 'Hotel Reservation');
    }
};