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
        .fd-toolbar-icon {
            font-size: 22px;
            margin-bottom: 8px;
            color: #3b82f6;
            transition: transform 0.2s;
        }
        .fd-toolbar-btn:hover .fd-toolbar-icon {
            transform: scale(1.1);
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
            transition: background 0.15s ease;
        }
        .fd-list-item:hover { background: #f8fafc; }
        .fd-list-item:last-child { border-bottom: none; }
        
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
    </style>`).appendTo(wrapper);

    // Main Layout Skeleton
    $(wrapper).find('.layout-main-section').append(`
        <div id="fd-content" style="padding-top: 10px;">
            <!-- Omni Search Bar -->
            <div class="row" style="margin-bottom: 20px;">
                <div class="col-md-9 col-xs-12" style="position: relative;">
                    <div style="position: relative;">
                        <span class="fas fa-search" style="position: absolute; left: 14px; top: 13px; color: #94a3b8; font-size: 14px;"></span>
                        <input type="text" id="fd-omni-search" class="form-control" style="padding-left: 38px; height: 42px; border-radius: 8px; border: 1px solid #cbd5e1; font-size: 13px;"
                            placeholder="${__('Tìm kiếm thông minh: Tên khách, Số điện thoại, Số phòng, CCCD/Hộ chiếu, Mã đặt phòng OTA...')}">
                    </div>
                    <div id="fd-omni-results" style="display:none; position:absolute; top:100%; left:0; right:0; z-index:50; background:#fff; border:1px solid #cbd5e1; border-radius:0 0 8px 8px; max-height:320px; overflow-y:auto; box-shadow:0 10px 25px rgba(0,0,0,0.1);"></div>
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
                        <span><i class="fas fa-plane-arrival" style="color:#d97706; margin-right:8px;"></i>${__('Danh Sách Khách Đến (Arrivals)')}</span>
                        <span id="arrivals-count-badge" class="badge" style="background:#f1f5f9; color:#475569; font-size:11px;">0</span>
                    </div>
                    <div id="list-arrivals" class="fd-list-container">
                        <div class="text-center p-4 text-muted">${__('Đang tải dữ liệu...')}</div>
                    </div>
                </div>

                <!-- Departures Column -->
                <div class="col-md-6" style="margin-bottom: 20px;">
                    <div class="fd-list-header">
                        <span><i class="fas fa-plane-departure" style="color:#dc2626; margin-right:8px;"></i>${__('Danh Sách Khách Đi (Departures)')}</span>
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
}

function setup_omni_search() {
    let input = $('#fd-omni-search');
    let results = $('#fd-omni-results');
    let debounce_timer = null;

    input.on('input', function () {
        let query = $(this).val();
        clearTimeout(debounce_timer);
        if (!query || query.length < 2) {
            results.hide().empty();
            return;
        }
        debounce_timer = setTimeout(() => {
            frappe.call({
                method: 'hospitality_core.hospitality_core.api.folio_operations.omni_search',
                args: { query: query },
                callback: function (r) {
                    render_omni_results(r.message || []);
                }
            });
        }, 300);
    });

    $(document).on('click', function (e) {
        if (!$(e.target).closest('#fd-omni-search, #fd-omni-results').length) {
            results.hide();
        }
    });
}

function render_omni_results(rows) {
    let results = $('#fd-omni-results');
    if (!rows.length) {
        results.html(`<div class="p-3 text-muted">${__('No matches found.')}</div>`).show();
        return;
    }
    let html = rows.map((r) => `
        <div class="fd-list-item" style="cursor:pointer;" onclick="frappe.set_route('Form', 'Hotel Reservation', '${r.reservation}')">
            <div style="flex:1;">
                <div style="font-weight:600;">${frappe.utils.escape_html(r.guest_name || '')}</div>
                <div style="font-size:12px; color:#6c757d;">
                    ${frappe.utils.escape_html(r.room || __('Unassigned'))} &middot; ${frappe.utils.escape_html(r.status || '')} &middot; ${r.arrival_date} &rarr; ${r.departure_date}
                    ${r.external_booking_id ? ' &middot; Ref: ' + frappe.utils.escape_html(r.external_booking_id) : ''}
                </div>
            </div>
        </div>`).join('');
    results.html(html).show();
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

    frappe.call({
        method: "hospitality_core.hospitality_core.page.front_desk_console.front_desk_console.get_console_data",
        args: { target_date: selected_date },
        freeze: true,
        freeze_message: __('Đang làm mới bàn lễ tân...'),
        callback: function (r) {
            if (r.message) {
                _fd_cache.stats = r.message.stats || {};
                _fd_cache.arrivals = r.message.arrivals || [];
                _fd_cache.departures = r.message.departures || [];

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

    if (data.length === 0) {
        html = `<div class="text-center p-4 text-muted">${is_filtered ? __('Không có khách nào đang chờ check-in.') : __('Không có khách đến trong ngày đã chọn.')}</div>`;
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

            html += `
            <div class="fd-list-item">
                <div style="flex:1;">
                    <div style="font-weight:700; font-size:14px; margin-bottom: 2px;">
                        <a href="#" style="color:#1e293b;" onclick="frappe.set_route('Form', 'Hotel Reservation', '${d.name}'); return false;">${frappe.utils.escape_html(d.guest_name || __('Khách Vãng Lai'))}</a>
                    </div>
                    <div style="font-size:12px; color:#64748b;">
                        <span class="fas fa-bed" style="color:#3b82f6;"></span> <b>${frappe.utils.escape_html(d.room || __('Chưa xếp phòng'))}</b> &middot; <span class="text-muted">${frappe.utils.escape_html(d.room_type || '')}</span>
                    </div>
                </div>
                <div class="text-right">
                    <div style="margin-bottom:6px;">${badge}</div>
                    ${d.status === 'Reserved' ? `<button class="btn btn-xs btn-primary" style="font-weight:600; border-radius:4px;" onclick="frappe.set_route('Form', 'Hotel Reservation', '${d.name}')"><i class="fa fa-sign-in-alt"></i> ${__('Check-in')}</button>` : ''}
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

    if (data.length === 0) {
        html = `<div class="text-center p-4 text-muted">${is_filtered ? __('Không có khách nào đang chờ check-out.') : __('Không có khách đi trong ngày đã chọn.')}</div>`;
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
                    ${d.status === 'Checked In' ? `<button class="btn btn-xs btn-danger" style="font-weight:600; border-radius:4px;" onclick="frappe.set_route('Form', 'Hotel Reservation', '${d.name}')"><i class="fa fa-sign-out-alt"></i> ${__('Check-out')}</button>` : ''}
                </div>
            </div>`;
        });
    }
    $('#list-departures').html(html);
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
                                            <div style="font-size: 13px; color: #475569; margin-top: 6px; cursor: pointer;" onclick="navigator.clipboard.writeText('${data.account_number}'); frappe.show_alert({message: __('Đã sao chép STK!'), indicator: 'green'});">
                                                STK: <b>${data.account_number}</b> (${data.account_name}) <i class="fa fa-copy text-primary" style="margin-left: 4px;"></i>
                                            </div>
                                            <div style="font-size: 12px; color: #e11d48; margin-top: 6px; cursor: pointer;" onclick="navigator.clipboard.writeText('${data.description}'); frappe.show_alert({message: __('Đã sao chép Nội dung CK!'), indicator: 'green'});">
                                                Nội dung: <b>${data.description}</b> <i class="fa fa-copy text-danger" style="margin-left: 4px;"></i>
                                            </div>
                                        </div>
                                    `
                                }
                            ],
                            primary_action_label: __('Đóng')
                        });
                        qr_d.show();
                    }
                }
            });
        }
    });
    d.show();
}