frappe.pages['front-desk-console'].on_page_load = function (wrapper) {
    var page = frappe.ui.make_app_page({
        parent: wrapper,
        title: 'Front Desk Console',
        single_column: true
    });

    // 1. Add Date Filter
    page.add_field({
        fieldname: 'console_date',
        label: 'Date',
        fieldtype: 'Date',
        default: frappe.datetime.now_date(),
        change: function () {
            render_console(wrapper, page);
        }
    });

    // Refresh Button
    page.set_primary_action('Refresh Data', function () {
        render_console(wrapper, page);
    });

    page.add_menu_item(__('Scan ID (CCCD/Passport)'), function () {
        open_id_scanner_dialog();
    });
    page.add_menu_item(__('Split Bill'), function () {
        open_split_bill_dialog();
    });
    page.add_menu_item(__('Merge Folio'), function () {
        open_merge_folio_dialog();
    });
    page.add_menu_item(__('Xuất Excel Khai Báo XNC Quốc Tế (XLSX)'), function () {
        let cur_date = page.fields_dict.console_date.get_value() || frappe.datetime.now_date();
        window.open(`/api/method/hospitality_core.hospitality_core.api.police_declaration.export_quangninh_immigration_report_xlsx?target_date=${cur_date}`);
    });
    page.add_menu_item(__('Xuất Excel Khai Báo Tạm Trú Toàn Đoàn (XLSX)'), function () {
        let cur_date = page.fields_dict.console_date.get_value() || frappe.datetime.now_date();
        window.open(`/api/method/hospitality_core.hospitality_core.api.police_declaration.export_police_declaration_xlsx?target_date=${cur_date}`);
    });

    page.add_inner_button(__('⚡ Tạo VietQR Nhanh'), function () {
        open_quick_vietqr_dialog();
    });
    page.add_inner_button(__('Quét CCCD / Passport'), function () {
        open_id_scanner_dialog();
    });
    page.add_inner_button(__('📊 Xuất Excel XNC (XLSX)'), function () {
        let cur_date = page.fields_dict.console_date.get_value() || frappe.datetime.now_date();
        window.open(`/api/method/hospitality_core.hospitality_core.api.police_declaration.export_quangninh_immigration_report_xlsx?target_date=${cur_date}`);
    });
    page.add_inner_button(__('📋 Xuất File CSV XNC'), function () {
        let cur_date = page.fields_dict.console_date.get_value() || frappe.datetime.now_date();
        window.open(`/api/method/hospitality_core.hospitality_core.api.police_declaration.export_quangninh_immigration_report?target_date=${cur_date}`);
    });
    page.add_inner_button(__('Tách Bill'), function () {
        open_split_bill_dialog();
    });
    page.add_inner_button(__('Gộp Folio'), function () {
        open_merge_folio_dialog();
    });

    // CSS Styling
    $(`<style>
        .fd-stat-card {
            background: #fff;
            border: 1px solid #d1d8dd;
            border-radius: 8px;
            padding: 20px;
            text-align: center;
            box-shadow: 0 2px 5px rgba(0,0,0,0.05);
            transition: all 0.2s;
            height: 100%;
        }
        .fd-stat-card:hover { transform: translateY(-2px); box-shadow: 0 5px 15px rgba(0,0,0,0.1); }
        .fd-stat-number { font-size: 32px; font-weight: 700; color: #1f272e; margin: 10px 0; }
        .fd-stat-label { font-size: 13px; color: #8d99a6; text-transform: uppercase; letter-spacing: 0.5px; }
        
        .fd-toolbar-btn {
            display: inline-block;
            text-align: center;
            padding: 15px;
            background: #f8f9fa;
            border: 1px solid #ebf1f5;
            border-radius: 6px;
            width: 100%;
            cursor: pointer;
            color: #36414c;
            font-weight: 600;
        }
        .fd-toolbar-btn:hover { background: #e2e6ea; text-decoration: none; color: #1f272e; }
        .fd-toolbar-icon { font-size: 24px; display: block; margin-bottom: 8px; color: #5e64ff; }

        .fd-list-header { background: #f0f4f7; padding: 10px 15px; font-weight: bold; border-radius: 4px 4px 0 0; border: 1px solid #d1d8dd; border-bottom: none; }
        .fd-list-container { border: 1px solid #d1d8dd; border-radius: 0 0 4px 4px; background: #fff; min-height: 300px; max-height: 500px; overflow-y: auto; }
        .fd-list-item { padding: 12px 15px; border-bottom: 1px solid #f1f1f1; display: flex; align-items: center; justify-content: space-between; }
        .fd-list-item:hover { background: #fafbfc; }
        .fd-list-item:last-child { border-bottom: none; }
        
        .badge-pending { background: #fff5e6; color: #ff9f43; border: 1px solid #ff9f43; padding: 2px 8px; border-radius: 12px; font-size: 11px; }
        .badge-done { background: #e8f5e9; color: #28a745; border: 1px solid #28a745; padding: 2px 8px; border-radius: 12px; font-size: 11px; }
        .badge-missed { background: #ffebee; color: #c62828; border: 1px solid #c62828; padding: 2px 8px; border-radius: 12px; font-size: 11px; }
    </style>`).appendTo(wrapper);

    // Main Layout Skeleton
    // CORRECTION: Removed 'page' argument from set_route for custom pages
    $(wrapper).find('.layout-main-section').append(`
        <div id="fd-content" style="padding-top: 10px;">
            <!-- Omni Search -->
            <div class="row" style="margin-bottom: 15px;">
                <div class="col-md-8 col-xs-12" style="position: relative;">
                    <input type="text" id="fd-omni-search" class="form-control"
                        placeholder="${__('Search by guest name, phone, room, ID number, or OTA booking code...')}">
                    <div id="fd-omni-results" style="display:none; position:absolute; top:100%; left:0; right:0; z-index:50; background:#fff; border:1px solid #d1d8dd; border-radius:0 0 6px 6px; max-height:320px; overflow-y:auto; box-shadow:0 6px 14px rgba(0,0,0,0.1);"></div>
                </div>
            </div>

            <!-- Quick Actions Row -->
            <div class="row" style="margin-bottom: 20px;">
                <div class="col-md-2 col-xs-4"><a class="fd-toolbar-btn" onclick="frappe.set_route('tape-chart')">Tape Chart</a></div>
                <div class="col-md-2 col-xs-4"><a class="fd-toolbar-btn" onclick="frappe.set_route('availability-tool')">Availability</a></div>
                <div class="col-md-2 col-xs-4"><a class="fd-toolbar-btn" onclick="frappe.set_route('housekeeping-view')">Housekeeping</a></div>
                <div class="col-md-2 col-xs-4"><a class="fd-toolbar-btn" onclick="frappe.set_route('List', 'Hotel Reservation')">Reservations</a></div>
                <div class="col-md-2 col-xs-4"><a class="fd-toolbar-btn" onclick="frappe.set_route('query-report', 'House List')">House List</a></div>
                <div class="col-md-2 col-xs-4"><a class="fd-toolbar-btn" onclick="frappe.set_route('List', 'Hotel Maintenance Request')">Maintenance</a></div>
                <div class="col-md-2 col-xs-4"><a class="fd-toolbar-btn" onclick="frappe.set_route('housekeeping-mobile')">Housekeeping Mobile</a></div>
            </div>

            <!-- Stats Row -->
            <div class="row" style="margin-bottom: 30px;">
                <div class="col-md-3">
                    <div class="fd-stat-card">
                        <div class="fd-stat-label">Arrivals Pending</div>
                        <div class="fd-stat-number" id="stat-arr-pending" style="color: #ff9f43">0</div>
                        <small class="text-muted">For selected date</small>
                    </div>
                </div>
                <div class="col-md-3">
                    <div class="fd-stat-card">
                        <div class="fd-stat-label">Departures Pending</div>
                        <div class="fd-stat-number" id="stat-dep-pending" style="color: #ef5350">0</div>
                        <small class="text-muted">For selected date</small>
                    </div>
                </div>
                <div class="col-md-3">
                    <div class="fd-stat-card">
                        <div class="fd-stat-label">Rooms In-House</div>
                        <div class="fd-stat-number" id="stat-occupancy">0</div>
                        <small class="text-muted" id="stat-occ-pct">0% Occupancy</small>
                    </div>
                </div>
                <div class="col-md-3">
                    <div class="fd-stat-card">
                        <div class="fd-stat-label">Available Rooms</div>
                        <div class="fd-stat-number" id="stat-available" style="color: #28a745">0</div>
                        <small class="text-muted">Net Availability</small>
                    </div>
                </div>
            </div>

            <!-- Lists Row -->
            <div class="row">
                <!-- Arrivals Column -->
                <div class="col-md-6">
                    <div class="fd-list-header">
                        <span class="fas fa-plane-arrival" style="color:#5e64ff; margin-right:5px;"></span> Arrivals
                    </div>
                    <div id="list-arrivals" class="fd-list-container">
                        <div class="text-center p-3 text-muted">Loading...</div>
                    </div>
                </div>

                <!-- Departures Column -->
                <div class="col-md-6">
                    <div class="fd-list-header">
                        <span class="fas fa-plane-departure" style="color:#ef5350; margin-right:5px;"></span> Departures
                    </div>
                    <div id="list-departures" class="fd-list-container">
                        <div class="text-center p-3 text-muted">Loading...</div>
                    </div>
                </div>
            </div>
        </div>
    `);

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
                <div style="font-weight:600;">${r.guest_name || ''}</div>
                <div style="font-size:12px; color:#6c757d;">
                    ${r.room || __('Unassigned')} &middot; ${r.status} &middot; ${r.arrival_date} &rarr; ${r.departure_date}
                    ${r.external_booking_id ? ' &middot; Ref: ' + r.external_booking_id : ''}
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
                        frappe.new_doc('Guest', {
                            full_name: res.full_name,
                            identification_no: res.id_number,
                            identification_type: res.document_type === 'Passport' ? 'Passport' : 'CCCD'
                        });
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

function render_console(wrapper, page) {
    let selected_date = page.fields_dict.console_date.get_value();

    frappe.call({
        method: "hospitality_core.hospitality_core.page.front_desk_console.front_desk_console.get_console_data",
        args: { target_date: selected_date },
        callback: function (r) {
            if (r.message) {
                update_stats(r.message.stats);
                render_arrivals(r.message.arrivals);
                render_departures(r.message.departures);
            }
        }
    });
}

function update_stats(stats) {
    $('#stat-arr-pending').text(stats.arrivals_pending);
    $('#stat-dep-pending').text(stats.departures_pending);
    $('#stat-occupancy').text(stats.in_house);
    $('#stat-occ-pct').text(stats.occupancy_pct + '% Occupancy');
    $('#stat-available').text(stats.available);
}

function render_arrivals(data) {
    let html = '';
    if (data.length === 0) {
        html = '<div class="text-center p-4 text-muted">No arrivals found for this date.</div>';
    } else {
        data.forEach(d => {
            let is_pending = d.status === 'Reserved';
            let is_arrived = d.status === 'Checked In' || d.status === 'Checked Out';
            let badge = '';

            if (is_arrived) {
                badge = '<span class="badge-done"><i class="fa fa-check"></i> Arrived</span>';
            } else if (is_pending) {
                let is_past = frappe.datetime.get_diff(frappe.datetime.now_date(), d.arrival_date) > 0;
                if (is_past) badge = '<span class="badge-missed">No Show</span>';
                else badge = '<span class="badge-pending">Pending Check-in</span>';
            }

            html += `
            <div class="fd-list-item">
                <div style="flex:1;">
                    <div style="font-weight:600; font-size:14px;">
                        <a href="#" onclick="frappe.set_route('Form', 'Hotel Reservation', '${d.name}')">${d.guest_name}</a>
                    </div>
                    <div style="font-size:12px; color:#6c757d;">
                        <span class="fas fa-bed"></span> ${d.room || 'Unassigned'} &middot; ${d.room_type}
                    </div>
                </div>
                <div class="text-right">
                    <div style="margin-bottom:4px;">${badge}</div>
                    ${d.status === 'Reserved' ? `<button class="btn btn-xs btn-primary" onclick="frappe.set_route('Form', 'Hotel Reservation', '${d.name}')">Open</button>` : ''}
                </div>
            </div>`;
        });
    }
    $('#list-arrivals').html(html);
}

function render_departures(data) {
    let html = '';
    if (data.length === 0) {
        html = '<div class="text-center p-4 text-muted">No departures found for this date.</div>';
    } else {
        data.forEach(d => {
            let is_left = d.status === 'Checked Out';
            let is_pending = d.status === 'Checked In';
            let badge = '';

            if (is_left) {
                badge = '<span class="badge-done"><i class="fa fa-check"></i> Checked Out</span>';
            } else if (is_pending) {
                let is_past = frappe.datetime.get_diff(frappe.datetime.now_date(), d.departure_date) > 0;
                if (is_past) badge = '<span class="badge-missed">Overstay</span>';
                else badge = '<span class="badge-pending">Expected Departure</span>';
            }

            html += `
            <div class="fd-list-item">
                <div style="flex:1;">
                    <div style="font-weight:600; font-size:14px;">
                        <a href="#" onclick="frappe.set_route('Form', 'Hotel Reservation', '${d.name}')">${d.guest_name}</a>
                    </div>
                    <div style="font-size:12px; color:#6c757d;">
                        <span class="fas fa-door-open"></span> ${d.room} &middot; ${d.room_type}
                    </div>
                </div>
                <div class="text-right">
                    <div style="margin-bottom:4px;">${badge}</div>
                    ${d.status === 'Checked In' ? `<button class="btn btn-xs btn-danger" onclick="frappe.set_route('Form', 'Hotel Reservation', '${d.name}')">Checkout</button>` : ''}
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
                                d.set_value('room', r.room || '');
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