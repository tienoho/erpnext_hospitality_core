const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const path = require('node:path');
const core = path.join(__dirname, '../hospitality_core/hospitality_core');
let handlers, requests = [], html = '';
const context = {
    frappe: {ui: {form: {on: (_, h) => { handlers = h; }}}, call: r => requests.push(r),
        boot: {sysdefaults: {currency: 'VND'}}, utils: {escape_html: s => s.replace(/</g, '&lt;').replace(/>/g, '&gt;')}},
    format_currency: value => String(value), __: s => s
};
vm.createContext(context);
vm.runInContext(fs.readFileSync(path.join(core, 'doctype/hotel_reservation/hotel_reservation.js'), 'utf8'), context);
const frm = {is_new: () => false, doc: {name: 'R', room: '101', room_type: 'Standard', rate_plan: 'P',
    arrival_date: '2026-09-03', departure_date: '2026-09-05'},
    fields_dict: {room_rate_preview: {$wrapper: {html: value => { html = value; }}}}};
const quote = value => ({nights: 3, total: value, nightly_rates: [
    {date: '2026-09-03', season_name: '<script>', base_rate: 100, los_discount: 10, los_percent: 10, manual_discount: 0, final_rate: 90},
    {date: '2026-09-04', base_rate: 200, los_discount: 20, los_percent: 10, manual_discount: 0, final_rate: 180}
]});
context.render_room_rate_preview(frm);
frm.doc.departure_date = '2026-09-06';
context.render_room_rate_preview(frm);
assert.equal(requests[1].args.reservation_name, 'R');
requests[1].callback({message: quote(450)});
const newest = html;
requests[0].callback({message: quote(999)});
assert.equal(html, newest, 'Phản hồi cũ không được ghi đè giá mới');
requests[0].error();
assert.equal(html, newest, 'Lỗi của request cũ không được xóa giá mới');
assert.ok(html.includes('450'));
assert.ok(html.includes('2026-09-03') && html.includes('2026-09-04'));
assert.ok(html.includes('&lt;script&gt;') && !html.includes('<script>'));
frm.doc.room = null;
context.render_room_rate_preview(frm);
const empty = html;
requests[1].callback({message: quote(450)});
assert.equal(html, empty, 'Xóa phòng phải vô hiệu hóa request đang chạy');
assert.ok(handlers.refresh.toString().includes('render_room_rate_preview'));

vm.runInContext(fs.readFileSync(path.join(core, 'doctype/room_rate_plan/room_rate_plan.js'), 'utf8'), context);
context.frappe.throw = message => { throw new Error(message); };
assert.throws(() => handlers.validate({doc: {los_discounts: [{idx: 1, min_nights: 3}, {idx: 2, min_nights: 3}]}}));
assert.throws(() => handlers.validate({doc: {seasons: [
    {idx: 1, valid_from: '2026-01-01', valid_to: '2026-09-06'},
    {idx: 2, valid_from: '2026-09-06', valid_to: '2026-12-31'}
]}}));
console.log('Các kiểm thử preview, phản hồi đảo thứ tự, escape HTML và cấu hình đều đạt.');
