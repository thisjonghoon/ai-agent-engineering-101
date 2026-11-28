import json, statistics, httpx

def run(args,kit):
 r=httpx.get(kit.market.rstrip('/')+'/api/ledger',params={'after':args.get('after',0),'limit':args.get('limit',500)},timeout=10); data=r.json()
 if isinstance(data,list): rows=data
 elif isinstance(data,dict): rows=data.get('records',data.get('deals',data.get('settles',data.get('ledger',[]))))
 else: rows=[]
 groups={}
 def walk(x):
  if isinstance(x,dict):
   sku=x.get('sku') or x.get('item_sku') or x.get('item')
   price=x.get('price',x.get('unit_price',x.get('sale_price',x.get('amount'))))
   grade=x.get('grade',x.get('inventory_grade',''))
   try:
    if sku is not None and price is not None: groups.setdefault(str(sku)+'|'+str(grade),[]).append(int(price))
   except: pass
   for v in x.values():
    if isinstance(v,(dict,list)): walk(v)
  elif isinstance(x,list):
   for v in x: walk(v)
 walk(rows); prices={}
 for k,v in groups.items():
  sku,g=k.split('|',1); prices[sku]={'price':int(statistics.median(v)),'grade':g,'samples':len(v)}
 with open('prices.json','w',encoding='utf-8') as f: json.dump(prices,f,ensure_ascii=False,indent=2)
 sample=rows[:2] if isinstance(rows,list) else []
 return {'ok':True,'count':len(rows),'priced':len(prices),'prices':prices,'sample':sample}
