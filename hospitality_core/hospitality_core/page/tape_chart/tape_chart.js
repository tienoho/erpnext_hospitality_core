var _tc_days_span = 14;

frappe.pages['tape-chart'].on_page_load = function (wrapper) {
    var page = frappe.ui.make_app_page({
        parent: wrapper,
        title: __('Tape Chart 2.0 (Sơ Đồ Đặt Phòng Trực Quan)'),
        single_column: true
    });

    page.add_field({
        fieldname: 'start_date',
        label: __('Từ Ngày'),
        fieldtype: 'Date',
        default: frappe.datetime.now_date(),
        change: function () {
            render_tape_chart(wrapper, page);
        }
    });

    page.set_primary_action(__('Làm Mới'), function () {
        render_tape_chart(wrapper, page);
    });

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
        #tape-chart-legend { margin: 12px 0; font-size: 12px; display: flex; flex-wrap: wrap; gap: 15px; align-items: center; }
        #tape-chart-legend .tc-legend-swatch { display:inline-block; width:12px; height:12px; border-radius:3px; margin-right:5px; vertical-align:middle; }
        #tape-chart-legend .tc-legend-item { white-space:nowrap; font-weight: 500; }
        #tape-chart-container table { border-collapse: collapse; background: #fff; }
        #tape-chart-container th, #tape-chart-container td { border: 1px solid #e2e8f0; }
        .tc-room-row.tc-drop-hover { outline: 2px dashed #2f80ed; outline-offset: -2px; }
        .tc-booking-block { color: #fff; font-weight: 600; text-align: center; vertical-align: middle; cursor: grab; border-radius: 4px; padding: 3px 6px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; box-shadow: 0 1px 3px rgba(0,0,0,0.1); }
        .tc-booking-block:active { cursor: grabbing; }
        #tc-tooltip { position: fixed; z-index: 9999; background: #1f272e; color: #fff; padding: 10px 14px; border-radius: 6px; font-size: 12px; line-height: 1.5; box-shadow: 0 4px 16px rgba(0,0,0,0.3); max-width: 280px; pointer-events: none; display: none; }
        #tc-tooltip b { color: #fff; }
    </style>`).appendTo(wrapper);

    $(wrapper).find('.layout-main-section').append(`
        <div id="tape-chart-legend"></div>
        <div id="tape-chart-container" style="overflow-x: auto; box-shadow: 0 2px 8px rgba(0,0,0,0.05); border-radius: 6px; margin-bottom: 25px;"></div>
    `);
    $('body').append('<div id="tc-tooltip"></div>');

    render_tape_chart(wrapper, page);
};

function render_tape_chart(wrapper, page) {
    let start_date = page.fields_dict.start_date.get_value() || frappe.datetime.now_date();
    let end_date = frappe.datetime.add_days(start_date, _tc_days_span);

    frappe.call({
        method: "hospitality_core.hospitality_core.page.tape_chart.tape_chart.get_chart_data",
        args: { start_date: start_date, end_date: end_date },
        freeze: true,
        callback: function (r) {
            if (r.message) {
                draw_legend(r.message.source_colors);
                draw_grid(r.message, start_date, end_date);
            }
        }
    });
}

function draw_legend(source_colors) {
    let html = '<span style="font-size:12px; color:#8d99a6; font-weight:600; text-transform:uppercase; margin-right:4px;">Nguồn khách:</span>';
    Object.keys(source_colors).forEach((key) => {
        html += `<span class="tc-legend-item"><span class="tc-legend-swatch" style="background:${source_colors[key]}"></span>${key}</span>`;
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
        <thead><tr><th style="width: 100px; position: sticky; left: 0; background: #f8f9fa; z-index: 2; vertical-align: middle; text-align: center;">${__('Phòng')}</th>`;
    
    dates.forEach((d) => {
        let is_today = (d === today_str);
        let date_obj = new Date(d);
        let day_idx = date_obj.getDay();
        let is_weekend = (day_idx === 0 || day_idx === 6);

        let bg = is_today ? '#e8f4fd' : (is_weekend ? '#f4f6f9' : '#fff');
        let border = is_today ? 'border-left: 2px solid #2f80ed; border-right: 2px solid #2f80ed;' : '';
        let today_badge = is_today ? `<br><span class="badge" style="background:#2f80ed; color:#fff; font-size:9px; padding:1px 4px;">${__('Hôm nay')}</span>` : '';
        let weekend_label = (is_weekend && !is_today) ? `<br><span style="color:#8d99a6; font-size:9px;">${day_idx === 0 ? 'CN' : 'T7'}</span>` : '';

        html += `<th style="min-width: 48px; text-align: center; background:${bg}; ${border}">
            ${d.split('-').slice(1).reverse().join('/')}${today_badge}${weekend_label}
        </th>`;
    });
    html += `</tr></thead><tbody>`;

    rooms.forEach((room) => {
        let room_bookings = bookings
            .filter((b) => b.room === room.name)
            .sort((a, b) => (a.arrival_date < b.arrival_date ? -1 : 1));

        html += `<tr class="tc-room-row" data-room="${room.name}">
            <td style="position: sticky; left: 0; background: #fff; z-index: 1; border-right: 2px solid #cbd5e1;">
                <b>${room.room_number || room.name}</b><br>
                <small class="text-muted" style="font-size:10px;">${room.room_type}</small>
            </td>`;

        let date_idx = 0;
        while (date_idx < dates.length) {
            let date = dates[date_idx];
            let booking = room_bookings.find((b) => date >= b.arrival_date && date < b.departure_date);

            if (!booking) {
                let is_today = (date === today_str);
                let date_obj = new Date(date);
                let is_weekend = (date_obj.getDay() === 0 || date_obj.getDay() === 6);
                let bg = is_today ? '#f0f7fd' : (is_weekend ? '#fafbfc' : '#fff');
                let border = is_today ? 'border-left: 2px solid #2f80ed; border-right: 2px solid #2f80ed;' : '';

                html += `<td style="background:${bg}; ${border}"></td>`;
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

            let opacity = booking.status === 'Checked In' ? '1' : '0.65';
            html += `<td colspan="${span}" style="padding: 2px; vertical-align: middle;">
                <div class="tc-booking-block"
                     draggable="true"
                     data-reservation="${booking.name}"
                     data-source-room="${room.name}"
                     style="background:${booking.color}; opacity:${opacity};"
                     onclick="frappe.set_route('Form', 'Hotel Reservation', '${booking.name}')">
                    ${booking.guest_name || booking.guest || ''}
                </div>
            </td>`;
            date_idx += span;
        }

        html += `</tr>`;
    });

    html += `</tbody></table>`;
    container.html(html);

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
                <div style="font-size:13px; font-weight:700; margin-bottom:2px;">${b.guest_name || b.guest}</div>
                <div style="color:#a0aec0; font-size:11px;">${b.status} &middot; <span style="color:#63b3ed;">${source_line}</span></div>
                <div style="margin-top:4px;">${b.arrival_date} &rarr; ${b.departure_date}</div>
                <div style="margin-top:2px;">Dư nợ Folio: <b style="color:#feb2b2;">${balance}</b></div>
                ${b.external_booking_id ? `<div style="color:#cbd5e0; font-size:11px;">Mã OTA: ${b.external_booking_id}</div>` : ''}
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
    $('.tc-booking-block').on('dragstart', function (e) {
        e.originalEvent.dataTransfer.setData('text/plain', JSON.stringify({
            reservation: $(this).data('reservation'),
            source_room: $(this).data('source-room')
        }));
    });

    $('.tc-room-row')
        .on('dragover', function (e) {
            e.preventDefault();
            $(this).addClass('tc-drop-hover');
        })
        .on('dragleave', function () {
            $(this).removeClass('tc-drop-hover');
        })
        .on('drop', function (e) {
            e.preventDefault();
            $(this).removeClass('tc-drop-hover');

            let payload;
            try {
                payload = JSON.parse(e.originalEvent.dataTransfer.getData('text/plain'));
            } catch (err) {
                return;
            }

            let target_room = $(this).data('room');
            if (!payload.reservation || target_room === payload.source_room) return;

            frappe.confirm(
                __('Chuyển đặt phòng {0} sang Phòng {1}?', [payload.reservation, target_room]),
                function () {
                    frappe.call({
                        method: 'hospitality_core.hospitality_core.page.tape_chart.tape_chart.move_booking',
                        args: { reservation_name: payload.reservation, new_room: target_room },
                        freeze: true,
                        callback: function (r) {
                            if (!r.exc) {
                                frappe.pages['tape-chart'].get_primary_action().trigger('click');
                            }
                        }
                    });
                }
            );
        });
}
