frappe.pages['tape-chart'].on_page_load = function (wrapper) {
    var page = frappe.ui.make_app_page({
        parent: wrapper,
        title: 'Tape Chart 2.0 (Reservation Calendar)',
        single_column: true
    });

    page.add_field({
        fieldname: 'start_date',
        label: 'Start Date',
        fieldtype: 'Date',
        default: frappe.datetime.now_date(),
        change: function () {
            render_tape_chart(wrapper, page);
        }
    });

    page.set_primary_action('Refresh', function () {
        render_tape_chart(wrapper, page);
    });

    $(`<style>
        #tape-chart-legend { margin: 10px 0; font-size: 12px; }
        #tape-chart-legend .tc-legend-swatch { display:inline-block; width:12px; height:12px; border-radius:2px; margin-right:4px; vertical-align:middle; }
        #tape-chart-legend .tc-legend-item { margin-right:16px; white-space:nowrap; }
        #tape-chart-container table { border-collapse: collapse; }
        #tape-chart-container th, #tape-chart-container td { border: 1px solid #e0e4e8; }
        .tc-room-row.tc-drop-hover { outline: 2px dashed #2f80ed; outline-offset: -2px; }
        .tc-booking-block { color: #fff; font-weight: 600; text-align: center; vertical-align: middle; cursor: grab; border-radius: 3px; padding: 2px 4px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
        .tc-booking-block:active { cursor: grabbing; }
        #tc-tooltip { position: fixed; z-index: 9999; background: #1f272e; color: #fff; padding: 10px 12px; border-radius: 6px; font-size: 12px; line-height: 1.5; box-shadow: 0 4px 14px rgba(0,0,0,0.25); max-width: 260px; pointer-events: none; display: none; }
        #tc-tooltip b { color: #fff; }
    </style>`).appendTo(wrapper);

    $(wrapper).find('.layout-main-section').append(`
        <div id="tape-chart-legend"></div>
        <div id="tape-chart-container" style="overflow-x: auto;"></div>
    `);
    $('body').append('<div id="tc-tooltip"></div>');

    render_tape_chart(wrapper, page);
};

function render_tape_chart(wrapper, page) {
    let start_date = page.fields_dict.start_date.get_value();
    let end_date = frappe.datetime.add_days(start_date, 14); // 2 week view

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
    let html = '';
    Object.keys(source_colors).forEach((key) => {
        html += `<span class="tc-legend-item"><span class="tc-legend-swatch" style="background:${source_colors[key]}"></span>${key}</span>`;
    });
    $('#tape-chart-legend').html(html);
}

function draw_grid(data, start, end) {
    let rooms = data.rooms;
    let bookings = data.bookings;
    let container = $('#tape-chart-container');
    container.empty();

    let dates = [];
    let curr = start;
    while (curr < end) {
        dates.push(curr);
        curr = frappe.datetime.add_days(curr, 1);
    }

    let html = `<table class="table table-bordered table-sm" style="font-size: 11px;">
        <thead><tr><th style="width: 90px; position: sticky; left: 0; background: #fff;">Room</th>`;
    dates.forEach((d) => {
        html += `<th style="min-width: 42px; text-align: center;">${d.split('-').slice(1).reverse().join('/')}</th>`;
    });
    html += `</tr></thead><tbody>`;

    rooms.forEach((room) => {
        let room_bookings = bookings
            .filter((b) => b.room === room.name)
            .sort((a, b) => (a.arrival_date < b.arrival_date ? -1 : 1));

        html += `<tr class="tc-room-row" data-room="${room.name}">
            <td style="position: sticky; left: 0; background: #fff;"><b>${room.room_number}</b><br><small class="text-muted">${room.room_type}</small></td>`;

        let date_idx = 0;
        while (date_idx < dates.length) {
            let date = dates[date_idx];
            let booking = room_bookings.find((b) => date >= b.arrival_date && date < b.departure_date);

            if (!booking) {
                html += `<td></td>`;
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

            let opacity = booking.status === 'Checked In' ? '1' : '0.55';
            html += `<td colspan="${span}" style="padding: 2px;">
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
            let balance = b.outstanding_balance != null ? frappe.format(b.outstanding_balance, { fieldtype: 'Currency' }) : '-';
            let source_line = b.source_category === 'OTA' && b.ota_platform ? `${b.source_category} (${b.ota_platform})` : b.source_category;
            tooltip.html(`
                <div><b>${b.guest_name || b.guest}</b></div>
                <div>${b.status} &middot; ${source_line}</div>
                <div>${b.arrival_date} &rarr; ${b.departure_date}</div>
                <div>Folio Balance: <b>${balance}</b></div>
                ${b.external_booking_id ? `<div>Booking Ref: ${b.external_booking_id}</div>` : ''}
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
                __('Move reservation {0} to Room {1}?', [payload.reservation, target_room]),
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
