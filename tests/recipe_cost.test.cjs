const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
let prompts = [], calls = [], messages = [];
const ctx = {
    __: x => x, format_currency: (x,c) => `${x} ${c}`,
    frappe: {ui: {form: {on() {}}}, datetime: {now_datetime: () => '2026-09-08 12:00:00'},
        utils: {escape_html: x => x.replaceAll('<','&lt;').replaceAll('>','&gt;')},
        prompt: (fields, callback) => prompts.push(callback), call: r => calls.push(r),
        msgprint: m => messages.push(m)}
};
vm.createContext(ctx);
vm.runInContext(fs.readFileSync('hospitality_core/hospitality_core/doctype/item_recipe/item_recipe.js','utf8'), ctx);
const frm = {doc: {name:'DISH'}, is_dirty: () => false};
ctx.calculate_total_cost(frm);
prompts.shift()({warehouse:'A',at:'2026-09-08 12:00:00'});
ctx.calculate_total_cost(frm);
prompts.shift()({warehouse:'B',at:'2026-09-08 12:00:00'});
assert.equal(calls[1].args.warehouse,'B');
const result = {message:{batch_cost:50000,unit_cost:25000,quantity:2,uom:'portion',warehouse:'<B>',at:'today',currency:'VND'}};
calls[1].callback(result);
calls[0].callback(result);
assert.equal(messages.length,1);
assert.ok(messages[0].message.includes('25000 VND'));
assert.ok(messages[0].message.includes('&lt;B&gt;'));
frm.is_dirty = () => true;
ctx.calculate_total_cost(frm);
assert.equal(prompts.length,0);
console.log('Giá vốn: currency, phản hồi đảo thứ tự, escape HTML và form chưa lưu đều đạt.');
