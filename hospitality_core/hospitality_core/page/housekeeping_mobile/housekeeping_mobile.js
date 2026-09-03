frappe.pages['housekeeping-mobile'].on_page_load = function (wrapper) {
    var page = frappe.ui.make_app_page({
        parent: wrapper,
        title: 'Housekeeping Mobile',
        single_column: true
    });

    $(`<style>
        .hkm-tabs { display:flex; position: sticky; top:0; z-index:10; background:#fff; border-bottom:1px solid #e0e4e8; margin-bottom:10px; }
        .hkm-tab { flex:1; text-align:center; padding:12px 4px; font-size:13px; font-weight:600; color:#8d99a6; cursor:pointer; }
        .hkm-tab.active { color:#2f80ed; border-bottom:2px solid #2f80ed; }
        .hkm-room-card { border:1px solid #e0e4e8; border-radius:8px; padding:14px; margin-bottom:10px; display:flex; justify-content:space-between; align-items:center; }
        .hkm-room-title { font-size:18px; font-weight:700; }
        .hkm-room-sub { font-size:12px; color:#8d99a6; }
        .hkm-status-pill { font-size:11px; padding:3px 10px; border-radius:12px; font-weight:600; color:#fff; }
        .hkm-btn-row { display:flex; gap:6px; flex-wrap:wrap; margin-top:8px; }
        .hkm-btn { flex:1; min-width:70px; padding:10px 6px; border-radius:6px; border:none; font-size:12px; font-weight:600; color:#fff; }
        .hkm-section { display:none; }
        .hkm-section.active { display:block; }
        .hkm-floor-filter { margin-bottom:10px; }
    </style>`).appendTo(wrapper);

    $(wrapper).find('.layout-main-section').append(`
        <div class="hkm-tabs">
            <div class="hkm-tab active" data-tab="rooms">${__('Rooms')}</div>
            <div class="hkm-tab" data-tab="minibar">${__('Minibar')}</div>
            <div class="hkm-tab" data-tab="lostfound">${__('Lost & Found')}</div>
            <div class="hkm-tab" data-tab="maintenance">${__('Maintenance')}</div>
        </div>

        <div id="hkm-section-rooms" class="hkm-section active">
            <select id="hkm-floor-filter" class="form-control hkm-floor-filter">
                <option value="">${__('All Floors')}</option>
            </select>
            <div id="hkm-room-list"></div>
        </div>

        <div id="hkm-section-minibar" class="hkm-section">
            <div class="form-group">
                <label>${__('Room')}</label>
                <input type="text" id="hkm-mb-room" class="form-control" placeholder="${__('Room number, e.g. 101')}">
            </div>
            <div id="hkm-mb-items"></div>
            <button class="btn btn-default btn-sm" id="hkm-mb-add-row" style="margin-bottom:10px;">+ ${__('Add Item')}</button>
            <button class="btn btn-primary btn-block" id="hkm-mb-submit">${__('Post to Folio')}</button>
        </div>

        <div id="hkm-section-lostfound" class="hkm-section">
            <div class="form-group"><label>${__('Item Description')}</label><input type="text" id="hkm-lf-item" class="form-control"></div>
            <div class="form-group"><label>${__('Found Location')}</label><input type="text" id="hkm-lf-location" class="form-control"></div>
            <button class="btn btn-primary btn-block" id="hkm-lf-submit">${__('Report Found Item')}</button>
        </div>

        <div id="hkm-section-maintenance" class="hkm-section">
            <div class="form-group"><label>${__('Room')}</label><input type="text" id="hkm-mnt-room" class="form-control"></div>
            <div class="form-group">
                <label>${__('Issue Type')}</label>
                <select id="hkm-mnt-type" class="form-control">
                    <option>Plumbing</option><option>Electrical</option><option>HVAC</option>
                    <option>Furniture</option><option>Cleaning</option><option>Other</option>
                </select>
            </div>
            <div class="form-group"><label>${__('Description')}</label><textarea id="hkm-mnt-desc" class="form-control"></textarea></div>
            <div class="form-group">
                <label>${__('Photo')}</label><br>
                <button class="btn btn-default btn-sm" id="hkm-mnt-attach">${__('Attach Photo')}</button>
                <div id="hkm-mnt-photo-preview" style="margin-top:8px;"></div>
            </div>
            <button class="btn btn-primary btn-block" id="hkm-mnt-submit">${__('Send to Technical Team')}</button>
        </div>
    `);

    setup_tabs(wrapper);
    setup_rooms_tab();
    setup_minibar_tab();
    setup_lostfound_tab();
    setup_maintenance_tab();
};

function setup_tabs(wrapper) {
    $(wrapper).on('click', '.hkm-tab', function () {
        let tab = $(this).data('tab');
        $('.hkm-tab').removeClass('active');
        $(this).addClass('active');
        $('.hkm-section').removeClass('active');
        $(`#hkm-section-${tab}`).addClass('active');
    });
}

const STATUS_COLORS = {
    'Available': '#27ae60', 'Occupied': '#2f80ed', 'Dirty': '#eb5757',
    'Cleaning': '#f2994a', 'Inspected': '#56ccf2', 'Out of Order': '#828282'
};

// Dirty -> Cleaning -> Inspected -> Available
const NEXT_STATUS = { 'Dirty': 'Cleaning', 'Cleaning': 'Inspected', 'Inspected': 'Available' };

function setup_rooms_tab() {
    frappe.call({
        method: 'hospitality_core.hospitality_core.api.housekeeping_mobile.get_floors',
        callback: function (r) {
            (r.message || []).forEach((floor) => {
                $('#hkm-floor-filter').append(`<option value="${floor}">${floor}</option>`);
            });
        }
    });

    $('#hkm-floor-filter').on('change', load_room_board);
    load_room_board();
}

function load_room_board() {
    frappe.call({
        method: 'hospitality_core.hospitality_core.api.housekeeping_mobile.get_my_board',
        args: { floor: $('#hkm-floor-filter').val() || null },
        callback: function (r) {
            let list = $('#hkm-room-list');
            list.empty();
            (r.message || []).forEach((room) => {
                let color = STATUS_COLORS[room.status] || '#828282';
                let next = NEXT_STATUS[room.status];
                list.append(`
                    <div class="hkm-room-card">
                        <div>
                            <div class="hkm-room-title">${room.room_number}</div>
                            <div class="hkm-room-sub">${room.room_type || ''} ${room.floor ? '&middot; Floor ' + room.floor : ''}</div>
                        </div>
                        <div style="text-align:right;">
                            <span class="hkm-status-pill" style="background:${color}">${room.status}</span>
                            ${next ? `<div class="hkm-btn-row"><button class="hkm-btn" style="background:${STATUS_COLORS[next]}" onclick="hkm_set_status('${room.name}','${next}')">${__('Mark')} ${next}</button></div>` : ''}
                        </div>
                    </div>
                `);
            });
        }
    });
}

window.hkm_set_status = function (room, status) {
    frappe.call({
        method: 'hospitality_core.hospitality_core.api.housekeeping_mobile.update_room_status',
        args: { room: room, status: status },
        callback: function () {
            load_room_board();
        }
    });
};

function setup_minibar_tab() {
    function add_row(item_code = '', qty = 1, amount = 0) {
        let idx = $('#hkm-mb-items .hkm-mb-row').length;
        $('#hkm-mb-items').append(`
            <div class="hkm-mb-row row" style="margin-bottom:6px;" data-idx="${idx}">
                <div class="col-xs-5"><input class="form-control input-sm hkm-mb-item" placeholder="${__('Item Code')}" value="${item_code}"></div>
                <div class="col-xs-3"><input class="form-control input-sm hkm-mb-qty" type="number" placeholder="Qty" value="${qty}"></div>
                <div class="col-xs-4"><input class="form-control input-sm hkm-mb-amount" type="number" placeholder="${__('Amount')}" value="${amount}"></div>
            </div>
        `);
    }
    add_row();
    $('#hkm-mb-add-row').on('click', () => add_row());

    $('#hkm-mb-submit').on('click', function () {
        let room = $('#hkm-mb-room').val();
        if (!room) { frappe.msgprint(__('Please enter a room number.')); return; }

        let items = [];
        $('#hkm-mb-items .hkm-mb-row').each(function () {
            let item = $(this).find('.hkm-mb-item').val();
            let qty = $(this).find('.hkm-mb-qty').val();
            let amount = $(this).find('.hkm-mb-amount').val();
            if (item && amount) items.push({ item: item, qty: qty, amount: amount });
        });

        if (!items.length) { frappe.msgprint(__('Add at least one item with an amount.')); return; }

        frappe.call({
            method: 'hospitality_core.hospitality_core.api.housekeeping_mobile.log_minibar_consumption',
            args: { room: room, items: items },
            freeze: true,
            callback: function (r) {
                if (!r.exc) {
                    frappe.show_alert({ message: __('Minibar consumption posted to folio.'), indicator: 'green' });
                    $('#hkm-mb-items').empty();
                    add_row();
                }
            }
        });
    });
}

function setup_lostfound_tab() {
    $('#hkm-lf-submit').on('click', function () {
        let item_name = $('#hkm-lf-item').val();
        let found_location = $('#hkm-lf-location').val();
        if (!item_name || !found_location) { frappe.msgprint(__('Please fill in both fields.')); return; }

        frappe.call({
            method: 'hospitality_core.hospitality_core.api.housekeeping_mobile.create_lost_and_found_report',
            args: { item_name: item_name, found_location: found_location },
            freeze: true,
            callback: function (r) {
                if (!r.exc) {
                    frappe.show_alert({ message: __('Lost & Found report created: {0}', [r.message]), indicator: 'green' });
                    $('#hkm-lf-item').val('');
                    $('#hkm-lf-location').val('');
                }
            }
        });
    });
}

function setup_maintenance_tab() {
    let attached_file_url = null;

    $('#hkm-mnt-attach').on('click', function () {
        new frappe.ui.FileUploader({
            allow_multiple: false,
            restrictions: { allowed_file_types: ['image/*'] },
            on_success: (file) => {
                attached_file_url = file.file_url;
                $('#hkm-mnt-photo-preview').html(`<img src="${file.file_url}" style="max-width:120px; border-radius:6px;">`);
            }
        });
    });

    $('#hkm-mnt-submit').on('click', function () {
        let room = $('#hkm-mnt-room').val();
        let issue_type = $('#hkm-mnt-type').val();
        let description = $('#hkm-mnt-desc').val();
        if (!room || !description) { frappe.msgprint(__('Please fill in Room and Description.')); return; }

        frappe.call({
            method: 'hospitality_core.hospitality_core.api.housekeeping_mobile.report_maintenance_issue',
            args: { room: room, issue_type: issue_type, description: description, image: attached_file_url },
            freeze: true,
            callback: function (r) {
                if (!r.exc) {
                    $('#hkm-mnt-room').val('');
                    $('#hkm-mnt-desc').val('');
                    $('#hkm-mnt-photo-preview').empty();
                    attached_file_url = null;
                }
            }
        });
    });
}
