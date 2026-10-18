import fs from 'node:fs';import vm from 'node:vm';import assert from 'node:assert/strict';
const root=new URL('../site/assets/',import.meta.url),sandbox={window:{},Date,console};vm.createContext(sandbox);
for(const name of ['demo-products-v2-1.js','demo-products-v2-2.js','demo-products-v2-3.js','demo-products-v2-4.js','demo-profile-v2.js'])vm.runInContext(fs.readFileSync(new URL(name,root),'utf8'),sandbox,{filename:name});
const close=(a,b,epsilon=.004)=>assert.ok(Math.abs(a-b)<epsilon,`${a} != ${b}`),r=x=>Math.round((x+Number.EPSILON)*100)/100;
for(const reference of ['2026-10-18T13:00:00Z','2026-11-01T00:00:05Z','2027-01-01T00:00:00Z']){
 const now=new Date(reference),s=sandbox.window.OUTPOST_DEMO_PROFILE.buildMonth(sandbox.window.OUTPOST_DEMO_PRODUCTS,now);
 assert.equal(JSON.stringify(s),JSON.stringify(sandbox.window.OUTPOST_DEMO_PROFILE.buildMonth(sandbox.window.OUTPOST_DEMO_PRODUCTS,now)));
 assert.ok(s.sales.length>1000&&s.sales.length<2500);assert.ok(Buffer.byteLength(JSON.stringify(s))<2*1024*1024);
 assert.equal(new Set(s.sales.map(x=>new Date(x.at).toDateString())).size,30);
 const balance=new Map(s.stockOpening.quantities.map(x=>[x.productId,x.qty])),events=[];
 for(const sale of s.sales){close(sale.total,sale.lines.reduce((n,l)=>n+l.amount,0));close(sale.total,sale.cash+sale.card+(sale.payment==='debt'?sale.total:0));assert.ok(sale.lines.length);for(const l of sale.lines){close(l.amount,r(l.qty*l.price));assert.ok(l.unitCost>0);events.push({at:sale.at,id:l.productId,qty:-l.qty,rank:2});}}
 for(const p of s.purchases)events.push({at:p.at,id:p.productId,qty:p.qty,rank:1});
 for(const doc of s.returns){const sale=s.sales.find(x=>x.id===doc.saleId);assert.ok(sale&&doc.at>=sale.at);close(doc.total,doc.payments.reduce((n,p)=>n+p.amount,0));for(const l of doc.lines){assert.ok(l.qty<=sale.lines.find(x=>x.productId===l.productId).qty);events.push({at:doc.at,id:l.productId,qty:l.qty,rank:3});}}
 for(const doc of s.writeoffs){close(doc.totalCost,r(doc.lines.reduce((n,l)=>n+l.qty*l.cost,0)));for(const l of doc.lines)events.push({at:doc.at,id:l.productId,qty:-l.qty,rank:4});}
 for(const doc of s.inventories.filter(x=>x.status==='posted'))for(const l of doc.items)events.push({at:doc.postedAt,id:l.productId,qty:l.actual-l.expected,expected:l.expected,rank:5});
 events.sort((a,b)=>a.at.localeCompare(b.at)||a.rank-b.rank);
 for(const e of events){assert.ok(+new Date(e.at)<=+now,'future event');if(e.expected!=null)close(balance.get(e.id),e.expected);balance.set(e.id,Math.round((balance.get(e.id)+e.qty)*1000)/1000);assert.ok(balance.get(e.id)>=-.0001,'negative generated stock');}
 for(const p of s.products)close(p.stock,balance.get(p.id));
 for(const c of s.customers)close(c.debt,r(s.sales.filter(x=>x.payment==='debt'&&x.customerId===c.id).reduce((n,x)=>n+x.total,0)-s.cashMovements.filter(x=>x.type==='DebtRepayment'&&x.customerId===c.id).reduce((n,x)=>n+x.amount,0)));
 for(const supplier of s.suppliers)close(supplier.debt,r(s.purchases.filter(x=>x.supplierId===supplier.id).reduce((n,x)=>n+r(x.qty*x.cost),0)-s.supplierPayments.filter(x=>x.supplierId===supplier.id).reduce((n,x)=>n+x.amount,0)));
 for(const shift of [...s.cashShifts,s.currentCashShift]){const inside=x=>x.at>=shift.openedAt&&+new Date(x.at)<=+(shift.closedAt?new Date(shift.closedAt):now);const cash=shift.openingBalance+s.sales.filter(inside).reduce((n,x)=>n+x.cash,0)+s.cashMovements.filter(inside).reduce((n,x)=>n+(x.direction==='in'?x.amount:-x.amount),0);assert.ok(cash>=0);if(shift.status==='closed')close(cash,shift.expectedClosingBalance);}
 assert.equal(s.cashShifts.length,29);assert.ok(s.returns.length>=9&&s.writeoffs.length>=4&&s.purchaseDrafts.length&&s.inventories.some(x=>x.status==='draft'));
 assert.ok(s.customers.every(c=>!/[+][0-9]/.test(c.phone)));
 console.log('Fictional month invariants: PASS',reference,s.sales.length,'receipts',Buffer.byteLength(JSON.stringify(s)),'bytes');
}
