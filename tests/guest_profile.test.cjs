const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const path = require('node:path');
let rendered = '', requests = [];
const body = {empty: () => { rendered = ''; }, text: v => { rendered = v; },
    html: v => { rendered = v; }, find: () => ({on() {}})};
const context = {frappe: {pages: {'guest-360': {}}, call: r => requests.push(r),
    utils: {escape_html: v => String(v).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;')}},
    __: s => s, format_currency: (v, c) => `${v} ${c}`};
vm.createContext(context);
const source = fs.readFileSync(path.join(__dirname, '../hospitality_core/hospitality_core/page/guest_360/guest_360.js'), 'utf8');
new Function(source);
vm.runInContext(source, context);
const wrapper = {guest_request: 0, guest_content: body};
const profile = name => ({guest: {name: 'G', full_name: name}, history: [],
    spend_by_currency: {USD: 100, VND: 2000000}, balances_by_currency: {USD: 20},
    preferences: [{preference_type: 'Note', preference_value: '<img onerror=bad()>', sharing_scope: 'Group'}]});
context.render_guest_profile(wrapper, 'A');
context.render_guest_profile(wrapper, 'B');
requests[1].callback({message: profile('<script>bad()</script>')});
assert.ok(rendered.includes('&lt;script&gt;') && !rendered.includes('<script>'));
assert.ok(rendered.includes('&lt;img') && !rendered.includes('<img'));
assert.ok(rendered.includes('100 USD') && rendered.includes('2000000 VND'));
const latest = rendered;
requests[0].callback({message: profile('Old')});
requests[0].error();
assert.equal(rendered, latest);
context.render_guest_profile(wrapper, null);
requests[1].callback({message: profile('Stale')});
assert.equal(rendered, '');
console.log('Guest 360: escape HTML, currency và phản hồi đảo thứ tự đều đạt.');
