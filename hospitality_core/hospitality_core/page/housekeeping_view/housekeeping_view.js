var _hk_rooms_cache = [];
var _hk_status_filter = 'all'; // 'all' | 'Available' | 'Dirty' | 'Cleaning' | 'Inspected' | 'Occupied' | 'Out of Order'
var _hk_selected_rooms = new Set();

const HK_STATUS_CONFIG = {
    'Available': { label: __('Sạch'), color: '#10b981', border: '#10b981', bg: '#ecfdf5', badge_bg: '#10b981' },
    'Dirty': { label: __('Cần dọn'), color: '#ef4444', border: '#ef4444', bg: '#fef2f2', badge_bg: '#ef4444' },
    'Cleaning': { label: __('Đang dọn'), color: '#f59e0b', border: '#f59e0b', bg: '#fffbeb', badge_bg: '#f59e0b' },
    'Inspected': { label: __('Đã KT'), color: '#06b6d4', border: '#06b6d4', bg: '#ecfeff', badge_bg: '#06b6d4' },
    'Occupied': { label: __('Đang ở'), color: '#6366f1', border: '#6366f1', bg: '#eef2ff', badge_bg: '#6366f1' },
    'Out of Order': { label: __('Khóa/Sửa'), color: '#64748b', border: '#64748b', bg: '#f8fafc', badge_bg: '#64748b' }
};

frappe.pages['housekeeping-view'].on_page_load = function (wrapper) {
    var page = frappe.ui.make_app_page({
        parent: wrapper,
        title: __('Bảng Điều Phối Buồng Phòng (Housekeeping Board)'),
        single_column: true
    });

    page.set_primary_action(__('Làm Mới'), function () {
        load_housekeeping_board(wrapper, page);
    });

    page.add_inner_button(__('Buồng Di Động'), function () {
        frappe.set_route('housekeeping-mobile');
    });

    page.add_inner_button(__('Sơ Đồ Tape Chart'), function () {
        frappe.set_route('tape-chart');
    });

    $(`<style>
        .hk-summary-bar {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(130px, 1fr));
            gap: 12px;
            margin-bottom: 20px;
        }
        .hk-counter-chip {
            background: #fff;
            border: 1px solid #e2e8f0;
            border-radius: 8px;
            padding: 12px 14px;
            text-align: center;
            cursor: pointer;
            transition: all 0.2s ease;
            box-shadow: 0 1px 3px rgba(0,0,0,0.03);
        }
        .hk-counter-chip:hover {
            transform: translateY(-2px);
            box-shadow: 0 4px 10px rgba(0,0,0,0.08);
        }
        .hk-counter-chip:active {
            transform: scale(0.96);
        }
        .hk-counter-chip.active {
            border-color: #2563eb;
            box-shadow: 0 0 0 2px rgba(37,99,235,0.25);
            background: #f8faff;
        }
        .hk-counter-num {
            font-size: 24px;
            font-weight: 800;
            line-height: 1.1;
            margin-bottom: 2px;
        }
        .hk-counter-label {
            font-size: 11px;
            font-weight: 700;
            text-transform: uppercase;
            color: #64748b;
        }

        .hk-room-card {
            background: #fff;
            border: 1px solid #e2e8f0;
            border-radius: 10px;
            padding: 14px;
            margin-bottom: 16px;
            transition: transform 0.2s cubic-bezier(0.4, 0, 0.2, 1), box-shadow 0.2s ease;
            position: relative;
            box-shadow: 0 1px 4px rgba(0,0,0,0.04);
            display: flex;
            flex-direction: column;
            justify-content: space-between;
            min-height: 155px;
        }
        .hk-room-card:hover {
            transform: translateY(-3px);
            box-shadow: 0 6px 16px rgba(0,0,0,0.08);
        }
        .hk-room-card:active {
            transform: translateY(-1px) scale(0.99);
        }
        .hk-room-card.selected {
            border-color: #2563eb;
            box-shadow: 0 0 0 2px #2563eb;
            background: #f8faff;
        }
        .hk-room-card .btn {
            transition: transform 0.12s ease, filter 0.12s ease;
        }
        .hk-room-card .btn:active {
            transform: scale(0.95);
            filter: brightness(0.92);
        }
        .hk-batch-bar .btn {
            transition: transform 0.12s ease;
        }
        .hk-batch-bar .btn:active {
            transform: scale(0.95);
        }

        .hk-batch-bar {
            position: fixed;
            bottom: 24px;
            left: 50%;
            transform: translate(-50%, 60px);
            opacity: 0;
            pointer-events: none;
            background: #0f172a;
            color: #fff;
            padding: 12px 24px;
            border-radius: 50px;
            box-shadow: 0 10px 25px rgba(0,0,0,0.35);
            display: flex;
            align-items: center;
            gap: 15px;
            z-index: 1000;
            transition: transform 0.25s cubic-bezier(0.16, 1, 0.3, 1), opacity 0.25s ease;
        }
        .hk-batch-bar.visible {
            transform: translate(-50%, 0);
            opacity: 1;
            pointer-events: auto;
        }

        #hk-search-box:focus {
            border-color: #3b82f6 !important;
            box-shadow: 0 0 0 3px rgba(59, 130, 246, 0.15) !important;
            outline: none !important;
        }
        #hk-search-clear {
            transition: color 0.15s ease, transform 0.15s ease;
        }
        #hk-search-clear:hover {
            color: #475569 !important;
            transform: scale(1.15);
        }

        /* Skeleton Shimmer & Micro-interactions */
        @keyframes hk-shimmer {
            0% { background-position: -200% 0; }
            100% { background-position: 200% 0; }
        }
        .hk-skeleton {
            background: linear-gradient(90deg, #f1f5f9 25%, #e2e8f0 50%, #f1f5f9 75%);
            background-size: 200% 100%;
            animation: hk-shimmer 1.5s infinite;
            border-radius: 4px;
            display: inline-block;
        }
        @keyframes hk-flash-success {
            0% { box-shadow: 0 0 0 0 rgba(16, 185, 129, 0.7); transform: scale(1); }
            50% { box-shadow: 0 0 0 8px rgba(16, 185, 129, 0.35); transform: scale(1.02); }
            100% { box-shadow: 0 0 0 0 rgba(16, 185, 129, 0); transform: scale(1); }
        }
        .hk-flash-success {
            animation: hk-flash-success 0.5s ease;
        }
    </style>`).appendTo(wrapper);

    $(wrapper).find('.layout-main-section').html(`
        <div id="hk-app-container" style="padding-top: 10px;">
            <!-- KPI Summary Bar -->
            <div id="hk-summary-section" class="hk-summary-bar"></div>

            <!-- Toolbar: Search & Floor Filter -->
            <div class="row" style="margin-bottom: 20px; align-items: center;">
                <div class="col-md-5 col-sm-6" style="margin-bottom: 8px;">
                    <div style="position: relative;">
                        <span class="fas fa-search" style="position: absolute; left: 12px; top: 11px; color: #94a3b8;"></span>
                        <input type="text" id="hk-search-box" class="form-control" style="padding-left: 36px; padding-right: 68px; border-radius: 8px; border: 1px solid #cbd5e1; height: 38px;"
                            placeholder="${__('Tìm kiếm số phòng, loại phòng...')}">
                        <div style="position: absolute; right: 10px; top: 8px; display: flex; align-items: center; gap: 6px;">
                            <span id="hk-search-clear" style="display:none; cursor:pointer; color:#94a3b8; font-size:14px; padding: 2px 4px;" title="${__('Xóa tìm kiếm')}"><i class="fas fa-times-circle"></i></span>
                            <kbd style="font-size: 11px; padding: 2px 6px; border-radius: 4px; background: #f1f5f9; border: 1px solid #cbd5e1; color: #64748b; font-family: inherit; font-weight: 700; cursor: default;" title="${__('Phím tắt mở tìm kiếm')}">/</kbd>
                        </div>
                    </div>
                </div>
                <div class="col-md-3 col-sm-4" style="margin-bottom: 8px;">
                    <select id="hk-floor-select" class="form-control" style="border-radius: 8px; border: 1px solid #cbd5e1; height: 38px;">
                        <option value="all">${__('Tất Cả Các Tầng')}</option>
                    </select>
                </div>
                <div class="col-md-4 col-sm-12 text-right" style="margin-bottom: 8px;">
                    <button class="btn btn-default btn-sm" id="hk-select-dirty-btn" style="border-radius: 6px; font-weight: 600; color:#b91c1c;">
                        <i class="fa fa-broom"></i> ${__('Chọn Phòng Bẩn')}
                    </button>
                    <button class="btn btn-default btn-sm" id="hk-select-all-btn" style="border-radius: 6px; font-weight: 600; margin-left: 6px;">
                        <i class="fa fa-check-square"></i> ${__('Tất Cả')}
                    </button>
                    <button class="btn btn-default btn-sm" id="hk-clear-filter-btn" style="border-radius: 6px; font-weight: 600; margin-left: 6px;">
                        <i class="fa fa-undo"></i> ${__('Đặt Lại')}
                    </button>
                </div>
            </div>

            <!-- Rooms Grid -->
            <div id="hk-rooms-grid" class="row"></div>

            <!-- Floating Batch Action Bar -->
            <div id="hk-batch-bar" class="hk-batch-bar">
                <span style="font-weight: 700; font-size: 13px;">${__('Đã chọn')} <span id="hk-selected-count">0</span> ${__('phòng')}</span>
                <button class="btn btn-success btn-xs" id="hk-batch-clean-btn" style="border-radius: 20px; font-weight: 600; padding: 5px 12px;">
                    <i class="fa fa-check"></i> ${__('Đánh Dấu Sạch')}
                </button>
                <button class="btn btn-info btn-xs" id="hk-batch-inspect-btn" style="border-radius: 20px; font-weight: 600; padding: 5px 12px;">
                    <i class="fa fa-shield-alt"></i> ${__('Đã Kiểm Tra')}
                </button>
                <button class="btn btn-warning btn-xs" id="hk-batch-dirty-btn" style="border-radius: 20px; font-weight: 600; padding: 5px 12px;">
                    <i class="fa fa-broom"></i> ${__('Cần Dọn')}
                </button>
                <button class="btn btn-link btn-xs" id="hk-batch-cancel-btn" style="color: #cbd5e1; text-decoration: underline;">
                    ${__('Bỏ chọn')}
                </button>
            </div>
        </div>
    `);

    setup_hk_events(wrapper);
    load_housekeeping_board(wrapper, page);
};

function setup_hk_events(wrapper) {
    $('#hk-search-box').on('input', function () {
        let q = $(this).val();
        if (q && q.length > 0) $('#hk-search-clear').show();
        else $('#hk-search-clear').hide();
        render_filtered_rooms();
    });

    $('#hk-search-clear').on('click', function () {
        $('#hk-search-box').val('').focus();
        $(this).hide();
        render_filtered_rooms();
    });

    // Keyboard shortcut: '/' to focus, 'Escape' to clear/blur
    $(document).off('keydown.hk_hotkey').on('keydown.hk_hotkey', function (e) {
        if (!$('#hk-search-box').is(':visible')) return;
        if ($('.modal.show, .modal.in').length) return;

        if (e.key === 'Escape') {
            if ($(e.target).is('#hk-search-box') || $('#hk-search-box').val()) {
                $('#hk-search-box').val('').blur();
                $('#hk-search-clear').hide();
                render_filtered_rooms();
                e.preventDefault();
            }
            return;
        }
        if ($(e.target).is('input, textarea, select, [contenteditable]')) return;
        if (e.key === '/') {
            e.preventDefault();
            $('#hk-search-box').focus().select();
        }
    });

    $('#hk-floor-select').on('change', function () {
        render_filtered_rooms();
    });

    $('#hk-select-dirty-btn').on('click', function () {
        let visible_rooms = get_visible_rooms();
        let target_dirty = visible_rooms.filter(r => r.status === 'Dirty');

        if (target_dirty.length === 0) {
            let any_dirty = _hk_rooms_cache.some(r => r.status === 'Dirty');
            if (any_dirty) {
                frappe.show_alert({ message: __('Không có phòng cần dọn phù hợp với bộ lọc hiện tại.'), indicator: 'blue' });
            } else {
                frappe.show_alert({ message: __('Tất cả các phòng đều đã sạch!'), indicator: 'green' });
            }
            return;
        }

        let all_dirty_selected = target_dirty.every(r => _hk_selected_rooms.has(r.name));
        if (all_dirty_selected) {
            target_dirty.forEach(r => _hk_selected_rooms.delete(r.name));
        } else {
            target_dirty.forEach(r => _hk_selected_rooms.add(r.name));
        }
        update_selection_ui();
    });

    $('#hk-select-all-btn').on('click', function () {
        let visible_rooms = get_visible_rooms();
        if (_hk_selected_rooms.size === visible_rooms.length && visible_rooms.length > 0) {
            _hk_selected_rooms.clear();
        } else {
            visible_rooms.forEach(r => _hk_selected_rooms.add(r.name));
        }
        update_selection_ui();
    });

    $('#hk-clear-filter-btn').on('click', function () {
        _hk_status_filter = 'all';
        $('#hk-search-box').val('');
        $('#hk-search-clear').hide();
        $('#hk-floor-select').val('all');
        $('.hk-counter-chip').removeClass('active');
        $('#hk-chip-all').addClass('active');
        render_filtered_rooms();
    });

    $('#hk-batch-clean-btn').on('click', () => run_batch_update('Available'));
    $('#hk-batch-inspect-btn').on('click', () => run_batch_update('Inspected'));
    $('#hk-batch-dirty-btn').on('click', () => run_batch_update('Dirty'));
    $('#hk-batch-cancel-btn').on('click', () => {
        _hk_selected_rooms.clear();
        update_selection_ui();
    });
}

function show_hk_skeletons() {
    let skelHtml = '';
    for (let i = 0; i < 12; i++) {
        skelHtml += `
            <div class="col-xs-6 col-sm-4 col-md-3 col-lg-2" style="padding: 6px;">
                <div class="hk-room-card" style="border-top: 4px solid #cbd5e1; min-height: 155px; opacity: 0.8;">
                    <div style="display:flex; justify-content:space-between; margin-bottom: 8px;">
                        <div class="hk-skeleton" style="width: 18px; height: 18px; border-radius: 4px;"></div>
                        <div class="hk-skeleton" style="width: 50px; height: 16px; border-radius: 4px;"></div>
                    </div>
                    <div class="hk-skeleton" style="width: 70px; height: 26px; border-radius: 4px; margin-bottom: 6px;"></div>
                    <div class="hk-skeleton" style="width: 100px; height: 14px; border-radius: 4px;"></div>
                    <div style="margin-top: 20px;">
                        <div class="hk-skeleton" style="width: 100%; height: 24px; border-radius: 4px;"></div>
                    </div>
                </div>
            </div>
        `;
    }
    $('#hk-rooms-grid').html(skelHtml);
}

function load_housekeeping_board(wrapper, page) {
    show_hk_skeletons();
    frappe.call({
        method: "hospitality_core.hospitality_core.page.housekeeping_view.housekeeping_view.get_room_statuses",
        callback: function (r) {
            if (r.message) {
                _hk_rooms_cache = r.message || [];
                _hk_selected_rooms.clear();
                populate_floor_select();
                render_kpi_summary();
                render_filtered_rooms();
                update_selection_ui();
            }
        }
    });
}

function populate_floor_select() {
    let select = $('#hk-floor-select');
    let cur_val = select.val();
    select.empty().append(`<option value="all">${__('Tất Cả Các Tầng')}</option>`);

    let floors = new Set();
    _hk_rooms_cache.forEach(r => { if (r.floor) floors.add(r.floor); });

    Array.from(floors).sort((a,b) => String(a).localeCompare(String(b), undefined, {numeric: true})).forEach(f => {
        select.append(`<option value="${f}">${__('Tầng')} ${f}</option>`);
    });

    if (cur_val && select.find(`option[value="${cur_val}"]`).length) {
        select.val(cur_val);
    }
}

function render_kpi_summary() {
    let counts = { all: _hk_rooms_cache.length };
    Object.keys(HK_STATUS_CONFIG).forEach(st => { counts[st] = 0; });

    _hk_rooms_cache.forEach(r => {
        if (counts[r.status] !== undefined) counts[r.status] += 1;
    });

    let html = `
        <div class="hk-counter-chip ${_hk_status_filter === 'all' ? 'active' : ''}" id="hk-chip-all" onclick="hk_filter_status('all')">
            <div class="hk-counter-num" style="color:#1e293b;">${counts.all}</div>
            <div class="hk-counter-label">${__('Tổng Số Phòng')}</div>
        </div>
    `;

    Object.keys(HK_STATUS_CONFIG).forEach(st => {
        let conf = HK_STATUS_CONFIG[st];
        let is_active = (_hk_status_filter === st) ? 'active' : '';
        html += `
            <div class="hk-counter-chip ${is_active}" id="hk-chip-${st.replace(/\s+/g, '-')}" onclick="hk_filter_status('${st}')">
                <div class="hk-counter-num" style="color:${conf.color};">${counts[st]}</div>
                <div class="hk-counter-label">${conf.label}</div>
            </div>
        `;
    });

    $('#hk-summary-section').html(html);
}

window.hk_filter_status = function (status) {
    _hk_status_filter = status;
    $('.hk-counter-chip').removeClass('active');
    if (status === 'all') {
        $('#hk-chip-all').addClass('active');
    } else {
        $(`#hk-chip-${status.replace(/\s+/g, '-')}`).addClass('active');
    }
    render_filtered_rooms();
};

function get_visible_rooms() {
    let search = ($('#hk-search-box').val() || '').trim().toLowerCase();
    let floor = $('#hk-floor-select').val();

    return _hk_rooms_cache.filter(r => {
        let match_status = (_hk_status_filter === 'all' || r.status === _hk_status_filter);
        let match_floor = (floor === 'all' || String(r.floor) === String(floor));
        let match_search = (!search || (r.room_number && r.room_number.toLowerCase().includes(search)) || (r.room_type && r.room_type.toLowerCase().includes(search)));
        return match_status && match_floor && match_search;
    });
}

function render_filtered_rooms() {
    let container = $('#hk-rooms-grid');
    container.empty();

    let visible = get_visible_rooms();

    if (visible.length === 0) {
        container.html(`
            <div class="col-12 text-center" style="padding: 48px 20px;">
                <div style="width: 56px; height: 56px; border-radius: 50%; background: #f1f5f9; display: inline-flex; align-items: center; justify-content: center; margin-bottom: 12px;">
                    <i class="fa fa-broom" style="font-size: 22px; color: #94a3b8;"></i>
                </div>
                <h5 style="color: #334155; font-weight: 600; margin-bottom: 6px;">${__('Không tìm thấy phòng phù hợp')}</h5>
                <p style="color: #64748b; font-size: 13px; max-width: 360px; margin: 0 auto 14px;">${__('Thử thay đổi bộ lọc tầng hoặc từ khóa tìm kiếm để xem danh sách phòng.')}</p>
                <button class="btn btn-default btn-sm" onclick="$('#hk-clear-filter-btn').click();" style="border-radius: 6px; font-weight: 600;">
                    <i class="fa fa-undo"></i> ${__('Đặt lại tất cả bộ lọc')}
                </button>
            </div>
        `);
        return;
    }

    visible.forEach(room => {
        let conf = HK_STATUS_CONFIG[room.status] || { label: room.status, color: '#64748b', border: '#cbd5e1', bg: '#fff', badge_bg: '#64748b' };
        let is_selected = _hk_selected_rooms.has(room.name) ? 'selected' : '';

        let html = `
            <div class="col-xs-6 col-sm-4 col-md-3 col-lg-2" style="padding: 6px;">
                <div class="hk-room-card ${is_selected}" data-room="${frappe.utils.escape_html(room.name)}" id="card-room-${frappe.utils.escape_html(room.name)}" style="border-top: 4px solid ${conf.border}; cursor: pointer;" onclick="hk_toggle_room('${room.name}')">
                    <div>
                        <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom: 6px;">
                            <input type="checkbox" class="hk-room-checkbox" data-room="${room.name}" ${_hk_selected_rooms.has(room.name) ? 'checked' : ''} onclick="event.stopPropagation(); hk_toggle_room('${room.name}')">
                            <span class="badge" style="background:${conf.badge_bg}; color:#fff; font-size:10px; padding:2px 6px; border-radius:4px; font-weight:600;">${conf.label}</span>
                        </div>
                        <div style="display:flex; justify-content:space-between; align-items:center;">
                            <div style="font-size:20px; font-weight:800; color:#1e293b; line-height: 1.1;">${frappe.utils.escape_html(room.room_number)}</div>
                            <a href="#" onclick="event.stopPropagation(); frappe.set_route('Form', 'Hotel Room', '${frappe.utils.escape_html(room.name)}'); return false;" style="color:#94a3b8; font-size:12px; padding:2px 4px;" title="${__('Xem chi tiết buồng phòng')}"><i class="fa fa-external-link-alt"></i></a>
                        </div>
                        <div style="font-size:11px; color:#64748b; margin-top:2px;">
                            ${frappe.utils.escape_html(room.room_type || '')} ${room.floor ? '&middot; T.' + room.floor : ''}
                        </div>
                    </div>
                    <div style="margin-top: 10px;">
                        ${get_action_button(room)}
                    </div>
                </div>
            </div>
        `;
        container.append(html);
    });
}

function get_action_button(room) {
    if (room.status === 'Dirty') {
        return `<button class="btn btn-success btn-xs btn-block" style="border-radius:5px; font-weight:600;" onclick="event.stopPropagation(); update_room_status('${room.name}', 'Cleaning', this)"><i class="fa fa-broom"></i> ${__('Bắt Đầu Dọn')}</button>`;
    } else if (room.status === 'Cleaning') {
        return `<button class="btn btn-info btn-xs btn-block" style="border-radius:5px; font-weight:600;" onclick="event.stopPropagation(); update_room_status('${room.name}', 'Inspected', this)"><i class="fa fa-shield-alt"></i> ${__('Dọn Xong')}</button>`;
    } else if (room.status === 'Inspected') {
        return `<button class="btn btn-primary btn-xs btn-block" style="border-radius:5px; font-weight:600;" onclick="event.stopPropagation(); update_room_status('${room.name}', 'Available', this)"><i class="fa fa-check"></i> ${__('Duyệt Sạch')}</button>`;
    } else if (room.status === 'Available') {
        return `<button class="btn btn-warning btn-xs btn-block" style="border-radius:5px; font-weight:600;" onclick="event.stopPropagation(); update_room_status('${room.name}', 'Dirty', this)"><i class="fa fa-undo"></i> ${__('Báo Bẩn')}</button>`;
    } else if (room.status === 'Occupied') {
        return `<button class="btn btn-warning btn-xs btn-block" style="border-radius:5px; font-weight:600;" onclick="event.stopPropagation(); update_room_status('${room.name}', 'Dirty', this)"><i class="fa fa-broom"></i> ${__('Yêu Cầu Dọn')}</button>`;
    } else {
        return `<button class="btn btn-default btn-xs btn-block disabled" style="border-radius:5px; font-size:11px;">${__('Đang Khóa')}</button>`;
    }
}

window.hk_toggle_room = function (room_name) {
    if (_hk_selected_rooms.has(room_name)) {
        _hk_selected_rooms.delete(room_name);
    } else {
        _hk_selected_rooms.add(room_name);
    }
    update_selection_ui();
};

function update_selection_ui() {
    let count = _hk_selected_rooms.size;
    $('#hk-selected-count').text(count);

    if (count > 0) {
        $('#hk-batch-bar').addClass('visible');
    } else {
        $('#hk-batch-bar').removeClass('visible');
    }

    $('#hk-rooms-grid .hk-room-card').each(function () {
        let r_name = $(this).data('room');
        let is_sel = _hk_selected_rooms.has(r_name);
        $(this).toggleClass('selected', is_sel);
        $(this).find('.hk-room-checkbox').prop('checked', is_sel);
    });
}

function run_batch_update(target_status) {
    if (_hk_selected_rooms.size === 0) return;

    let room_names = Array.from(_hk_selected_rooms);
    let target_label = (HK_STATUS_CONFIG[target_status] && HK_STATUS_CONFIG[target_status].label) || target_status;
    frappe.confirm(
        __('Bạn có chắc muốn cập nhật trạng thái "{0}" cho {1} phòng đã chọn?', [target_label, room_names.length]),
        function () {
            frappe.call({
                method: "hospitality_core.hospitality_core.page.housekeeping_view.housekeeping_view.batch_set_room_status",
                args: { rooms: room_names, status: target_status },
                freeze: true,
                freeze_message: __('Đang cập nhật hàng loạt...'),
                callback: function (r) {
                    if (!r.exc && r.message && r.message.success) {
                        frappe.show_alert({ message: r.message.message, indicator: 'green' });
                        _hk_selected_rooms.clear();
                        load_housekeeping_board();
                    }
                }
            });
        }
    );
}

window.update_room_status = function (room_name, new_status, btn_el) {
    let $btn = btn_el ? $(btn_el) : $(`#card-room-${room_name} .btn`);
    let orig_html = $btn.html();
    $btn.prop('disabled', true).html(`<i class="fa fa-spinner fa-spin"></i> ${__('Đang lưu...')}`);

    frappe.call({
        method: "hospitality_core.hospitality_core.page.housekeeping_view.housekeeping_view.set_room_status",
        args: { room: room_name, status: new_status },
        callback: function (r) {
            if (!r.exc) {
                let final_status = (r.message && r.message.status) || new_status;
                let status_label = (HK_STATUS_CONFIG[final_status] && HK_STATUS_CONFIG[final_status].label) || final_status;
                frappe.show_alert({ message: __('Đã đổi trạng thái phòng sang {0}', [status_label]), indicator: 'green' });
                // Cập nhật ngay trong cache để giao diện đổi tức thì theo trạng thái thực tế từ server
                let found = _hk_rooms_cache.find(x => x.name === room_name);
                if (found) found.status = final_status;
                render_kpi_summary();
                render_filtered_rooms();
                // Trigger flash animation on updated room card
                let card = $('#hk-rooms-grid .hk-room-card').filter(function () {
                    return $(this).data('room') === room_name;
                });
                if (card.length) {
                    card.addClass('hk-flash-success');
                    setTimeout(() => card.removeClass('hk-flash-success'), 600);
                }
            } else {
                $btn.prop('disabled', false).html(orig_html);
            }
        },
        error: function () {
            $btn.prop('disabled', false).html(orig_html);
        }
    });
};