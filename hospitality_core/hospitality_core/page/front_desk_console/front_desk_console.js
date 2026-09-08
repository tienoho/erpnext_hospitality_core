frappe.pages['front-desk-console'].on_page_load = function (wrapper) {
    var page = frappe.ui.make_app_page({
        parent: wrapper,
        title: 'Front Desk Console',
        single_column: true
    });

    // 1. Add Date Filter
    page.add_field({
        fieldname: 'console_date',
        label: __('Ngày'),
        fieldtype: 'Date',
        default: frappe.datetime.now_date(),
        change: function () {
            render_console(wrapper, page);
        }
    });

    // Refresh Button
    page.set_primary_action(__('Làm Mới'), function () {
        render_console(wrapper, page);
    });

    // Inner Buttons (Các thao tác lễ tân thường trực)
    page.add_inner_button(__('⚡ Tạo VietQR Nhanh'), function () {
        open_quick_vietqr_dialog();
    });
    page.add_inner_button(__('Quét CCCD / Passport'), function () {
        open_id_scanner_dialog();
    });
    page.add_inner_button(__('Tách Bill'), function () {
        open_split_bill_dialog();
    });
    page.add_inner_button(__('Gộp Folio'), function () {
        open_merge_folio_dialog();
    });

    // Page Menu (Báo cáo & Tác vụ xuất dữ liệu Công an / XNC)
    page.add_menu_item(__('📊 Xuất Excel Khai Báo XNC (XLSX)'), function () {
        let cur_date = page.fields_dict.console_date.get_value() || frappe.datetime.now_date();
        window.open(`/api/method/hospitality_core.hospitality_core.api.police_declaration.export_quangninh_immigration_report_xlsx?target_date=${cur_date}`);
    });
    page.add_menu_item(__('📋 Xuất File CSV Khai Báo XNC'), function () {
        let cur_date = page.fields_dict.console_date.get_value() || frappe.datetime.now_date();
        window.open(`/api/method/hospitality_core.hospitality_core.api.police_declaration.export_quangninh_immigration_report?target_date=${cur_date}`);
    });
    page.add_menu_item(__('📑 Xuất Excel Khai Báo Tạm Trú Toàn Đoàn (XLSX)'), function () {
        let cur_date = page.fields_dict.console_date.get_value() || frappe.datetime.now_date();
        window.open(`/api/method/hospitality_core.hospitality_core.api.police_declaration.export_police_declaration_xlsx?target_date=${cur_date}`);
    });

    // CSS Styling
    $(`<style>
        .fd-quick-actions-bar {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(130px, 1fr));
            gap: 12px;
            margin-bottom: 24px;
        }
        .fd-toolbar-btn {
            display: flex;
            flex-direction: column;
            align-items: center;
            justify-content: center;
            text-align: center;
            padding: 14px 8px;
            background: #fff;
            border: 1px solid #e2e8f0;
            border-radius: 8px;
            cursor: pointer;
            color: #334155;
            font-weight: 600;
            font-size: 12px;
            transition: all 0.2s ease;
            box-shadow: 0 1px 3px rgba(0,0,0,0.04);
            text-decoration: none !important;
        }
        .fd-toolbar-btn:hover {
            background: #f8fafc;
            border-color: #3b82f6;
            color: #1d4ed8;
            transform: translateY(-2px);
            box-shadow: 0 4px 10px rgba(59,130,246,0.12);
        }
        .fd-toolbar-btn:active {
            transform: scale(0.96) translateY(0);
        }
        .fd-toolbar-icon {
            font-size: 22px;
            margin-bottom: 8px;
            color: #3b82f6;
            transition: transform 0.2s;
        }
        .fd-toolbar-btn:hover .fd-toolbar-icon {
            transform: scale(1.1);
        }

        /* Skeleton Shimmer Loading */
        @keyframes fd-shimmer {
            0% { background-position: -200% 0; }
            100% { background-position: 200% 0; }
        }
        .skeleton-shimmer {
            background: linear-gradient(90deg, #f1f5f9 25%, #e2e8f0 50%, #f1f5f9 75%);
            background-size: 200% 100%;
            animation: fd-shimmer 1.5s infinite;
            border-radius: 6px;
            display: inline-block;
        }
        .skeleton-card-num {
            width: 52px;
            height: 32px;
            margin-bottom: 4px;
        }
        .skeleton-list-item {
            padding: 14px 16px;
            border-bottom: 1px solid #f1f5f9;
            display: flex;
            align-items: center;
            justify-content: space-between;
        }

        /* Smart Empty States */
        .smart-empty-state {
            text-align: center;
            padding: 38px 20px;
            color: #64748b;
        }
        .smart-empty-icon {
            width: 54px;
            height: 54px;
            border-radius: 50%;
            background: #f8fafc;
            border: 1px solid #e2e8f0;
            display: inline-flex;
            align-items: center;
            justify-content: center;
            margin-bottom: 12px;
            font-size: 22px;
            color: #94a3b8;
        }
        .smart-empty-title {
            font-size: 14px;
            font-weight: 700;
            color: #334155;
            margin-bottom: 4px;
        }
        .smart-empty-subtitle {
            font-size: 12px;
            color: #94a3b8;
            max-width: 320px;
            margin: 0 auto;
        }
        .smart-empty-badge {
            display: inline-block;
            margin-top: 10px;
            background: #f1f5f9;
            color: #475569;
            padding: 3px 12px;
            border-radius: 12px;
            font-size: 11px;
            font-weight: 600;
        }

        .fd-stat-card {
            background: #fff;
            border: 1px solid #e2e8f0;
            border-radius: 10px;
            padding: 18px 20px;
            box-shadow: 0 2px 6px rgba(0,0,0,0.04);
            transition: all 0.2s ease;
            position: relative;
            cursor: pointer;
            overflow: hidden;
            height: 100%;
        }
        .fd-stat-card:hover {
            transform: translateY(-3px);
            box-shadow: 0 8px 20px rgba(0,0,0,0.08);
        }
        .fd-stat-card.active-filter {
            border-color: #2563eb;
            box-shadow: 0 0 0 2px rgba(37,99,235,0.2), 0 8px 20px rgba(0,0,0,0.08);
            background: #f8faff;
        }
        .fd-stat-card-top {
            display: flex;
            align-items: center;
            justify-content: space-between;
            margin-bottom: 8px;
        }
        .fd-stat-label {
            font-size: 12px;
            font-weight: 700;
            color: #64748b;
            text-transform: uppercase;
            letter-spacing: 0.5px;
        }
        .fd-stat-icon-wrap {
            width: 36px;
            height: 36px;
            border-radius: 8px;
            display: flex;
            align-items: center;
            justify-content: center;
            font-size: 16px;
            transition: transform 0.25s cubic-bezier(0.34, 1.56, 0.64, 1);
        }
        .fd-stat-card:hover .fd-stat-icon-wrap {
            transform: scale(1.12) rotate(4deg);
        }
        .fd-stat-card:active {
            transform: scale(0.98);
        }
        .fd-stat-number {
            font-size: 32px;
            font-weight: 800;
            line-height: 1.1;
            margin-bottom: 4px;
        }
        .fd-stat-subtext {
            font-size: 12px;
            color: #94a3b8;
            font-weight: 500;
        }

        .fd-list-header {
            background: #f8fafc;
            padding: 12px 18px;
            font-weight: 700;
            font-size: 14px;
            color: #1e293b;
            border-radius: 8px 8px 0 0;
            border: 1px solid #e2e8f0;
            border-bottom: none;
            display: flex;
            align-items: center;
            justify-content: space-between;
        }
        .fd-list-container {
            border: 1px solid #e2e8f0;
            border-radius: 0 0 8px 8px;
            background: #fff;
            min-height: 320px;
            max-height: 520px;
            overflow-y: auto;
        }
        .fd-list-item {
            padding: 14px 18px;
            border-bottom: 1px solid #f1f5f9;
            display: flex;
            align-items: center;
            justify-content: space-between;
            transition: all 0.2s cubic-bezier(0.4, 0, 0.2, 1);
            border-left: 3px solid transparent;
        }
        .fd-list-item:hover {
            background: #f8fafc;
            border-left: 3px solid #3b82f6;
            padding-left: 21px;
        }
        .fd-list-item:last-child { border-bottom: none; }
        .fd-list-item .btn {
            transition: transform 0.12s ease;
        }
        .fd-list-item .btn:active {
            transform: scale(0.94);
        }

        /* Omni Search Micro-interactions */
        #fd-omni-search {
            transition: border-color 0.2s ease, box-shadow 0.2s ease;
        }
        #fd-omni-search:focus {
            border-color: #3b82f6 !important;
            box-shadow: 0 0 0 3px rgba(59, 130, 246, 0.15) !important;
            outline: none !important;
        }
        #fd-search-clear {
            transition: color 0.15s ease, transform 0.15s ease;
        }
        #fd-search-clear:hover {
            color: #475569 !important;
            transform: scale(1.15);
        }
        .fd-omni-result-item {
            transition: all 0.15s ease;
            border-left: 3px solid transparent;
        }
        .fd-omni-result-item:hover, .fd-omni-result-item.active-result {
            background: #eff6ff !important;
            border-left: 3px solid #2563eb !important;
            padding-left: 21px;
        }

        #btn-reset-filters {
            transition: all 0.15s ease;
        }
        #btn-reset-filters:active {
            transform: scale(0.96);
        }
        
        .badge-pending {
            background: #fffbeb;
            color: #b45309;
            border: 1px solid #fde68a;
            padding: 3px 10px;
            border-radius: 12px;
            font-size: 11px;
            font-weight: 600;
        }
        .badge-done {
            background: #ecfdf5;
            color: #047857;
            border: 1px solid #a7f3d0;
            padding: 3px 10px;
            border-radius: 12px;
            font-size: 11px;
            font-weight: 600;
        }
        .badge-missed {
            background: #fef2f2;
            color: #b91c1c;
            border: 1px solid #fecaca;
            padding: 3px 10px;
            border-radius: 12px;
            font-size: 11px;
            font-weight: 600;
        }

        /* Live Clock & Filter Pills */
        @keyframes fd-pulse {
            0% { box-shadow: 0 0 0 0 rgba(16, 185, 129, 0.7); }
            70% { box-shadow: 0 0 0 6px rgba(16, 185, 129, 0); }
            100% { box-shadow: 0 0 0 0 rgba(16, 185, 129, 0); }
        }
        .fd-pulse-dot {
            width: 8px;
            height: 8px;
            background: #10b981;
            border-radius: 50%;
            display: inline-block;
            animation: fd-pulse 2s infinite;
        }
        .fd-filter-pill {
            display: inline-flex;
            align-items: center;
            gap: 4px;
            background: #eff6ff;
            color: #2563eb;
            border: 1px solid #bfdbfe;
            border-radius: 12px;
            padding: 2px 8px;
            font-size: 11px;
            font-weight: 600;
            cursor: pointer;
            transition: all 0.15s ease;
            margin-left: 6px;
        }
        .fd-filter-pill:hover {
            background: #dbeafe;
            color: #1d4ed8;
            transform: scale(1.03);
        }
    </style>`).appendTo(wrapper);

    // Main Layout Skeleton
    $(wrapper).find('.layout-main-section').append(`
        <div id="fd-content" style="padding-top: 10px;">
            <!-- Live Ticker Bar -->
            <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 14px; padding: 0 4px;">
                <div style="display: flex; align-items: center; gap: 8px; font-size: 12px; color: #475569; font-weight: 600;">
                    <span class="fd-pulse-dot" title="${__('Hệ thống hoạt động trực tuyến')}"></span>
                    <span style="color:#047857; font-weight:700; letter-spacing: 0.5px;">LIVE</span>
                    <span style="color:#cbd5e1;">&bull;</span>
                    <i class="fa fa-clock" style="color:#64748b;"></i>
                    <span id="fd-live-clock" style="font-family: monospace; font-size: 13px; font-weight: 700; color: #1e293b;">--:--:--</span>
                </div>
                <div style="font-size: 12px; color: #64748b;">
                    <span style="color: #94a3b8;">${__('Đồng bộ gần nhất:')}</span> <b id="fd-last-synced" style="color:#334155;">${__('Đang cập nhật...')}</b>
                </div>
            </div>

            <!-- Omni Search Bar -->
            <div class="row" style="margin-bottom: 20px;">
                <div class="col-md-9 col-xs-12" style="position: relative;">
                    <div style="position: relative;">
                        <span id="fd-search-icon" class="fas fa-search" style="position: absolute; left: 14px; top: 13px; color: #94a3b8; font-size: 14px; transition: color 0.2s;"></span>
                        <input type="text" id="fd-omni-search" class="form-control" style="padding-left: 38px; padding-right: 70px; height: 42px; border-radius: 8px; border: 1px solid #cbd5e1; font-size: 13px;"
                            placeholder="${__('Tìm kiếm thông minh: Tên khách, Số điện thoại, Số phòng, CCCD/Hộ chiếu, Mã đặt phòng OTA...')}">
                        <div style="position: absolute; right: 12px; top: 9px; display: flex; align-items: center; gap: 8px;">
                            <span id="fd-search-clear" style="display:none; cursor:pointer; color:#94a3b8; font-size:15px; padding: 2px 4px;" title="${__('Xóa tìm kiếm')}"><i class="fas fa-times-circle"></i></span>
                            <kbd style="font-size: 11px; padding: 2px 7px; border-radius: 5px; background: #f1f5f9; border: 1px solid #cbd5e1; color: #64748b; font-family: inherit; font-weight: 700; cursor: default;" title="${__('Phím tắt mở tìm kiếm')}">/</kbd>
                        </div>
                    </div>
                    <div id="fd-omni-results" style="display:none; position:absolute; top:100%; left:0; right:0; z-index:50; background:#fff; border:1px solid #cbd5e1; border-radius:0 0 8px 8px; max-height:340px; overflow-y:auto; box-shadow:0 10px 25px rgba(0,0,0,0.1);"></div>
                </div>
                <div class="col-md-3 col-xs-12 text-right">
                    <button class="btn btn-default btn-sm" id="btn-reset-filters" style="height: 42px; width: 100%; border-radius: 8px; font-weight: 600;">
                        <i class="fa fa-undo"></i> ${__('Đặt Lại Bộ Lọc')}
                    </button>
                </div>
            </div>

            <!-- Quick Actions Grid (8 nút phân bổ cân đối tuyệt đối) -->
            <div class="fd-quick-actions-bar">
                <a class="fd-toolbar-btn" onclick="frappe.set_route('tape-chart')">
                    <span class="fd-toolbar-icon fas fa-th"></span>
                    <span>${__('Sơ Đồ Buồng')}</span>
                </a>
                <a class="fd-toolbar-btn" onclick="frappe.set_route('availability-tool')">
                    <span class="fd-toolbar-icon fas fa-search"></span>
                    <span>${__('Tra Cứu Phòng')}</span>
                </a>
                <a class="fd-toolbar-btn" onclick="frappe.set_route('housekeeping-view')">
                    <span class="fd-toolbar-icon fas fa-broom"></span>
                    <span>${__('Buồng Phòng')}</span>
                </a>
                <a class="fd-toolbar-btn" onclick="frappe.set_route('List', 'Hotel Reservation')">
                    <span class="fd-toolbar-icon fas fa-calendar-check"></span>
                    <span>${__('Đặt Phòng')}</span>
                </a>
                <a class="fd-toolbar-btn" onclick="frappe.set_route('query-report', 'House List')">
                    <span class="fd-toolbar-icon fas fa-users"></span>
                    <span>${__('Khách Lưu Trú')}</span>
                </a>
                <a class="fd-toolbar-btn" onclick="frappe.set_route('List', 'Hotel Maintenance Request')">
                    <span class="fd-toolbar-icon fas fa-tools"></span>
                    <span>${__('Bảo Trì Phòng')}</span>
                </a>
                <a class="fd-toolbar-btn" onclick="frappe.set_route('guest-360')">
                    <span class="fd-toolbar-icon fas fa-id-card"></span>
                    <span>${__('Hồ Sơ Khách 360')}</span>
                </a>
                <a class="fd-toolbar-btn" onclick="frappe.set_route('housekeeping-mobile')">
                    <span class="fd-toolbar-icon fas fa-mobile-alt"></span>
                    <span>${__('Buồng Di Động')}</span>
                </a>
            </div>

            <!-- Stats Row: 4 Thẻ KPI Thông Minh (Click-to-Filter) -->
            <div class="row" style="margin-bottom: 25px;">
                <div class="col-md-3 col-sm-6" style="margin-bottom: 12px;">
                    <div class="fd-stat-card" id="card-arr-pending" title="${__('Bấm để lọc danh sách khách sắp nhận phòng')}">
                        <div class="fd-stat-card-top">
                            <span class="fd-stat-label">${__('Khách Sắp Đến')}</span>
                            <div class="fd-stat-icon-wrap" style="background: #fffbeb; color: #f59e0b;">
                                <i class="fas fa-plane-arrival"></i>
                            </div>
                        </div>
                        <div class="fd-stat-number" id="stat-arr-pending" style="color: #d97706;">0</div>
                        <div class="fd-stat-subtext">${__('Chờ Check-in trong ngày')}</div>
                    </div>
                </div>
                <div class="col-md-3 col-sm-6" style="margin-bottom: 12px;">
                    <div class="fd-stat-card" id="card-dep-pending" title="${__('Bấm để lọc danh sách khách sắp trả phòng')}">
                        <div class="fd-stat-card-top">
                            <span class="fd-stat-label">${__('Khách Sắp Đi')}</span>
                            <div class="fd-stat-icon-wrap" style="background: #fef2f2; color: #ef4444;">
                                <i class="fas fa-plane-departure"></i>
                            </div>
                        </div>
                        <div class="fd-stat-number" id="stat-dep-pending" style="color: #dc2626;">0</div>
                        <div class="fd-stat-subtext">${__('Chờ Check-out trong ngày')}</div>
                    </div>
                </div>
                <div class="col-md-3 col-sm-6" style="margin-bottom: 12px;">
                    <div class="fd-stat-card" id="card-in-house" onclick="frappe.set_route('query-report', 'House List')" title="${__('Bấm để mở báo cáo danh sách khách đang lưu trú')}">
                        <div class="fd-stat-card-top">
                            <span class="fd-stat-label">${__('Đang Lưu Trú')}</span>
                            <div class="fd-stat-icon-wrap" style="background: #eef2ff; color: #6366f1;">
                                <i class="fas fa-bed"></i>
                            </div>
                        </div>
                        <div class="fd-stat-number" id="stat-occupancy" style="color: #4f46e5;">0</div>
                        <div class="fd-stat-subtext" id="stat-occ-pct">0% ${__('Công suất')}</div>
                    </div>
                </div>
                <div class="col-md-3 col-sm-6" style="margin-bottom: 12px;">
                    <div class="fd-stat-card" id="card-available" onclick="frappe.set_route('availability-tool')" title="${__('Bấm để mở công cụ tra cứu buồng phòng chi tiết')}">
                        <div class="fd-stat-card-top">
                            <span class="fd-stat-label">${__('Phòng Khả Dụng')}</span>
                            <div class="fd-stat-icon-wrap" style="background: #ecfdf5; color: #10b981;">
                                <i class="fas fa-door-open"></i>
                            </div>
                        </div>
                        <div class="fd-stat-number" id="stat-available" style="color: #059669;">0</div>
                        <div class="fd-stat-subtext">${__('Sẵn sàng đón khách')}</div>
                    </div>
                </div>
            </div>

            <!-- Lists Row -->
            <div class="row">
                <!-- Arrivals Column -->
                <div class="col-md-6" style="margin-bottom: 20px;">
                    <div class="fd-list-header">
                        <span>
                            <i class="fas fa-plane-arrival" style="color:#d97706; margin-right:8px;"></i>${__('Danh Sách Khách Đến (Arrivals)')}
                            <span id="arrivals-filter-indicator"></span>
                        </span>
                        <span id="arrivals-count-badge" class="badge" style="background:#f1f5f9; color:#475569; font-size:11px;">0</span>
                    </div>
                    <div id="list-arrivals" class="fd-list-container">
                        <div class="text-center p-4 text-muted">${__('Đang tải dữ liệu...')}</div>
                    </div>
                </div>

                <!-- Departures Column -->
                <div class="col-md-6" style="margin-bottom: 20px;">
                    <div class="fd-list-header">
                        <span>
                            <i class="fas fa-plane-departure" style="color:#dc2626; margin-right:8px;"></i>${__('Danh Sách Khách Đi (Departures)')}
                            <span id="departures-filter-indicator"></span>
                        </span>
                        <span id="departures-count-badge" class="badge" style="background:#f1f5f9; color:#475569; font-size:11px;">0</span>
                    </div>
                    <div id="list-departures" class="fd-list-container">
                        <div class="text-center p-4 text-muted">${__('Đang tải dữ liệu...')}</div>
                    </div>
                </div>
            </div>
        </div>
    `);

    setup_kpi_filters();
    render_console(wrapper, page);
    setup_omni_search();
    start_live_clock();
    setup_list_actions();
}

function setup_omni_search() {
    let input = $('#fd-omni-search');
    let results = $('#fd-omni-results');
    let icon = $('#fd-search-icon');
    let clearBtn = $('#fd-search-clear');
    let debounce_timer = null;
    let selected_index = -1;

    function get_items() {
        return results.find('.fd-omni-result-item');
    }

    function set_active_item(idx) {
        let items = get_items();
        items.removeClass('active-result');
        if (idx >= 0 && idx < items.length) {
            selected_index = idx;
            let active = items.eq(idx).addClass('active-result');
            let container = results;
            let activeTop = active.position().top;
            let activeBottom = activeTop + active.outerHeight();
            if (activeBottom > container.innerHeight()) {
                container.scrollTop(container.scrollTop() + activeBottom - container.innerHeight());
            } else if (activeTop < 0) {
                container.scrollTop(container.scrollTop() + activeTop);
            }
        } else {
            selected_index = -1;
        }
    }

    input.on('input', function () {
        let query = $(this).val();
        selected_index = -1;
        clearTimeout(debounce_timer);

        if (query && query.length > 0) {
            clearBtn.show();
        } else {
            clearBtn.hide();
        }

        if (!query || query.length < 2) {
            results.hide().empty();
            icon.removeClass('fa-spinner fa-spin').addClass('fa-search').css('color', '#94a3b8');
            return;
        }

        // Real-time spinner micro-interaction
        icon.removeClass('fa-search').addClass('fa-spinner fa-spin').css('color', '#3b82f6');

        debounce_timer = setTimeout(() => {
            frappe.call({
                method: 'hospitality_core.hospitality_core.api.folio_operations.omni_search',
                args: { query: query },
                callback: function (r) {
                    icon.removeClass('fa-spinner fa-spin').addClass('fa-search').css('color', '#94a3b8');
                    render_omni_results(r.message || []);
                }
            });
        }, 280);
    });

    clearBtn.on('click', function () {
        input.val('').focus();
        clearBtn.hide();
        results.hide().empty();
        icon.removeClass('fa-spinner fa-spin').addClass('fa-search').css('color', '#94a3b8');
    });

    $(document).on('click', function (e) {
        if (!$(e.target).closest('#fd-omni-search, #fd-omni-results, #fd-search-clear').length) {
            results.hide();
        }
    });

    // Arrow navigation & Enter key handling in Omni-Search
    input.on('keydown', function (e) {
        if (!results.is(':visible')) return;
        let items = get_items();
        if (!items.length) return;

        if (e.key === 'ArrowDown') {
            e.preventDefault();
            let next = selected_index + 1;
            if (next >= items.length) next = 0;
            set_active_item(next);
        } else if (e.key === 'ArrowUp') {
            e.preventDefault();
            let prev = selected_index - 1;
            if (prev < 0) prev = items.length - 1;
            set_active_item(prev);
        } else if (e.key === 'Enter') {
            e.preventDefault();
            if (selected_index >= 0 && selected_index < items.length) {
                items.eq(selected_index).click();
            } else if (items.length > 0) {
                items.first().click();
            }
        }
    });

    // Hover sync with keyboard index
    results.on('mouseenter', '.fd-omni-result-item', function () {
        get_items().removeClass('active-result');
        selected_index = $(this).index();
        $(this).addClass('active-result');
    });

    // Receptionist Hotkeys: Press '/' to focus search, 'Escape' to dismiss
    $(document).off('keydown.fd_hotkey').on('keydown.fd_hotkey', function (e) {
        if (!$('#fd-omni-search').is(':visible')) return;
        if ($('.modal.show, .modal.in').length) return;

        if (e.key === 'Escape') {
            if ($('#fd-omni-results').is(':visible') || $(e.target).is('#fd-omni-search')) {
                $('#fd-omni-results').hide();
                $('#fd-omni-search').blur();
                e.preventDefault();
            }
            return;
        }

        if ($(e.target).is('input, textarea, select, [contenteditable]')) return;

        if (e.key === '/') {
            e.preventDefault();
            $('#fd-omni-search').focus().select();
        }
    });
}

function render_omni_results(rows) {
    let results = $('#fd-omni-results');
    if (!rows.length) {
        results.html(`
            <div style="padding: 24px 18px; text-align: center; color: #64748b;">
                <div style="width:44px; height:44px; border-radius:50%; background:#f1f5f9; display:inline-flex; align-items:center; justify-content:center; margin-bottom:10px; border:1px solid #e2e8f0;">
                    <i class="fas fa-search" style="font-size:18px; color:#94a3b8;"></i>
                </div>
                <div style="font-weight:700; font-size:13px; color:#1e293b; margin-bottom:4px;">${__('Không tìm thấy kết quả phù hợp')}</div>
                <div style="font-size:12px; color:#64748b; margin-bottom:12px;">${__('Không có đặt phòng nào khớp với từ khóa vừa nhập.')}</div>
                <div style="display:flex; flex-direction:column; gap:5px; font-size:11px; color:#64748b; text-align:left; background:#f8fafc; padding:10px 14px; border-radius:6px; border:1px dashed #cbd5e1;">
                    <div style="font-weight:700; color:#334155;">💡 ${__('Gợi ý tra cứu nhanh:')}</div>
                    <div>&bull; ${__('Nhập số phòng thực tế')} (ví dụ: <code>101</code>, <code>202</code>)</div>
                    <div>&bull; ${__('Nhập số điện thoại khách')} (ví dụ: <code>0912...</code>)</div>
                    <div>&bull; ${__('Nhập số CCCD hoặc Hộ chiếu')}</div>
                    <div>&bull; ${__('Nhập mã đặt phòng OTA')} (ví dụ: <code>BK-01...</code>)</div>
                </div>
            </div>
        `).show();
        return;
    }
    let html = rows.map((r) => `
        <div class="fd-list-item fd-omni-result-item" style="cursor:pointer;" data-res="${frappe.utils.escape_html(r.reservation)}">
            <div style="flex:1;">
                <div style="font-weight:600;">${frappe.utils.escape_html(r.guest_name || '')}</div>
                <div style="font-size:12px; color:#6c757d;">
                    ${frappe.utils.escape_html(r.room || __('Unassigned'))} &middot; ${frappe.utils.escape_html(r.status || '')} &middot; ${frappe.utils.escape_html(r.arrival_date || '')} &rarr; ${frappe.utils.escape_html(r.departure_date || '')}
                    ${r.external_booking_id ? ' &middot; Ref: ' + frappe.utils.escape_html(r.external_booking_id) : ''}
                </div>
            </div>
        </div>`).join('');
    results.html(html).show();
    results.find('.fd-omni-result-item').off('click').on('click', function () {
        let res = $(this).data('res');
        if (res) frappe.set_route('Form', 'Hotel Reservation', res);
    });
}

function open_id_scanner_dialog() {
    let dialog = new frappe.ui.Dialog({
        title: __('Scan ID Document (CCCD / Passport)'),
        fields: [
            {
                fieldname: 'raw_text',
                fieldtype: 'Small Text',
                label: __('Paste OCR text or MRZ lines'),
                description: __('Paste the text output from your CCCD/passport scanner or OCR hardware bridge here.'),
                reqd: 1
            },
            { fieldtype: 'Section Break' },
            { fieldname: 'full_name', fieldtype: 'Data', label: __('Full Name'), read_only: 1 },
            { fieldname: 'id_number', fieldtype: 'Data', label: __('ID / Passport Number'), read_only: 1 },
            { fieldtype: 'Column Break' },
            { fieldname: 'date_of_birth', fieldtype: 'Data', label: __('Date of Birth'), read_only: 1 },
            { fieldname: 'nationality', fieldtype: 'Data', label: __('Nationality'), read_only: 1 }
        ],
        primary_action_label: __('Parse'),
        primary_action(values) {
            frappe.call({
                method: 'hospitality_core.hospitality_core.api.id_scanner.parse_id_document',
                args: { raw_text: values.raw_text },
                callback: function (r) {
                    let res = r.message;
                    if (!res || !res.success) {
                        frappe.msgprint({ message: res ? res.message : __('Could not parse document.'), indicator: 'red' });
                        return;
                    }
                    dialog.set_value('full_name', res.full_name);
                    dialog.set_value('id_number', res.id_number);
                    dialog.set_value('date_of_birth', res.date_of_birth);
                    dialog.set_value('nationality', res.nationality);
                    dialog.set_primary_action(__('Create Guest'), function () {
                        // parse_id_document() đã bóc tách đủ gender/date_of_birth/
                        // nationality từ lâu, nhưng trước đây "Create Guest" không hề
                        // truyền các trường này — Guest tạo ra luôn thiếu Giới tính/Ngày
                        // sinh (2 trường bắt buộc cho khai báo tạm trú Công an, xem
                        // police_declaration.py). Đồng thời "CCCD" không phải giá trị
                        // hợp lệ của Select "identification_type" (chỉ có Passport/
                        // National ID/Driver License) — đã sửa thành "National ID".
                        let guest_fields = {
                            full_name: res.full_name,
                            identification_no: res.id_number,
                            identification_type: res.document_type === 'Passport' ? 'Passport' : 'National ID',
                            date_of_birth: res.date_of_birth || undefined
                        };
                        if (res.gender === 'Nam') {
                            guest_fields.gender = 'Male';
                        } else if (res.gender === 'Nữ') {
                            guest_fields.gender = 'Female';
                        }
                        // Guest.nationality là Link tới Country (ERPNext core lưu tên
                        // tiếng Anh, VD "Vietnam") — parse_id_document() trả "Việt Nam"
                        // cho CCCD (map an toàn được), nhưng trả mã ISO-3 thô (VD "USA")
                        // cho hộ chiếu nước ngoài, không khớp trực tiếp tên Country nào
                        // nên cố tình BỎ TRỐNG để lễ tân tự chọn, tránh set sai dữ liệu.
                        if (res.nationality === 'Việt Nam') {
                            guest_fields.nationality = 'Vietnam';
                        }
                        frappe.new_doc('Guest', guest_fields);
                        dialog.hide();
                    });
                }
            });
        }
    });
    dialog.show();
}

function open_split_bill_dialog() {
    let dialog = new frappe.ui.Dialog({
        title: __('Split Bill'),
        fields: [
            {
                fieldname: 'transaction', fieldtype: 'Link', options: 'Folio Transaction',
                label: __('Transaction to Split'), reqd: 1
            },
            {
                fieldname: 'splits', fieldtype: 'Table', label: __('Split Into'),
                fields: [
                    { fieldname: 'folio', fieldtype: 'Link', options: 'Guest Folio', in_list_view: 1, label: __('Folio'), reqd: 1 },
                    { fieldname: 'amount', fieldtype: 'Currency', in_list_view: 1, label: __('Amount'), reqd: 1 }
                ],
                data: [{}, {}],
                get_data: () => dialog.get_value('splits')
            }
        ],
        primary_action_label: __('Split'),
        primary_action(values) {
            frappe.call({
                method: 'hospitality_core.hospitality_core.api.folio_operations.split_transaction',
                args: { transaction_name: values.transaction, splits: values.splits },
                freeze: true,
                callback: function (r) {
                    if (!r.exc) dialog.hide();
                }
            });
        }
    });
    dialog.show();
}

function open_merge_folio_dialog() {
    let dialog = new frappe.ui.Dialog({
        title: __('Merge Folio'),
        fields: [
            { fieldname: 'source_folio', fieldtype: 'Link', options: 'Guest Folio', label: __('Source Folio (will be closed)'), reqd: 1 },
            { fieldname: 'target_folio', fieldtype: 'Link', options: 'Guest Folio', label: __('Target Folio (receives charges)'), reqd: 1 }
        ],
        primary_action_label: __('Merge'),
        primary_action(values) {
            frappe.confirm(
                __('This will move all open charges from {0} into {1} and close {0}. Continue?', [values.source_folio, values.target_folio]),
                function () {
                    frappe.call({
                        method: 'hospitality_core.hospitality_core.api.folio_operations.merge_folios',
                        args: { source_folio: values.source_folio, target_folio: values.target_folio },
                        freeze: true,
                        callback: function (r) {
                            if (!r.exc) dialog.hide();
                        }
                    });
                }
            );
        }
    });
    dialog.show();
}

var _fd_cache = { arrivals: [], departures: [], stats: {} };
var _active_kpi_filter = null; // null | 'arr_pending' | 'dep_pending'

function setup_kpi_filters() {
    $('#card-arr-pending').off('click').on('click', function () {
        if (_active_kpi_filter === 'arr_pending') {
            reset_kpi_filters();
        } else {
            _active_kpi_filter = 'arr_pending';
            $('.fd-stat-card').removeClass('active-filter');
            $(this).addClass('active-filter');
            apply_kpi_filters();
            $('html, body').animate({
                scrollTop: $('#list-arrivals').offset().top - 120
            }, 300);
        }
    });

    $('#card-dep-pending').off('click').on('click', function () {
        if (_active_kpi_filter === 'dep_pending') {
            reset_kpi_filters();
        } else {
            _active_kpi_filter = 'dep_pending';
            $('.fd-stat-card').removeClass('active-filter');
            $(this).addClass('active-filter');
            apply_kpi_filters();
            $('html, body').animate({
                scrollTop: $('#list-departures').offset().top - 120
            }, 300);
        }
    });

    $('#btn-reset-filters').off('click').on('click', function () {
        reset_kpi_filters();
    });
}

function reset_kpi_filters() {
    _active_kpi_filter = null;
    $('.fd-stat-card').removeClass('active-filter');
    $('#fd-omni-search').val('');
    $('#fd-omni-results').hide().empty();
    render_arrivals(_fd_cache.arrivals);
    render_departures(_fd_cache.departures);
}

function apply_kpi_filters() {
    if (_active_kpi_filter === 'arr_pending') {
        let filtered = _fd_cache.arrivals.filter(d => d.status === 'Reserved');
        render_arrivals(filtered, true);
        render_departures(_fd_cache.departures);
    } else if (_active_kpi_filter === 'dep_pending') {
        let filtered = _fd_cache.departures.filter(d => d.status === 'Checked In');
        render_departures(filtered, true);
        render_arrivals(_fd_cache.arrivals);
    }
}

function render_console(wrapper, page) {
    let selected_date = page.fields_dict.console_date.get_value();

    // Hiển thị khung xương Shimmer tạo cảm giác mượt mà tức thì
    show_console_skeletons();

    frappe.call({
        method: "hospitality_core.hospitality_core.page.front_desk_console.front_desk_console.get_console_data",
        args: { target_date: selected_date },
        callback: function (r) {
            if (r.message) {
                _fd_cache.stats = r.message.stats || {};
                _fd_cache.arrivals = r.message.arrivals || [];
                _fd_cache.departures = r.message.departures || [];

                let now = new Date();
                let sync_time = ('0' + now.getHours()).slice(-2) + ':' + ('0' + now.getMinutes()).slice(-2) + ':' + ('0' + now.getSeconds()).slice(-2);
                $('#fd-last-synced').text(sync_time);

                update_stats(_fd_cache.stats);
                if (_active_kpi_filter) {
                    apply_kpi_filters();
                } else {
                    render_arrivals(_fd_cache.arrivals);
                    render_departures(_fd_cache.departures);
                }
            }
        }
    });
}

function show_console_skeletons() {
    $('#stat-arr-pending').html('<span class="skeleton-shimmer skeleton-card-num"></span>');
    $('#stat-dep-pending').html('<span class="skeleton-shimmer skeleton-card-num"></span>');
    $('#stat-occupancy').html('<span class="skeleton-shimmer skeleton-card-num"></span>');
    $('#stat-occ-pct').html('<span class="skeleton-shimmer" style="width:72px; height:14px; margin-top:2px;"></span>');
    $('#stat-available').html('<span class="skeleton-shimmer skeleton-card-num"></span>');

    let skeletonList = Array(4).fill(0).map(() => `
        <div class="skeleton-list-item">
            <div style="flex:1;">
                <div class="skeleton-shimmer" style="width:130px; height:15px; margin-bottom:6px;"></div>
                <div class="skeleton-shimmer" style="width:85px; height:12px;"></div>
            </div>
            <div class="skeleton-shimmer" style="width:78px; height:24px; border-radius:12px;"></div>
        </div>
    `).join('');
    $('#list-arrivals').html(skeletonList);
    $('#list-departures').html(skeletonList);
}

function update_stats(stats) {
    $('#stat-arr-pending').text(stats.arrivals_pending || 0);
    $('#stat-dep-pending').text(stats.departures_pending || 0);
    $('#stat-occupancy').text(stats.in_house || 0);
    $('#stat-occ-pct').text((stats.occupancy_pct || 0) + '% ' + __('Công suất'));
    $('#stat-available').text(stats.available || 0);
}

function render_arrivals(data, is_filtered = false) {
    let html = '';
    let count_text = is_filtered ? `${data.length} / ${_fd_cache.arrivals.length} ${__('chờ')}` : `${data.length}`;
    $('#arrivals-count-badge').text(count_text);

    if (is_filtered) {
        $('#arrivals-filter-indicator').html(`<span class="fd-filter-pill" onclick="reset_kpi_filters();" title="${__('Bấm để hủy lọc')}"><i class="fa fa-filter"></i> ${__('Đang lọc chờ')} <i class="fa fa-times"></i></span>`);
    } else {
        $('#arrivals-filter-indicator').empty();
    }

    if (data.length === 0) {
        html = `
        <div class="smart-empty-state">
            <div class="smart-empty-icon"><i class="fas fa-plane-arrival"></i></div>
            <div class="smart-empty-title">${is_filtered ? __('Không có khách nào đang chờ check-in') : __('Không có khách đến trong ngày')}</div>
            <div class="smart-empty-subtitle">${is_filtered ? __('Toàn bộ khách đến hôm nay đã hoàn tất nhận phòng.') : __('Không có đặt phòng nào có ngày đến vào ngày đã chọn.')}</div>
            <span class="smart-empty-badge">✓ ${__('Đã đồng bộ')}</span>
        </div>`;
    } else {
        data.forEach(d => {
            let is_pending = d.status === 'Reserved';
            let is_arrived = d.status === 'Checked In' || d.status === 'Checked Out';
            let badge = '';

            if (is_arrived) {
                badge = `<span class="badge-done"><i class="fa fa-check"></i> ${__('Đã Đến')}</span>`;
            } else if (is_pending) {
                let is_past = frappe.datetime.get_diff(frappe.datetime.now_date(), d.arrival_date) > 0;
                if (is_past) badge = `<span class="badge-missed"><i class="fa fa-exclamation-triangle"></i> ${__('Vắng Mặt (No Show)')}</span>`;
                else badge = `<span class="badge-pending"><i class="fa fa-clock"></i> ${__('Chờ Check-in')}</span>`;
            }

            let hk_badge = '';
            if (d.room && d.room_hk_status) {
                if (d.room_hk_status === 'Available' || d.room_hk_status === 'Inspected') {
                    hk_badge = `<span class="badge" style="background:#ecfdf5; color:#047857; font-size:10px; border:1px solid #a7f3d0; padding:2px 6px; border-radius:4px; font-weight:600; margin-left:6px;" title="${__('Phòng đã dọn sạch sẵn sàng đón khách')}"><i class="fa fa-check-circle"></i> ${__('Sạch')}</span>`;
                } else if (d.room_hk_status === 'Dirty') {
                    hk_badge = `<span class="badge" style="background:#fef2f2; color:#b91c1c; border:1px solid #fecaca; font-size:10px; padding:2px 6px; border-radius:4px; font-weight:600; margin-left:6px;" title="${__('Phòng chưa dọn - Cần báo Housekeeping')}"><i class="fa fa-exclamation-circle"></i> ${__('Chưa dọn')}</span>`;
                } else if (d.room_hk_status === 'Cleaning') {
                    hk_badge = `<span class="badge" style="background:#fffbeb; color:#b45309; border:1px solid #fde68a; font-size:10px; padding:2px 6px; border-radius:4px; font-weight:600; margin-left:6px;" title="${__('Housekeeping đang dọn dẹp')}"><i class="fa fa-broom"></i> ${__('Đang dọn')}</span>`;
                }
            }

            html += `
            <div class="fd-list-item">
                <div style="flex:1;">
                    <div style="font-weight:700; font-size:14px; margin-bottom: 2px;">
                        <a href="#" style="color:#1e293b;" onclick="frappe.set_route('Form', 'Hotel Reservation', '${d.name}'); return false;">${frappe.utils.escape_html(d.guest_name || __('Khách Vãng Lai'))}</a>
                    </div>
                    <div style="font-size:12px; color:#64748b; display:flex; align-items:center; flex-wrap:wrap; gap:4px;">
                        <span class="fas fa-bed" style="color:#3b82f6;"></span>
                        <b>${frappe.utils.escape_html(d.room || __('Chưa xếp phòng'))}</b>${hk_badge} &middot; <span class="text-muted">${frappe.utils.escape_html(d.room_type || '')}</span>
                    </div>
                </div>
                <div class="text-right">
                    <div style="margin-bottom:6px;">${badge}</div>
                    ${d.status === 'Reserved' ? `<button class="btn btn-xs btn-primary fd-action-checkin" style="font-weight:600; border-radius:4px;" data-res="${frappe.utils.escape_html(d.name)}"><i class="fa fa-sign-in-alt"></i> ${__('Check-in')}</button>` : ''}
                </div>
            </div>`;
        });
    }
    $('#list-arrivals').html(html);
}

function render_departures(data, is_filtered = false) {
    let html = '';
    let count_text = is_filtered ? `${data.length} / ${_fd_cache.departures.length} ${__('chờ')}` : `${data.length}`;
    $('#departures-count-badge').text(count_text);

    if (is_filtered) {
        $('#departures-filter-indicator').html(`<span class="fd-filter-pill" onclick="reset_kpi_filters();" title="${__('Bấm để hủy lọc')}"><i class="fa fa-filter"></i> ${__('Đang lọc chờ')} <i class="fa fa-times"></i></span>`);
    } else {
        $('#departures-filter-indicator').empty();
    }

    if (data.length === 0) {
        html = `
        <div class="smart-empty-state">
            <div class="smart-empty-icon"><i class="fas fa-plane-departure"></i></div>
            <div class="smart-empty-title">${is_filtered ? __('Không có khách nào đang chờ check-out') : __('Không có khách đi trong ngày')}</div>
            <div class="smart-empty-subtitle">${is_filtered ? __('Toàn bộ khách trả phòng hôm nay đã làm thủ tục xong.') : __('Không có đặt phòng nào có ngày trả phòng vào ngày đã chọn.')}</div>
            <span class="smart-empty-badge">✓ ${__('Đã hoàn tất')}</span>
        </div>`;
    } else {
        data.forEach(d => {
            let is_left = d.status === 'Checked Out';
            let is_pending = d.status === 'Checked In';
            let badge = '';

            if (is_left) {
                badge = `<span class="badge-done"><i class="fa fa-check"></i> ${__('Đã Trả Phòng')}</span>`;
            } else if (is_pending) {
                let is_past = frappe.datetime.get_diff(frappe.datetime.now_date(), d.departure_date) > 0;
                if (is_past) badge = `<span class="badge-missed"><i class="fa fa-exclamation-circle"></i> ${__('Quá Giờ (Overstay)')}</span>`;
                else badge = `<span class="badge-pending"><i class="fa fa-clock"></i> ${__('Chờ Check-out')}</span>`;
            }

            html += `
            <div class="fd-list-item">
                <div style="flex:1;">
                    <div style="font-weight:700; font-size:14px; margin-bottom: 2px;">
                        <a href="#" style="color:#1e293b;" onclick="frappe.set_route('Form', 'Hotel Reservation', '${d.name}'); return false;">${frappe.utils.escape_html(d.guest_name || __('Khách Vãng Lai'))}</a>
                    </div>
                    <div style="font-size:12px; color:#64748b;">
                        <span class="fas fa-door-open" style="color:#ef4444;"></span> <b>${frappe.utils.escape_html(d.room || '')}</b> &middot; <span class="text-muted">${frappe.utils.escape_html(d.room_type || '')}</span>
                    </div>
                </div>
                <div class="text-right">
                    <div style="margin-bottom:6px;">${badge}</div>
                    ${d.status === 'Checked In' ? `<button class="btn btn-xs btn-danger fd-action-checkout" style="font-weight:600; border-radius:4px;" data-res="${frappe.utils.escape_html(d.name)}"><i class="fa fa-sign-out-alt"></i> ${__('Check-out')}</button>` : ''}
                </div>
            </div>`;
        });
    }
    $('#list-departures').html(html);
}

function start_live_clock() {
    if (window._fd_clock_interval) clearInterval(window._fd_clock_interval);
    const update_time = () => {
        let now = new Date();
        let time_str = ('0' + now.getHours()).slice(-2) + ':' + ('0' + now.getMinutes()).slice(-2) + ':' + ('0' + now.getSeconds()).slice(-2);
        $('#fd-live-clock').text(time_str);
    };
    update_time();
    window._fd_clock_interval = setInterval(update_time, 1000);
}

function setup_list_actions() {
    $('#list-arrivals').off('click', '.fd-action-checkin').on('click', '.fd-action-checkin', function (e) {
        e.preventDefault();
        let $btn = $(this);
        let res = $btn.data('res');
        $btn.prop('disabled', true).html(`<i class="fa fa-spinner fa-spin"></i> ${__('Mở...')}`);
        frappe.set_route('Form', 'Hotel Reservation', res);
    });

    $('#list-departures').off('click', '.fd-action-checkout').on('click', '.fd-action-checkout', function (e) {
        e.preventDefault();
        let $btn = $(this);
        let res = $btn.data('res');
        $btn.prop('disabled', true).html(`<i class="fa fa-spinner fa-spin"></i> ${__('Mở...')}`);
        frappe.set_route('Form', 'Hotel Reservation', res);
    });
}

function open_quick_vietqr_dialog() {
    let d = new frappe.ui.Dialog({
        title: __('⚡ Tạo Mã VietQR Nhanh Cho Khách'),
        fields: [
            {
                label: __('Guest Folio'),
                fieldname: 'folio',
                fieldtype: 'Link',
                options: 'Guest Folio',
                get_query: () => ({ filters: { status: 'Open' } }),
                reqd: 1,
                change: function () {
                    let val = d.get_value('folio');
                    if (val) {
                        frappe.db.get_value('Guest Folio', val, ['outstanding_balance', 'room'], (r) => {
                            if (r) {
                                d.set_value('amount', r.outstanding_balance > 0 ? r.outstanding_balance : 0);
                                if (r.room) {
                                    frappe.db.get_value('Hotel Room', r.room, 'room_number', (hr) => {
                                        d.set_value('room', (hr && hr.room_number) ? hr.room_number : r.room);
                                    });
                                } else {
                                    d.set_value('room', '');
                                }
                            }
                        });
                    }
                }
            },
            {
                label: __('Số Phòng'),
                fieldname: 'room',
                fieldtype: 'Data',
                read_only: 1
            },
            {
                label: __('Số Tiền Thanh Toán (VND)'),
                fieldname: 'amount',
                fieldtype: 'Currency',
                reqd: 1
            }
        ],
        primary_action_label: __('Hiển Thị Mã VietQR'),
        primary_action: function (vals) {
            let amt = flt(vals.amount);
            if (amt <= 0) {
                frappe.msgprint({
                    title: __('Số Tiền Không Hợp Lệ'),
                    message: __('Số tiền thanh toán phải lớn hơn 0 VND. Vui lòng nhập lại số tiền hợp lệ.'),
                    indicator: 'orange'
                });
                return;
            }

            frappe.call({
                method: 'hospitality_core.hospitality_core.api.vietqr_bridge.generate_vietqr_payload',
                args: {
                    folio_name: vals.folio,
                    amount: amt
                },
                callback: function (r) {
                    if (!r.exc && r.message) {
                        d.hide();
                        let data = r.message;
                        let qr_d = new frappe.ui.Dialog({
                            title: __('⚡ Quét VietQR NAPAS 247 - Phòng {0}', [data.room || '']),
                            fields: [
                                {
                                    fieldname: 'qr_html',
                                    fieldtype: 'HTML',
                                    options: `
                                        <div style="text-align: center; padding: 10px;">
                                            <img src="${data.vietqr_image_url}" style="max-width: 260px; border-radius: 8px; box-shadow: 0 2px 10px rgba(0,0,0,0.1);" />
                                            <div style="font-size: 20px; font-weight: 800; color: #0284c7; margin-top: 10px;">${data.formatted_amount}</div>
                                            <div class="qr-copy-stk" style="font-size: 13px; color: #475569; margin-top: 8px; cursor: pointer; padding: 4px; border-radius: 6px; background: #f8fafc; border: 1px solid #e2e8f0; display: inline-block;">
                                                STK: <b>${frappe.utils.escape_html(data.account_number)}</b> (${frappe.utils.escape_html(data.account_name)}) <i class="fa fa-copy text-primary" style="margin-left: 4px;"></i>
                                            </div>
                                            <div class="qr-copy-desc" style="font-size: 12px; color: #e11d48; margin-top: 8px; cursor: pointer; padding: 4px; border-radius: 6px; background: #fff5f5; border: 1px solid #fed7d7; display: block;">
                                                Nội dung: <b>${frappe.utils.escape_html(data.description)}</b> <i class="fa fa-copy text-danger" style="margin-left: 4px;"></i>
                                            </div>
                                        </div>
                                    `
                                }
                            ],
                            primary_action_label: __('Đóng')
                        });
                        qr_d.show();

                        const safe_copy = (text, msg) => {
                            if (!text) return;
                            if (navigator.clipboard && window.isSecureContext) {
                                navigator.clipboard.writeText(text).then(() => {
                                    frappe.show_alert({ message: msg, indicator: 'green' });
                                }).catch(() => fallback_copy(text, msg));
                            } else {
                                fallback_copy(text, msg);
                            }
                        };
                        const fallback_copy = (text, msg) => {
                            let ta = document.createElement("textarea");
                            ta.value = text;
                            ta.style.position = "fixed";
                            ta.style.left = "-9999px";
                            document.body.appendChild(ta);
                            ta.focus();
                            ta.select();
                            try {
                                document.execCommand('copy');
                                frappe.show_alert({ message: msg, indicator: 'green' });
                            } catch (e) {
                                frappe.show_alert({ message: __('Không thể tự động sao chép'), indicator: 'orange' });
                            }
                            ta.remove();
                        };

                        qr_d.$wrapper.find('.qr-copy-stk').on('click', function () {
                            let $btn = $(this);
                            safe_copy(data.account_number, __('Đã sao chép STK!'));
                            let $icon = $btn.find('i');
                            $icon.removeClass('fa-copy text-primary').addClass('fa-check text-success');
                            setTimeout(() => {
                                $icon.removeClass('fa-check text-success').addClass('fa-copy text-primary');
                            }, 1500);
                        });
                        qr_d.$wrapper.find('.qr-copy-desc').on('click', function () {
                            let $btn = $(this);
                            safe_copy(data.description, __('Đã sao chép Nội dung CK!'));
                            let $icon = $btn.find('i');
                            $icon.removeClass('fa-copy text-danger').addClass('fa-check text-success');
                            setTimeout(() => {
                                $icon.removeClass('fa-check text-success').addClass('fa-copy text-danger');
                            }, 1500);
                        });
                    }
                }
            });
        }
    });
    d.show();
}