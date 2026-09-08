frappe.pages['housekeeping-mobile'].on_page_load = function (wrapper) {
    var page = frappe.ui.make_app_page({
        parent: wrapper,
        title: __('Buồng Phòng Di Động (Housekeeping Mobile)'),
        single_column: true
    });

    $(`<style>
        .hkm-tabs { display:flex; position: sticky; top:0; z-index:10; background:#fff; border-bottom:1px solid #e2e8f0; margin-bottom:12px; }
        .hkm-tab { flex:1; text-align:center; padding:14px 4px; font-size:13px; font-weight:700; color:#64748b; cursor:pointer; }
        .hkm-tab.active { color:#2563eb; border-bottom:3px solid #2563eb; }
        .hkm-room-card { border:1px solid #e2e8f0; border-radius:10px; padding:14px 16px; margin-bottom:12px; display:flex; justify-content:space-between; align-items:center; box-shadow:0 1px 4px rgba(0,0,0,0.04); background:#fff; transition: transform 0.15s ease, box-shadow 0.15s ease; }
        .hkm-room-card:active { transform: scale(0.99); }
        .hkm-room-title { font-size:20px; font-weight:800; color:#1e293b; }
        .hkm-room-sub { font-size:12px; color:#64748b; margin-top:2px; }
        .hkm-status-pill { font-size:11px; padding:4px 12px; border-radius:12px; font-weight:700; color:#fff; }
        .hkm-btn-row { display:flex; gap:8px; flex-wrap:wrap; margin-top:10px; }
        .hkm-btn {
            flex:1; min-width:80px; min-height:44px; padding:10px 14px; border-radius:8px; border:none; font-size:13px; font-weight:700; color:#fff; display:flex; align-items:center; justify-content:center;
            transition: transform 0.12s cubic-bezier(0.4, 0, 0.2, 1), filter 0.12s ease;
            user-select: none;
            -webkit-tap-highlight-color: transparent;
        }
        .hkm-btn:active {
            transform: scale(0.96);
            filter: brightness(0.92);
        }
        .hkm-section { display:none; }
        .hkm-section.active { display:block; }
        .hkm-floor-filter { margin-bottom:12px; height:42px; border-radius:8px; font-size:14px; font-weight:600; }
        @keyframes hkm-shimmer {
            0% { background-position: -200% 0; }
            100% { background-position: 200% 0; }
        }
        .hkm-skeleton {
            background: linear-gradient(90deg, #f1f5f9 25%, #e2e8f0 50%, #f1f5f9 75%);
            background-size: 200% 100%;
            animation: hkm-shimmer 1.5s infinite;
            border-radius: 4px;
            display: inline-block;
        }
    </style>`).appendTo(wrapper);

    $(wrapper).find('.layout-main-section').append(`
        <div class="hkm-tabs">
            <div class="hkm-tab active" data-tab="rooms"><i class="fa fa-bed"></i> ${__('Buồng Phòng')}</div>
            <div class="hkm-tab" data-tab="minibar"><i class="fa fa-cocktail"></i> ${__('Minibar')}</div>
            <div class="hkm-tab" data-tab="lostfound"><i class="fa fa-box-open"></i> ${__('Đồ Thất Lạc')}</div>
            <div class="hkm-tab" data-tab="maintenance"><i class="fa fa-tools"></i> ${__('Báo Hỏng')}</div>
        </div>

        <div id="hkm-section-rooms" class="hkm-section active">
            <select id="hkm-floor-filter" class="form-control hkm-floor-filter">
                <option value="">${__('Tất Cả Các Tầng')}</option>
            </select>
            <div id="hkm-room-list"></div>
        </div>

        <div id="hkm-section-minibar" class="hkm-section">
            <div class="form-group">
                <label>${__('Số Phòng')}</label>
                <input type="text" id="hkm-mb-room" class="form-control" placeholder="${__('Nhập số phòng, ví dụ: 101')}">
            </div>
            <div id="hkm-mb-items"></div>
            <button class="btn btn-default btn-sm" id="hkm-mb-add-row" style="margin-bottom:10px;">+ ${__('Thêm Dòng')}</button>
            <button class="btn btn-primary btn-block" id="hkm-mb-submit">${__('Ghi Vào Folio')}</button>
        </div>

        <div id="hkm-section-lostfound" class="hkm-section">
            <div class="form-group"><label>${__('Mô Tả Vật Phẩm')}</label><input type="text" id="hkm-lf-item" class="form-control"></div>
            <div class="form-group"><label>${__('Vị Trí Tìm Thấy')}</label><input type="text" id="hkm-lf-location" class="form-control"></div>
            <button class="btn btn-primary btn-block" id="hkm-lf-submit">${__('Gửi Báo Cáo Đồ Thất Lạc')}</button>
        </div>

        <div id="hkm-section-maintenance" class="hkm-section">
            <div class="form-group"><label>${__('Số Phòng')}</label><input type="text" id="hkm-mnt-room" class="form-control"></div>
            <div class="form-group">
                <label>${__('Loại Sự Cố')}</label>
                <select id="hkm-mnt-type" class="form-control">
                    <option value="Plumbing">${__('Hệ thống nước (Plumbing)')}</option>
                    <option value="Electrical">${__('Hệ thống điện (Electrical)')}</option>
                    <option value="HVAC">${__('Điều hòa / Không khí (HVAC)')}</option>
                    <option value="Furniture">${__('Nội thất / Giường tủ (Furniture)')}</option>
                    <option value="Cleaning">${__('Vệ sinh phòng (Cleaning)')}</option>
                    <option value="Other">${__('Khác (Other)')}</option>
                </select>
            </div>
            <div class="form-group"><label>${__('Mô Tả Chi Tiết')}</label><textarea id="hkm-mnt-desc" class="form-control"></textarea></div>
            <div class="form-group">
                <label>${__('Hình Ảnh')}</label><br>
                <button class="btn btn-default btn-sm" id="hkm-mnt-attach">${__('Đính Kèm Ảnh')}</button>
                <div id="hkm-mnt-photo-preview" style="margin-top:8px;"></div>
            </div>
            <button class="btn btn-primary btn-block" id="hkm-mnt-submit">${__('Gửi Báo Cáo Sang Đội Kỹ Thuật')}</button>
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

const STATUS_LABELS = {
    'Available': __('Sạch'), 'Occupied': __('Đang ở'), 'Dirty': __('Cần dọn'),
    'Cleaning': __('Đang dọn'), 'Inspected': __('Đã kiểm tra'), 'Out of Order': __('Khóa phòng')
};

// Dirty -> Cleaning -> Inspected -> Available
const NEXT_STATUS = { 'Dirty': 'Cleaning', 'Cleaning': 'Inspected', 'Inspected': 'Available' };

function setup_rooms_tab() {
    frappe.call({
        method: 'hospitality_core.hospitality_core.api.housekeeping_mobile.get_floors',
        callback: function (r) {
            let $select = $('#hkm-floor-filter');
            $select.empty().append(`<option value="">${__('Tất Cả Các Tầng')}</option>`);
            (r.message || []).forEach((floor) => {
                $select.append(`<option value="${floor}">${__('Tầng')} ${floor}</option>`);
            });
        }
    });

    $('#hkm-floor-filter').on('change', load_room_board);
    load_room_board();
}

function load_room_board() {
    let list = $('#hkm-room-list');
    list.html(`
        <div class="hkm-room-card" style="opacity:0.75;">
            <div style="flex:1;">
                <div class="hkm-skeleton" style="width: 70px; height: 24px; margin-bottom: 6px;"></div>
                <div class="hkm-skeleton" style="width: 130px; height: 14px;"></div>
            </div>
            <div class="hkm-skeleton" style="width: 70px; height: 26px; border-radius: 12px;"></div>
        </div>
        <div class="hkm-room-card" style="opacity:0.75;">
            <div style="flex:1;">
                <div class="hkm-skeleton" style="width: 70px; height: 24px; margin-bottom: 6px;"></div>
                <div class="hkm-skeleton" style="width: 130px; height: 14px;"></div>
            </div>
            <div class="hkm-skeleton" style="width: 70px; height: 26px; border-radius: 12px;"></div>
        </div>
        <div class="hkm-room-card" style="opacity:0.75;">
            <div style="flex:1;">
                <div class="hkm-skeleton" style="width: 70px; height: 24px; margin-bottom: 6px;"></div>
                <div class="hkm-skeleton" style="width: 130px; height: 14px;"></div>
            </div>
            <div class="hkm-skeleton" style="width: 70px; height: 26px; border-radius: 12px;"></div>
        </div>
    `);

    frappe.call({
        method: 'hospitality_core.hospitality_core.api.housekeeping_mobile.get_my_board',
        args: { floor: $('#hkm-floor-filter').val() || null },
        callback: function (r) {
            list.empty();
            let rooms = r.message || [];
            let dirtyCount = rooms.filter(rm => rm.status === 'Dirty').length;
            let $roomTab = $('.hkm-tab[data-tab="rooms"]');
            $roomTab.html(`<i class="fa fa-bed"></i> ${__('Buồng Phòng')}` + (dirtyCount > 0 ? ` <span class="badge" style="background:#ef4444; color:#fff; font-size:10px; border-radius:10px; padding:2px 6px; margin-left:4px;">${dirtyCount}</span>` : ''));

            if (rooms.length === 0) {
                list.html(`
                    <div style="text-align:center; padding:40px 16px; background:#fff; border:1px solid #e2e8f0; border-radius:10px;">
                        <i class="fa fa-check-circle" style="font-size:36px; color:#10b981; margin-bottom:12px;"></i>
                        <h4 style="font-size:16px; font-weight:700; color:#1e293b; margin-bottom:4px;">${__('Không có phòng nào')}</h4>
                        <p style="font-size:12px; color:#64748b; margin:0;">${__('Tất cả phòng trong tầng đã được xử lý hoặc không có dữ liệu.')}</p>
                    </div>
                `);
                return;
            }

            rooms.forEach((room) => {
                let color = STATUS_COLORS[room.status] || '#828282';
                let next = NEXT_STATUS[room.status];
                list.append(`
                    <div class="hkm-room-card" id="hkm-card-${frappe.utils.escape_html(room.name)}">
                        <div>
                            <div class="hkm-room-title">${frappe.utils.escape_html(room.room_number)}</div>
                            <div class="hkm-room-sub">${frappe.utils.escape_html(room.room_type || '')} ${room.floor ? '&middot; ' + __('Tầng') + ' ' + room.floor : ''}</div>
                        </div>
                        <div style="text-align:right;">
                            <span class="hkm-status-pill" style="background:${color}">${STATUS_LABELS[room.status] || room.status}</span>
                            ${next ? `<div class="hkm-btn-row"><button class="hkm-btn hkm-status-btn" style="background:${STATUS_COLORS[next]}" data-room="${frappe.utils.escape_html(room.name)}" data-next="${next}"><i class="fa fa-arrow-right" style="margin-right:4px;"></i>${STATUS_LABELS[next] || next}</button></div>` : ''}
                        </div>
                    </div>
                `);
            });

            list.off('click', '.hkm-status-btn').on('click', '.hkm-status-btn', function (e) {
                e.stopPropagation();
                let $btn = $(this);
                let room = $btn.data('room');
                let next = $btn.data('next');
                $btn.prop('disabled', true).css('opacity', '0.85').html(`<i class="fa fa-spinner fa-spin" style="margin-right:4px;"></i>${STATUS_LABELS[next] || next}`);
                hkm_set_status(room, next);
            });
        }
    });
}

function trigger_haptic(pattern = 50) {
    if (window.navigator && window.navigator.vibrate) {
        try {
            window.navigator.vibrate(pattern);
        } catch (e) {
            // Ignore if vibration API is not allowed or unsupported
        }
    }
}

window.hkm_set_status = function (room, status) {
    frappe.call({
        method: 'hospitality_core.hospitality_core.api.housekeeping_mobile.update_room_status',
        args: { room: room, status: status },
        freeze: true,
        freeze_message: __('Đang cập nhật...'),
        callback: function (r) {
            if (!r || !r.exc) {
                trigger_haptic(50);
                frappe.show_alert({ message: __('Đã đổi trạng thái phòng thành công.'), indicator: 'green' });
            }
            load_room_board();
        }
    });
};

function setup_minibar_tab() {
    function add_row(item_code = '', qty = 1, amount = 0) {
        let idx = $('#hkm-mb-items .hkm-mb-row').length;
        $('#hkm-mb-items').append(`
            <div class="hkm-mb-row row" style="margin-bottom:6px;" data-idx="${idx}">
                <div class="col-xs-5"><input class="form-control input-sm hkm-mb-item" placeholder="${__('Mã Món')}" value="${item_code}"></div>
                <div class="col-xs-3"><input class="form-control input-sm hkm-mb-qty" type="number" placeholder="${__('SL')}" value="${qty}"></div>
                <div class="col-xs-4"><input class="form-control input-sm hkm-mb-amount" type="number" placeholder="${__('Số Tiền (VND)')}" value="${amount}"></div>
            </div>
        `);
    }
    add_row();
    $('#hkm-mb-add-row').on('click', () => add_row());

    $('#hkm-mb-submit').on('click', function () {
        let room = $('#hkm-mb-room').val();
        if (!room) { frappe.msgprint(__('Vui lòng nhập số phòng.')); return; }

        let items = [];
        $('#hkm-mb-items .hkm-mb-row').each(function () {
            let item = $(this).find('.hkm-mb-item').val();
            let qty = $(this).find('.hkm-mb-qty').val();
            let amount = $(this).find('.hkm-mb-amount').val();
            if (item && amount) items.push({ item: item, qty: qty, amount: amount });
        });

        if (!items.length) { frappe.msgprint(__('Vui lòng thêm ít nhất một món có số tiền.')); return; }

        frappe.call({
            method: 'hospitality_core.hospitality_core.api.housekeeping_mobile.log_minibar_consumption',
            args: { room: room, items: items },
            freeze: true,
            freeze_message: __('Đang ghi Folio...'),
            callback: function (r) {
                if (!r.exc) {
                    trigger_haptic(50);
                    frappe.show_alert({ message: __('Đã ghi nhận tiêu dùng minibar vào Folio.'), indicator: 'green' });
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
        if (!item_name || !found_location) { frappe.msgprint(__('Vui lòng nhập đủ Mô tả vật phẩm và Vị trí tìm thấy.')); return; }

        frappe.call({
            method: 'hospitality_core.hospitality_core.api.housekeeping_mobile.create_lost_and_found_report',
            args: { item_name: item_name, found_location: found_location },
            freeze: true,
            freeze_message: __('Đang lưu báo cáo...'),
            callback: function (r) {
                if (!r.exc) {
                    trigger_haptic(50);
                    frappe.show_alert({ message: __('Đã tạo báo cáo đồ thất lạc: {0}', [r.message]), indicator: 'green' });
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
        if (!room || !description) { frappe.msgprint(__('Vui lòng nhập Số phòng và Mô tả sự cố.')); return; }

        frappe.call({
            method: 'hospitality_core.hospitality_core.api.housekeeping_mobile.report_maintenance_issue',
            args: { room: room, issue_type: issue_type, description: description, image: attached_file_url },
            freeze: true,
            freeze_message: __('Đang gửi báo cáo kỹ thuật...'),
            callback: function (r) {
                if (!r.exc) {
                    trigger_haptic(50);
                    frappe.show_alert({ message: __('Đã gửi báo cáo kỹ thuật thành công.'), indicator: 'green' });
                    $('#hkm-mnt-room').val('');
                    $('#hkm-mnt-desc').val('');
                    $('#hkm-mnt-photo-preview').empty();
                    attached_file_url = null;
                }
            }
        });
    });
}
