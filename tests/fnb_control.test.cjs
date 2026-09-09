const assert=require('node:assert/strict');
const fs=require('node:fs');
const vm=require('node:vm');
const handlers={},calls=[],prompts=[],messages=[];
const context={__:x=>x,window:{crypto:{randomUUID:()=> 'request-test'}},
    frappe:{ui:{form:{on:(dt,h)=>handlers[dt]=h}},call:r=>calls.push(r),
        prompt:(fields,callback)=>prompts.push({fields,callback}),msgprint:m=>messages.push(m)}};
vm.createContext(context);
vm.runInContext(fs.readFileSync('hospitality_core/public/js/fnb_control.js','utf8'),context);
function form(doc) {
    return {doc,fields_dict:{},buttons:{},dirtyState:false,reloads:0,
        is_new:()=>false,is_dirty(){return this.dirtyState;},
        add_custom_button(label,fn){this.buttons[label]=fn;},reload_doc(){this.reloads++;},set_query(){},
        add_child(table,row){(this.doc[table] ||= []).push(row);},refresh_field(){},dirty(){this.dirtyState=true;}};
}
const ticket=form({name:'T1',status:'Draft',property:'P1'});
handlers['FNB Service Ticket'].refresh(ticket);
ticket.buttons['Gửi bếp'](); ticket.buttons['Gửi bếp']();
calls.shift().callback({});
assert.equal(ticket.reloads,0,'Phản hồi cũ không reload form');
calls.shift().callback({});
assert.equal(ticket.reloads,1);
ticket.dirtyState=true; ticket.buttons['Gửi bếp']();
assert.equal(calls.length,0,'Form chưa lưu không gửi lệnh');
const transfer=form({name:'MR1',docstatus:1,fnb_outlet:'O1',material_request_type:'Material Transfer'});
handlers['Material Request'].refresh(transfer);
transfer.buttons['Giao qua kho trung chuyển']();
transfer.doc={...transfer.doc,name:'MR2'};
calls.shift().callback({message:{rows:[{line:'L1',item:'Rice',uom:'kg',remaining:4}]}});
assert.equal(prompts.length,0,'Chuyển chứng từ bỏ phản hồi xem lượng giao cũ');
handlers['Material Request'].refresh(transfer);
transfer.buttons['Giao qua kho trung chuyển']();
calls.shift().callback({message:{from_warehouse:'Main',to_warehouse:'Transit',rows:[{line:'L2',item:'Rice',uom:'kg',remaining:4}]}});
prompts.shift().callback({r0:2});
const dispatch=calls.shift();
assert.equal(dispatch.type,'POST');
assert.equal(dispatch.args.name,'MR2');
assert.equal(dispatch.args.quantities.L2,2);
assert.equal(dispatch.args.request_id,'request-test');
const invoice=form({name:'SI1',docstatus:0,fnb_version:'FNB v1',items:[{name:'IL1',item_code:'Rice',idx:1}]});
handlers['Sales Invoice'].refresh(invoice);
invoice.buttons['Liên kết phiếu bếp']();
calls.shift().callback({message:[{ticket:'T1',ticket_line:'TL1',item:'Rice',remaining:3,uom:'kg'}]});
prompts.shift().callback({source:'0',target:'IL1',quantity:2});
assert.equal(invoice.doc.fnb_allocations[0].ticket_line,'TL1');
assert.equal(invoice.doc.fnb_allocations[0].stock_qty,2);
assert.equal(invoice.is_dirty(),true);
console.log('F&B UI: phản hồi đảo thứ tự, chuyển chứng từ, dirty form, nhận từng phần và phân bổ phiếu bếp đạt.');
const outlet=form({name:'OUT1',modified:'v1',enabled:1,paused:0});
handlers['FNB Outlet'].refresh(outlet);
outlet.buttons['Tạm dừng F&B']();
outlet.doc={...outlet.doc,name:'OUT2'};
prompts.shift().callback({reason:'Pause'});
assert.equal(calls.length,0,'Dialog pause cũ không gửi lệnh cho outlet đã đổi');
const count=form({name:'COUNT1',modified:'v1',status:'Counting',items:[]});
handlers['FNB Stock Count'].refresh(count);
count.buttons['Khai báo hàng tìm thấy']();
prompts.shift().callback({item:'Rice',reason:'Found'});
const found=calls.shift();
assert.equal(found.args.name,'COUNT1');
assert.equal(found.type,'POST');
