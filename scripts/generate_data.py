"""Repeatable fictional records; no customer data is used."""
import json, random
from pathlib import Path
from datetime import datetime, timezone
r=random.Random(42); root=Path(__file__).resolve().parents[1]
date=datetime.now(timezone.utc).date().isoformat(); stamp=date+'T06:00:00+00:00'
products=[{'product_id':f'product-{i:02d}','title':f'Studio cotton tote {i:02d}',
    'description':'A cotton tote with two handles and an internal pocket.',
    'attributes':['Cotton','Two handles','Internal pocket'],'verified_faqs':['Material: cotton.','Care: hand wash.']} for i in range(20)]
customers=[{'customer_id':f'customer-{i:03d}','email':f'customer{i}@example.test','orders':r.randint(1,8),
    'total_spend':float(r.randint(20,900)),'currency':'USD','days_since_order':r.randint(1,220)} for i in range(50)]
orders=[{'id':f'order-{i:03d}','customer_id':customers[i%50]['customer_id'],'date':date,
    'total':float(r.randint(20,180)),'refunds':float(10 if i%17==0 else 0),'currency':'USD'} for i in range(100)]
carts=[{'customer_id':customers[i]['customer_id'],'cart_id':f'cart-{i:03d}','email':customers[i]['email'],
    'consent':i%5!=4,'items':[{'sku':f'SKU-{i%20:02d}','title':products[i%20]['title'],'quantity':1,'price':80.0}],
    'value':80.0,'currency':'USD','recent_purchase':i%9==8} for i in range(30)]
texts=[(1,'The item arrived broken. Please help.'),(2,'The delivery was late.'),(5,'Great item and helpful support.'),(3,'The size is as described.')]
reviews=[{'product_id':products[i%20]['product_id'],'rating':texts[i%4][0],'text':texts[i%4][1]} for i in range(40)]
(root/'data/dataset.json').write_text(json.dumps(dict(products=products,customers=customers,orders=orders,carts=carts,reviews=reviews),indent=2))
examples=[('cart.abandoned',carts[0]),('cart.abandoned',{**carts[1],'consent':False}),
    ('inventory.updated',dict(sku='SKU-03',available=8,daily_units=4.0,lead_days=7)),
    ('review.created',reviews[0]),('product.created',products[0]),('customer.updated',customers[0]),('brief.requested',{'date':date})]
events=[{'event_id':f'sample-{i:02d}','type':k,'timestamp':stamp,'source':'synthetic','payload':p} for i,(k,p) in enumerate(examples)]
(root/'data/events.json').write_text(json.dumps(events,indent=2))
print('Generated 20 products, 50 customers, 100 orders, 30 carts and 40 reviews; all fictional.')
