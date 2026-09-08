var _tc_days_span = 14;
var _tc_data_cache = null;
var _tc_wrapper = null;
var _tc_page = null;

const HK_BADGES = {
    'Available': { label: 'Sạch', bg: '#10b981', color: '#fff' },
    'Dirty': { label: 'Bẩn', bg: '#ef4444', color: '#fff' },
    'Cleaning': { label: 'Đang dọn', bg: '#f59e0b', color: '#fff' },
    'Inspected': { label: 'Đã KT', bg: '#06b6d4', color: '#fff' },
    'Occupied': { label: 'Đang ở', bg: '#6366f1', color: '#fff' },
    'Out of Order': { label: 'Khóa', bg: '#64748b', color: '#fff' }
};

frappe.pages['tape-chart'].on_page_load = function (wrapper) {
    var page = frappe.ui.make_app_page({
        parent: wrapper,
        title: __('Tape Chart 2.0 (Sơ Đồ Buồng Phòng Trực Quan)'),
        single_column: true
    });
    _tc_wrapper = wrapper;
    _tc_page = page;

    // 1. Start Date Field
    page.add_field({
        fieldname: 'start_date',
        label: __('Từ Ngày'),
        fieldtype: 'Date',
        default: frappe.datetime.now_date(),
        change: function () {
            render_tape_chart(wrapper, page);
        }
    });

    // 2. Floor Filter
    page.add_field({
        fieldname: 'floor_filter',
        label: __('Tầng'),
        fieldtype: 'Select',
        options: [__('Tất Cả Các Tầng')],
        default: __('Tất Cả Các Tầng'),
        change: function () {
            apply_filters_and_redraw(page);
        }
    });

    // 3. Room Type Filter
    page.add_field({
        fieldname: 'type_filter',
        label: __('Loại Phòng'),
        fieldtype: 'Select',
        options: [__('Tất Cả Loại Phòng')],
        default: __('Tất Cả Loại Phòng'),
        change: function () {
            apply_filters_and_redraw(page);
        }
    });

    // Primary Refresh
    page.set_primary_action(__('Làm Mới'), function () {
        render_tape_chart(wrapper, page);
    });

    // Quick Date Navigation
    page.add_inner_button(__('◀ Tuần Trước'), function () {
        let cur = page.fields_dict.start_date.get_value() || frappe.datetime.now_date();
        page.fields_dict.start_date.set_value(frappe.datetime.add_days(cur, -7));
    });
    page.add_inner_button(__('Hôm Nay'), function () {
        page.fields_dict.start_date.set_value(frappe.datetime.now_date());
        setTimeout(() => {
            let today_th = $('#tape-chart-container th').filter(function () {
                return $(this).text().includes('Hôm nay');
            });
            if (today_th.length) {
                let container = $('#tape-chart-container');
                let scrollLeft = today_th.position().left - container.width() / 2 + today_th.width() / 2;
                container.animate({ scrollLeft: container.scrollLeft() + scrollLeft }, 300);
            }
        }, 350);
    });
    page.add_inner_button(__('Tuần Sau ▶'), function () {
        let cur = page.fields_dict.start_date.get_value() || frappe.datetime.now_date();
        page.fields_dict.start_date.set_value(frappe.datetime.add_days(cur, 7));
    });

    // Days Span Buttons
    page.add_inner_button(__('7 Ngày'), function () {
        _tc_days_span = 7;
        render_tape_chart(wrapper, page);
    });
    page.add_inner_button(__('14 Ngày'), function () {
        _tc_days_span = 14;
        render_tape_chart(wrapper, page);
    });
    page.add_inner_button(__('30 Ngày'), function () {
        _tc_days_span = 30;
        render_tape_chart(wrapper, page);
    });
    page.add_inner_button(__('Tra Cứu Phòng Trống & OCC'), function () {
        frappe.set_route('availability-tool');
    });

    $(`<style>
        #tape-chart-legend {
            margin: 14px 0 10px 0;
            font-size: 12px;
            display: flex;
            flex-wrap: wrap;
            gap: 16px;
            align-items: center;
            background: #f8fafc;
            padding: 10px 14px;
            border-radius: 8px;
            border: 1px solid #e2e8f0;
        }
        #tape-chart-legend .tc-legend-swatch {
            display: inline-block;
            width: 12px;
            height: 12px;
            border-radius: 3px;
            margin-right: 6px;
            vertical-align: middle;
        }
        #tape-chart-legend .tc-legend-item {
            white-space: nowrap;
            font-weight: 600;
            color: #334155;
        }
        #tape-chart-container table {
            border-collapse: collapse;
            background: #fff;
        }
        #tape-chart-container th, #tape-chart-container td {
            border: 1px solid #e2e8f0;
        }
        .tc-room-row.tc-drop-hover {
            outline: 2px solid #10b981;
            outline-offset: -2px;
            background: #ecfdf5 !important;
            box-shadow: 0 0 12px rgba(16, 185, 129, 0.25) inset;
        }
        .tc-room-row.tc-drop-conflict {
            outline: 2px solid #ef4444;
            outline-offset: -2px;
            background: #fef2f2 !important;
            box-shadow: 0 0 12px rgba(239, 68, 68, 0.25) inset;
        }
        .tc-empty-cell {
            cursor: pointer;
            position: relative;
            transition: background 0.15s ease, box-shadow 0.15s ease;
        }
        .tc-empty-cell:hover {
            background: #e0f2fe !important;
            box-shadow: inset 0 0 0 1.5px #0284c7;
        }
        .tc-empty-cell:active {
            transform: scale(0.98);
        }
        @keyframes tc-shimmer {
            0% { background-position: -200% 0; }
            100% { background-position: 200% 0; }
        }
        .tc-skeleton {
            background: linear-gradient(90deg, #f1f5f9 25%, #e2e8f0 50%, #f1f5f9 75%);
            background-size: 200% 100%;
            animation: tc-shimmer 1.5s infinite;
            border-radius: 4px;
            display: inline-block;
        }
        .tc-booking-block {
            color: #fff;
            font-weight: 700;
            text-align: center;
            vertical-align: middle;
            cursor: grab;
            cursor: -webkit-grab;
            border-radius: 5px;
            padding: 4px 8px;
            white-space: nowrap;
            overflow: hidden;
            text-overflow: ellipsis;
            box-shadow: 0 1px 4px rgba(0,0,0,0.15);
            transition: transform 0.15s ease, box-shadow 0.15s ease, opacity 0.15s ease;
        }
        .tc-booking-block:hover {
            transform: translateY(-1px);
            box-shadow: 0 4px 8px rgba(0,0,0,0.22);
        }
        .tc-booking-block:active {
            cursor: grabbing;
            cursor: -webkit-grabbing;
            transform: scale(0.98);
        }
        #tc-tooltip {
            position: fixed;
            z-index: 9999;
            background: #0f172a;
            color: #fff;
            padding: 12px 16px;
            border-radius: 8px;
            font-size: 12px;
            line-height: 1.5;
            box-shadow: 0 10px 25px rgba(0,0,0,0.35);
            max-width: 300px;
            pointer-events: none;
            display: none;
            border: 1px solid #334155;
        }
        #tc-tooltip b { color: #fff; }
    </style>`).appendTo(wrapper);

    $(wrapper).find('.layout-main-section').append(`
        <div id="tape-chart-legend"></div>
        <div id="tape-chart-container" style="overflow-x: auto; box-shadow: 0 2px 10px rgba(0,0,0,0.06); border-radius: 8px; margin-bottom: 25px;"></div>
    `);
    $('body').find('#tc-tooltip').remove();
    $('body').append('<div id="tc-tooltip"></div>');

    // Hotkeys: ArrowLeft/ArrowRight to navigate weeks, Escape to dismiss tooltip
    $(document).off('keydown.tc_hotkey').on('keydown.tc_hotkey', function (e) {
        if (!$('#tape-chart-container').is(':visible')) return;
        if ($(e.target).is('input, textarea, select, [contenteditable]')) return;
        if ($('.modal.show, .modal.in').length) return;

        if (e.key === 'ArrowLeft') {
            let cur = page.fields_dict.start_date.get_value() || frappe.datetime.now_date();
            page.fields_dict.start_date.set_value(frappe.datetime.add_days(cur, -7));
        } else if (e.key === 'ArrowRight') {
            let cur = page.fields_dict.start_date.get_value() || frappe.datetime.now_date();
            page.fields_dict.start_date.set_value(frappe.datetime.add_days(cur, 7));
        } else if (e.key === 'Escape') {
            $('#tc-tooltip').hide();
        }
    });

    render_tape_chart(wrapper, page);
};

function show_tape_chart_skeleton() {
    let container = $('#tape-chart-container');
    let rows = Array(8).fill(0).map(() => `
        <tr>
            <td style="width:140px; padding:8px;"><span class="tc-skeleton" style="width:90px; height:18px;"></span></td>
            ${Array(14).fill(0).map(() => `<td><span class="tc-skeleton" style="width:100%; height:28px;"></span></td>`).join('')}
        </tr>
    `).join('');
    container.html(`
        <table class="table table-bordered table-sm" style="margin-bottom:0; background:#fff;">
            <thead><tr><th style="width:140px;"><span class="tc-skeleton" style="width:80px; height:16px;"></span></th>${Array(14).fill(0).map(() => `<th><span class="tc-skeleton" style="width:36px; height:16px;"></span></th>`).join('')}</tr></thead>
            <tbody>${rows}</tbody>
        </table>
    `);
}

function render_tape_chart(wrapper, page) {
    let start_date = page.fields_dict.start_date.get_value() || frappe.datetime.now_date();
    let end_date = frappe.datetime.add_days(start_date, _tc_days_span);

    // Hiển thị khung xương Shimmer tạo cảm giác mượt mà tức thì
    show_tape_chart_skeleton();

    frappe.call({
        method: "hospitality_core.hospitality_core.page.tape_chart.tape_chart.get_chart_data",
        args: { start_date: start_date, end_date: end_date },
        callback: function (r) {
            if (r.message) {
                _tc_data_cache = r.message;
                populate_filters(page, r.message.rooms || []);
                draw_legend(r.message.source_colors);
                apply_filters_and_redraw(page);
            }
        }
    });
}

function populate_filters(page, rooms) {
    let floors = new Set();
    let types = new Set();

    rooms.forEach(r => {
        if (r.floor) floors.add(r.floor);
        if (r.room_type) types.add(r.room_type);
    });

    let floor_options = [__('Tất Cả Các Tầng'), ...Array.from(floors).sort((a,b) => String(a).localeCompare(String(b), undefined, {numeric: true}))];
    let type_options = [__('Tất Cả Loại Phòng'), ...Array.from(types).sort()];

    let cur_floor = page.fields_dict.floor_filter.get_value();
    let cur_type = page.fields_dict.type_filter.get_value();

    page.fields_dict.floor_filter.df.options = floor_options;
    page.fields_dict.floor_filter.refresh();
    if (floor_options.includes(cur_floor)) page.fields_dict.floor_filter.set_value(cur_floor);

    page.fields_dict.type_filter.df.options = type_options;
    page.fields_dict.type_filter.refresh();
    if (type_options.includes(cur_type)) page.fields_dict.type_filter.set_value(cur_type);
}

function apply_filters_and_redraw(page) {
    if (!_tc_data_cache) return;

    let start_date = page.fields_dict.start_date.get_value() || frappe.datetime.now_date();
    let end_date = frappe.datetime.add_days(start_date, _tc_days_span);

    let selected_floor = page.fields_dict.floor_filter ? page.fields_dict.floor_filter.get_value() : null;
    let selected_type = page.fields_dict.type_filter ? page.fields_dict.type_filter.get_value() : null;

    let all_rooms = _tc_data_cache.rooms || [];
    let filtered_rooms = all_rooms.filter(r => {
        let match_floor = (!selected_floor || selected_floor === __('Tất Cả Các Tầng') || String(r.floor) === String(selected_floor));
        let match_type = (!selected_type || selected_type === __('Tất Cả Loại Phòng') || r.room_type === selected_type);
        return match_floor && match_type;
    });

    draw_grid({ rooms: filtered_rooms, bookings: _tc_data_cache.bookings || [] }, start_date, end_date);
}

function draw_legend(source_colors) {
    let html = `<span style="font-size:12px; color:#64748b; font-weight:700; text-transform:uppercase; margin-right:4px;">${__('Nguồn khách:')}</span>`;
    Object.keys(source_colors).forEach((key) => {
        html += `<span class="tc-legend-item"><span class="tc-legend-swatch" style="background:${source_colors[key]}"></span>${key}</span>`;
    });

    html += `<span style="border-left: 1px solid #cbd5e1; height: 16px; margin: 0 4px;"></span>`;
    html += `<span style="font-size:12px; color:#64748b; font-weight:700; text-transform:uppercase; margin-right:4px;">${__('Buồng phòng:')}</span>`;
    Object.keys(HK_BADGES).forEach(st => {
        let b = HK_BADGES[st];
        html += `<span class="tc-legend-item"><span class="tc-legend-swatch" style="background:${b.bg}; border-radius: 50%;"></span>${b.label}</span>`;
    });

    $('#tape-chart-legend').html(html);
}

function draw_grid(data, start, end) {
    let rooms = data.rooms || [];
    let bookings = data.bookings || [];
    let container = $('#tape-chart-container');
    container.empty();

    let dates = [];
    let curr = start;
    while (curr < end) {
        dates.push(curr);
        curr = frappe.datetime.add_days(curr, 1);
    }

    let today_str = frappe.datetime.now_date();

    let html = `<table class="table table-bordered table-sm" style="font-size: 11px; margin-bottom: 0;">
        <thead><tr><th style="min-width: 140px; position: sticky; left: 0; background: #f8fafc; z-index: 2; vertical-align: middle; text-align: center; font-weight:700;">${__('Phòng & Trạng Thái')}</th>`;
    
    dates.forEach((d) => {
        let is_today = (d === today_str);
        let date_obj = new Date(d);
        let day_idx = date_obj.getDay();
        let is_weekend = (day_idx === 0 || day_idx === 6);

        let bg = is_today ? '#e0f2fe' : (is_weekend ? '#f1f5f9' : '#fff');
        let border = is_today ? 'border-left: 2px solid #0284c7; border-right: 2px solid #0284c7;' : '';
        let today_badge = is_today ? `<br><span class="badge" style="background:#0284c7; color:#fff; font-size:9px; padding:1px 4px; border-radius:3px;">${__('Hôm nay')}</span>` : '';
        let weekend_label = (is_weekend && !is_today) ? `<br><span style="color:#94a3b8; font-size:9px;">${day_idx === 0 ? 'CN' : 'T7'}</span>` : '';

        html += `<th style="min-width: 48px; text-align: center; background:${bg}; ${border}">
            ${d.split('-').slice(1).reverse().join('/')}${today_badge}${weekend_label}
        </th>`;
    });
    html += `</tr></thead><tbody>`;

    if (rooms.length === 0) {
        html += `<tr><td colspan="${dates.length + 1}" class="text-center p-4 text-muted">${__('Không có phòng nào khớp với bộ lọc đã chọn.')}</td></tr>`;
    }

    rooms.forEach((room) => {
        let room_bookings = bookings
            .filter((b) => b.room === room.name)
            .sort((a, b) => (a.arrival_date < b.arrival_date ? -1 : 1));

        let hk = HK_BADGES[room.status] || { label: room.status || 'Chưa rõ', bg: '#94a3b8', color: '#fff' };

        html += `<tr class="tc-room-row" data-room="${room.name}" data-room-number="${frappe.utils.escape_html(room.room_number || room.name)}">
            <td style="position: sticky; left: 0; background: #fff; z-index: 1; border-right: 2px solid #cbd5e1; padding: 5px 8px;">
                <div style="display:flex; align-items:center; justify-content:space-between; gap:6px;">
                    <b style="font-size:12px; color:#1e293b;">${frappe.utils.escape_html(room.room_number || room.name)}</b>
                    <span class="badge" style="background:${hk.bg}; color:${hk.color}; font-size:9px; padding:2px 6px; border-radius:4px; font-weight:600;" title="${hk.label}">${hk.label}</span>
                </div>
                <div style="font-size:10px; color:#64748b; margin-top:2px;">
                    ${frappe.utils.escape_html(room.room_type || '')} ${room.floor ? '&middot; T.' + frappe.utils.escape_html(room.floor) : ''}
                </div>
            </td>`;

        let date_idx = 0;
        while (date_idx < dates.length) {
            let date = dates[date_idx];
            let booking = room_bookings.find((b) => date >= b.arrival_date && date < b.departure_date);

            if (!booking) {
                let is_today = (date === today_str);
                let date_obj = new Date(date);
                let is_weekend = (date_obj.getDay() === 0 || date_obj.getDay() === 6);
                let bg = is_today ? '#f0f9ff' : (is_weekend ? '#fafbfc' : '#fff');
                let border = is_today ? 'border-left: 2px solid #0284c7; border-right: 2px solid #0284c7;' : '';

                let cell_title = __('Bấm để tạo đặt phòng: Phòng {0} - Ngày {1}', [room.room_number || room.name, date]);
                html += `<td class="tc-empty-cell" data-room="${frappe.utils.escape_html(room.name)}" data-room-number="${frappe.utils.escape_html(room.room_number || room.name)}" data-room-type="${frappe.utils.escape_html(room.room_type || '')}" data-date="${date}" style="background:${bg}; ${border}" title="${cell_title}"></td>`;
                date_idx += 1;
                continue;
            }

            // Merge consecutive days belonging to the same booking into one draggable block.
            let span = 0;
            while (
                date_idx + span < dates.length &&
                dates[date_idx + span] >= booking.arrival_date &&
                dates[date_idx + span] < booking.departure_date
            ) {
                span += 1;
            }

            if (span <= 0) span = 1;

            let opacity = booking.status === 'Checked In' ? '1' : '0.75';
            html += `<td colspan="${span}" style="padding: 2px; vertical-align: middle;">
                <div class="tc-booking-block"
                     draggable="true"
                     data-reservation="${frappe.utils.escape_html(booking.name)}"
                     data-source-room="${frappe.utils.escape_html(room.name)}"
                     style="background:${booking.color}; opacity:${opacity};">
                    ${frappe.utils.escape_html(booking.guest_name || booking.guest || __('Khách vãng lai'))}
                </div>
            </td>`;
            date_idx += span;
        }

        html += `</tr>`;
    });

    html += `</tbody></table>`;
    container.html(html);

    container.find('.tc-booking-block').on('click', function () {
        tc_open_booking_drawer($(this).data('reservation'));
    });

    container.off('click', '.tc-empty-cell').on('click', '.tc-empty-cell', function () {
        let $cell = $(this);
        let room_name = $cell.data('room');
        let room_number = $cell.data('room-number') || room_name;
        let room_type = $cell.data('room-type');
        let date = $cell.data('date');
        let next_date = frappe.datetime.add_days(date, 1);

        tc_open_quick_booking_dialog(room_name, room_number, room_type, date, next_date);
    });

    attach_tooltip_handlers(bookings);
    attach_drag_handlers();
}

function attach_tooltip_handlers(bookings) {
    let tooltip = $('#tc-tooltip');
    let by_name = {};
    bookings.forEach((b) => (by_name[b.name] = b));

    $('.tc-booking-block')
        .on('mouseenter', function (e) {
            let b = by_name[$(this).data('reservation')];
            if (!b) return;
            let balance = b.outstanding_balance != null ? frappe.format(b.outstanding_balance, { fieldtype: 'Currency' }) : '0 VND';
            let source_line = b.source_category === 'OTA' && b.ota_platform ? `${b.source_category} (${b.ota_platform})` : b.source_category;
            tooltip.html(`
                <div style="font-size:13px; font-weight:700; margin-bottom:2px;">${frappe.utils.escape_html(b.guest_name || b.guest || '')}</div>
                <div style="color:#94a3b8; font-size:11px;">${frappe.utils.escape_html(b.status || '')} &middot; <span style="color:#38bdf8;">${frappe.utils.escape_html(source_line || '')}</span></div>
                <div style="margin-top:4px;">${b.arrival_date} &rarr; ${b.departure_date}</div>
                <div style="margin-top:2px;">${__('Dư nợ Folio:')} <b style="color:${b.outstanding_balance > 0 ? '#f87171' : '#4ade80'};">${balance}</b></div>
                ${b.external_booking_id ? `<div style="color:#cbd5e1; font-size:11px;">Mã OTA: ${frappe.utils.escape_html(b.external_booking_id)}</div>` : ''}
                <div style="margin-top:6px; font-size:10px; color:#cbd5e1; font-style:italic;">💡 ${__('Bấm để mở thao tác nhanh')}</div>
            `).show();
        })
        .on('mousemove', function (e) {
            tooltip.css({ top: e.clientY + 14, left: e.clientX + 14 });
        })
        .on('mouseleave', function () {
            tooltip.hide();
        });
}

function attach_drag_handlers() {
    $('.tc-booking-block')
        .on('dragstart', function (e) {
            $(this).css('opacity', '0.45');
            $('#tc-tooltip').hide();
            e.originalEvent.dataTransfer.setData('text/plain', JSON.stringify({
                reservation: $(this).data('reservation'),
                source_room: $(this).data('source-room')
            }));
        })
        .on('dragend', function () {
            $(this).css('opacity', '');
            $('.tc-room-row').removeClass('tc-drop-hover tc-drop-conflict');
        });

    $('.tc-room-row')
        .on('dragover', function (e) {
            e.preventDefault();
            let target_room = $(this).data('room');
            let room_obj = (_tc_data_cache && _tc_data_cache.rooms ? _tc_data_cache.rooms : []).find(r => r.name === target_room);
            if (room_obj && (room_obj.status === 'Out of Order' || room_obj.status === 'Out of Service')) {
                $(this).addClass('tc-drop-conflict').removeClass('tc-drop-hover');
            } else {
                $(this).addClass('tc-drop-hover').removeClass('tc-drop-conflict');
            }
        })
        .on('dragleave', function () {
            $(this).removeClass('tc-drop-hover tc-drop-conflict');
        })
        .on('drop', function (e) {
            e.preventDefault();
            $(this).removeClass('tc-drop-hover tc-drop-conflict');

            let payload;
            try {
                payload = JSON.parse(e.originalEvent.dataTransfer.getData('text/plain'));
            } catch (err) {
                return;
            }

            let target_room = $(this).data('room');
            let target_room_number = $(this).data('room-number') || target_room;
            if (!payload.reservation || target_room === payload.source_room) return;

            frappe.confirm(
                __('Chuyển đặt phòng {0} sang Phòng {1}?', [payload.reservation, target_room_number]),
                function () {
                    frappe.call({
                        method: 'hospitality_core.hospitality_core.page.tape_chart.tape_chart.move_booking',
                        args: { reservation_name: payload.reservation, new_room: target_room },
                        freeze: true,
                        freeze_message: __('Đang đổi buồng phòng...'),
                        callback: function (r) {
                            if (!r.exc) {
                                if (_tc_wrapper && _tc_page) {
                                    render_tape_chart(_tc_wrapper, _tc_page);
                                }
                            }
                        }
                    });
                }
            );
        });
}

// Quick View Popover / Drawer for Fast Actions
window.tc_open_booking_drawer = function (res_name) {
    $('#tc-tooltip').hide();
    if (!_tc_data_cache) return;
    let b = (_tc_data_cache.bookings || []).find(x => x.name === res_name);
    if (!b) return;

    let balance_color = (b.outstanding_balance > 0) ? '#dc2626' : '#16a34a';
    let balance_str = b.outstanding_balance != null ? frappe.format(b.outstanding_balance, { fieldtype: 'Currency' }) : '0 VND';
    let source_label = b.source_category === 'OTA' && b.ota_platform ? `${b.source_category} (${b.ota_platform})` : b.source_category;

    let d = new frappe.ui.Dialog({
        title: __('Thông Tin Đặt Phòng: {0}', [b.name]),
        fields: [
            {
                fieldtype: 'HTML',
                fieldname: 'summary_html',
                options: `
                    <div style="background: #f8fafc; border: 1px solid #e2e8f0; border-radius: 8px; padding: 16px; margin-bottom: 15px;">
                        <div style="display:flex; justify-content:space-between; align-items:flex-start; margin-bottom: 12px;">
                            <div>
                                <h4 style="margin:0 0 4px 0; color:#1e293b;">${frappe.utils.escape_html(b.guest_name || b.guest || __('Khách vãng lai'))}</h4>
                                <div style="font-size:12px; color:#64748b;">
                                    ${b.guest_phone ? `<i class="fa fa-phone"></i> <a href="tel:${b.guest_phone}">${b.guest_phone}</a> &middot; ` : ''}
                                    <span class="badge badge-info">${source_label}</span>
                                </div>
                            </div>
                            <span class="badge" style="background:${b.status === 'Checked In' ? '#10b981' : '#f59e0b'}; color:#fff; font-size:11px; padding:4px 8px;">${b.status}</span>
                        </div>
                        <div class="row" style="font-size:13px; line-height: 1.8;">
                            <div class="col-sm-6">
                                <div><span class="text-muted">${__('Phòng:')}</span> <b>${frappe.utils.escape_html(b.room_number || b.room || __('Chưa xếp'))}</b></div>
                                <div><span class="text-muted">${__('Lưu trú:')}</span> ${b.arrival_date} &rarr; ${b.departure_date}</div>
                            </div>
                            <div class="col-sm-6 text-right">
                                <div><span class="text-muted">${__('Dư nợ Folio:')}</span> <b style="color:${balance_color}; font-size:15px;">${balance_str}</b></div>
                                ${b.external_booking_id ? `<div style="font-size:11px; color:#64748b;">Ref: ${frappe.utils.escape_html(b.external_booking_id)}</div>` : ''}
                            </div>
                        </div>
                    </div>
                `
            }
        ],
        primary_action_label: __('Mở Đặt Phòng Chi Tiết'),
        primary_action: function () {
            d.hide();
            frappe.set_route('Form', 'Hotel Reservation', b.name);
        }
    });

    if (b.folio) {
        d.add_custom_action(__('Mở Folio Thanh Toán'), function () {
            d.hide();
            frappe.set_route('Form', 'Guest Folio', b.folio);
        });
    }

    d.show();
};

window.tc_open_quick_booking_dialog = function (room_name, room_number, room_type, arr_date, dep_date) {
    let d = new frappe.ui.Dialog({
        title: __('⚡ Tạo Đặt Phòng Nhanh - Phòng {0}', [room_number]),
        fields: [
            {
                fieldname: 'info_html',
                fieldtype: 'HTML',
                options: `
                    <div style="background:#f0f9ff; border:1px solid #bae6fd; border-radius:8px; padding:14px; margin-bottom:14px;">
                        <div style="font-size:14px; color:#0369a1; font-weight:700; margin-bottom:4px;">
                            <i class="fa fa-bed"></i> ${__('Phòng')} <b>${frappe.utils.escape_html(room_number)}</b> &middot; <span style="font-weight:normal;">${frappe.utils.escape_html(room_type)}</span>
                        </div>
                        <div style="font-size:13px; color:#0284c7;">
                            <i class="fa fa-calendar-alt"></i> ${arr_date} &rarr; ${dep_date} (1 ${__('đêm')})
                        </div>
                    </div>
                `
            },
            {
                fieldname: 'guest',
                fieldtype: 'Link',
                options: 'Guest',
                label: __('Khách Hàng'),
                reqd: 1
            },
            {
                fieldname: 'rate_plan',
                fieldtype: 'Link',
                options: 'Room Rate Plan',
                label: __('Gói Giá (Rate Plan)'),
                get_query: () => ({ filters: { room_type: room_type, active: 1 } })
            }
        ],
        primary_action_label: __('Mở Form Chi Tiết'),
        primary_action(vals) {
            d.hide();
            frappe.new_doc('Hotel Reservation', {
                room: room_name,
                room_type: room_type,
                arrival_date: arr_date,
                departure_date: dep_date,
                guest: vals.guest,
                rate_plan: vals.rate_plan || undefined
            });
        }
    });
    d.show();
};
