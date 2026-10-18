// Fictional documents; only public demo assortment and rounded activity patterns.
(() => {
  'use strict';
  const money=x=>Math.round((Number(x)+Number.EPSILON)*100)/100;
  const qty=x=>Math.round((Number(x)+Number.EPSILON)*1000)/1000;
  const dayKey=d=>[d.getFullYear(),String(d.getMonth()+1).padStart(2,'0'),String(d.getDate()).padStart(2,'0')].join('-');
  function buildMonth(catalog,reference=new Date()){
    const now=new Date(reference);let random=20261018;
    const rand=()=>((random=(random*1664525+1013904223)>>>0)/4294967296);
    const pick=items=>items[Math.floor(rand()*items.length)];
    const today=new Date(now);today.setHours(0,0,0,0);
    const first=new Date(today);first.setDate(first.getDate()-29);
    const products=JSON.parse(JSON.stringify(catalog)).filter(p=>Number(p.price)>0);
    const weighted=p=>/кг|kg|літр|\bл\b/i.test(p.unit||'');
    products.forEach((p,i)=>{p.cost=money(Math.max(.01,Math.min(Number(p.cost)||p.price*.72,p.price*.9)));p.stock=weighted(p)?qty(3+rand()*6):Math.floor(12+rand()*20);p.minimumStock=5;p.minimumPrice=money(p.cost*1.03);p.demoSupplierId='s'+String(i%5+1).padStart(3,'0');});
    const customers=Array.from({length:8},(_,i)=>({id:'c'+String(i+1).padStart(3,'0'),name:'Демо-клієнт '+String(i+1).padStart(2,'0'),phone:'Демонстраційний контакт '+(i+1),debt:0}));
    const suppliers=['Продуктовий дім','Молочний кошик','Напої та бакалія','Свіжий хліб','Господарський гурт'].map((name,i)=>({id:'s'+String(i+1).padStart(3,'0'),name:'Демо · '+name,openingDebt:0,debt:0,paidAmount:0}));
    const s={version:2,datasetMeta:{seedRevision:3,label:'Вигаданий демонстраційний місяць',privacy:'Суми, документи й контрагенти вигадані. Асортимент і округлені пропорції активності магазину взяті за основу.',anchorDay:dayKey(today),from:dayKey(first),to:dayKey(today),generatedAt:now.toISOString()},products,customers,suppliers,sales:[],purchases:[],returns:[],writeoffs:[],inventories:[],cashMovements:[],cashShifts:[],supplierPayments:[],purchaseDrafts:[],debtWriteOffs:[],writeoffDraft:null,stockOpening:{at:first.toISOString(),quantities:products.map(p=>({productId:p.id,qty:p.stock}))},nextSale:9001,nextPurchase:10001,nextPurchaseSession:1001,nextReturn:1001,nextWriteoff:1001,nextInventory:1001,nextCashShift:31,nextDemoProduct:1,cashShiftInitialized:true};
    const hot=products.filter(p=>p.price>=5&&p.price<=150).slice(0,65);
    const assortment=()=>rand()<.67&&hot.length?pick(hot):pick(products);
    let saleSerial=0,purchaseSerial=0,sessionSerial=0,returnSerial=0,writeoffSerial=0,inventorySerial=0,movementSerial=0;
    const movement=(type,direction,amount,at,extra={})=>s.cashMovements.push({id:'DEMO-CM-'+(++movementSerial),type,direction,amount:money(amount),at,affectsCash:true,user:'Демо-касир',demoSeed:true,...extra});
    for(let day=0;day<30;day++){
      const at=new Date(first);at.setDate(first.getDate()+day);
      const start=at.getTime(),isToday=day===29,end=isToday?now.getTime():new Date(at.getFullYear(),at.getMonth(),at.getDate(),21).getTime(),available=Math.max(0,end-start);
      const begin=start+(available>=8*3600000?8*3600000:available*.15),saleEnd=isToday?Math.max(begin,end-1000):start+20.5*3600000;
      const iso=f=>new Date(start+Math.min(available,Math.max(0,f)*available)).toISOString();
      const purchaseAt=new Date(start+Math.min(7*3600000,begin-start)).toISOString();
      const shift={id:day+1,status:isToday?'open':'closed',openingBalance:2000,openedAt:new Date(start).toISOString(),openedByName:'Демо-касир',demoSeed:true};
      let cash=2000;
      const count=Math.max(3,Math.round((44+rand()*20)*[1,.7,.8,1.1,1.3,1,1.2][at.getDay()]*(isToday?Math.max(.12,Math.min(1,available/(20.5*3600000))):1)));
      const planned=[];
      for(let i=0;i<count;i++){
        const used=new Set(),lines=[],lineCount=rand()<.47?1:rand()<.72?2:3+Math.floor(rand()*4);
        for(let k=0;k<lineCount;k++){
          const p=assortment();if(used.has(p.id))continue;used.add(p.id);
          const quantity=weighted(p)?qty(.15+rand()*1.35):1+(rand()<.14?1:0),discountPercent=rand()<.09?5:0,price=money(p.price*(1-discountPercent/100));
          lines.push({productId:p.id,name:p.name,qty:quantity,price,retailPrice:p.price,discountPercent,unitCost:p.cost,amount:money(quantity*price)});
        }
        const total=money(lines.reduce((sum,l)=>sum+l.amount,0)),method=rand(),payment=method<.63?'cash':method<.92?'card':method<.98?'mixed':'debt';
        const cashPart=payment==='cash'?total:payment==='mixed'?money(total*(.3+rand()*.4)):0;
        planned.push({id:'DEMO-S-'+String(++saleSerial).padStart(6,'0'),at:new Date(begin+(saleEnd-begin)*(i+.25)/count).toISOString(),payment,total,itemCount:lines.length,lines,cash:cashPart,card:payment==='card'?total:payment==='mixed'?money(total-cashPart):0,customerId:payment==='debt'?pick(customers).id:null,demoSeed:true});
      }
      const needed=new Map();for(const sale of planned)for(const l of sale.lines)needed.set(l.productId,qty((needed.get(l.productId)||0)+l.qty));
      for(let i=0;i<2;i++){const p=products[(day*11+i*19)%products.length];needed.set(p.id,Math.max(needed.get(p.id)||0,qty(p.stock+2)));}
      const sessions=new Map();
      for(const [id,amount] of needed){
        const p=products.find(p=>p.id===id);if(p.stock>=amount)continue;
        if(!sessions.has(p.demoSupplierId))sessions.set(p.demoSupplierId,'DEMO-SES-'+String(++sessionSerial).padStart(6,'0'));
        const quantity=weighted(p)?qty(amount-p.stock+2):Math.ceil(amount-p.stock+8);
        p.stock=qty(p.stock+quantity);
        s.purchases.push({id:'DEMO-P-'+(++purchaseSerial),sessionId:sessions.get(p.demoSupplierId),at:purchaseAt,supplierId:p.demoSupplierId,productId:id,qty:quantity,cost:p.cost,newPrice:p.price,demoSeed:true});
      }
      for(const sale of planned){for(const l of sale.lines){const p=products.find(p=>p.id===l.productId);p.stock=qty(p.stock-l.qty);}cash=money(cash+sale.cash);if(sale.payment==='debt'){const customer=customers.find(c=>c.id===sale.customerId);customer.debt=money(customer.debt+sale.total);}s.sales.push(sale);}
      if(day%3===2){
        const sale=[...s.sales].reverse().find(r=>r.at<=iso(.97)&&(r.payment==='cash'||r.payment==='card')),l=sale?.lines[0];
        if(l){const quantity=weighted(products.find(p=>p.id===l.productId))?qty(l.qty/2):1,total=money(quantity*l.price),type=sale.payment,record={id:'DEMO-RET-'+(++returnSerial),saleId:sale.id,saleNumber:sale.id,at:iso(.97),total,customerId:null,payments:[{type,amount:total}],lines:[{productId:l.productId,name:l.name,qty:quantity,price:l.price,unitCost:l.unitCost,amount:total}],status:'local',demoSeed:true};s.returns.push(record);const p=products.find(p=>p.id===l.productId);p.stock=qty(p.stock+quantity);if(type==='cash'){cash=money(cash-total);movement('SaleReturn','out',total,record.at,{comment:'Демо-повернення '+record.id});}}
      }
      if(day%4===1){const customer=pick(customers),amount=money(customer.debt*.35);if(amount>0){customer.debt=money(customer.debt-amount);cash=money(cash+amount);movement('DebtRepayment','in',amount,iso(1),{customerId:customer.id,customerName:customer.name,comment:'Демо · часткове погашення боргу'});}}
      if(day%6===4){const p=pick(products),quantity=weighted(p)?.125:1;if(p.stock>=quantity){p.stock=qty(p.stock-quantity);s.writeoffs.push({id:'DEMO-WO-'+(++writeoffSerial),at:iso(.94),reason:'Термін придатності',comment:'Демонстраційне списання',user:'Демо-касир',lines:[{productId:p.id,qty:quantity,cost:p.cost}],totalCost:money(quantity*p.cost),demoSeed:true});}}
      if(day===9||day===20){const items=products.slice(day,day+20).map((p,i)=>{const expected=p.stock,actual=qty(Math.max(0,expected+(i===0?1:i===1?-1:0)));p.stock=actual;return {productId:p.id,expected,actual};});s.inventories.push({id:'DEMO-INV-'+(++inventorySerial),status:'posted',startedAt:iso(.985),postedAt:iso(.99),warehouseId:'1',warehouseName:'Основний склад',comment:'Демо · планова перевірка залишків',user:'Демо-касир',items,demoSeed:true});}
      for(const [supplierId,sessionId] of sessions){const total=money(s.purchases.filter(p=>p.sessionId===sessionId).reduce((sum,p)=>sum+money(p.qty*p.cost),0)),amount=money(total*(day%3===0?.55:.85));s.supplierPayments.push({id:'DEMO-SP-'+sessionId,sessionId,supplierId,amount,method:'card',at:iso(.995),demoSeed:true});}
      if(!isToday){const withdrawn=money(Math.max(0,cash-2000));if(withdrawn){cash=money(cash-withdrawn);movement('CashOut','out',withdrawn,iso(1),{comment:'Демо · інкасація після зміни'});}Object.assign(shift,{closedAt:iso(1),expectedClosingBalance:cash,actualClosingBalance:cash,difference:0,closedByName:'Демо-касир'});s.cashShifts.unshift(shift);}else s.currentCashShift=shift;
    }
    suppliers.forEach(supplier=>{const purchases=money(s.purchases.filter(p=>p.supplierId===supplier.id).reduce((sum,p)=>sum+money(p.qty*p.cost),0));supplier.paidAmount=money(s.supplierPayments.filter(p=>p.supplierId===supplier.id).reduce((sum,p)=>sum+p.amount,0));supplier.debt=money(purchases-supplier.paidAmount);});
    const draftAt=new Date(now);draftAt.setMinutes(Math.max(0,draftAt.getMinutes()-10));
    s.inventories.unshift({id:'DEMO-INV-DRAFT',status:'draft',startedAt:draftAt.toISOString(),warehouseId:'1',warehouseName:'Основний склад',comment:'Демо · продовжіть підрахунок або створіть власну інвентаризацію',user:'Демо-касир',items:products.map((p,i)=>({productId:p.id,expected:p.stock,actual:i<12?p.stock:null})),demoSeed:true});
    s.purchaseDraft={id:'SES-001000',supplierId:suppliers[0].id,lines:[]};
    s.purchaseDrafts=[{id:'DEMO-SES-DRAFT',supplierId:suppliers[1].id,lines:products.slice(0,3).map(p=>({productId:p.id,qty:weighted(p)?1.25:5,cost:p.cost,newPrice:p.price})),demoSeed:true}];
    for(const key of ['sales','purchases','returns','writeoffs','cashMovements','supplierPayments'])s[key].sort((a,b)=>b.at.localeCompare(a.at));
    return s;
  }
  window.OUTPOST_DEMO_PROFILE={meta:{privacy:'Вигадані документи, публічний демо-асортимент та округлені пропорції активності магазину.'},buildMonth};
})();
