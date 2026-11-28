import json, statistics, httpx

def run(args,kit):
    r=httpx.get(kit.market.rstrip('/')+'/api/ledger',params={'after':args.get('after',0),'limit':args.get('limit',500)},timeout=10)
    data=r.json()
    if isinstance(data,list): rows=data
    elif isinstance(data,dict): rows=data.get('records',data.get('deals',data.get('settles',[])))
    else: rows=[]
    groups={}
    for row in rows:
        if not isinstance(row,dict): continue
        sku=row.get('sku') or row.get('item_sku') or row.get('id')
        price=row.get('price',row.get('amount',row.get('total')))
        grade=row.get('grade',row.get('inventory_grade',''))
        try: price=int(price)
        except: continue
        if sku is not None: groups.setdefault(str(sku)+'|'+str(grade),[]).append(price)
    prices={}
    for key,vals in groups.items():
        sku,grade=key.split('|',1); prices[sku]={'price':int(statistics.median(vals)),'grade':grade,'samples':len(vals)}
    with open('prices.json','w',encoding='utf-8') as f: json.dump(prices,f,ensure_ascii=False,indent=2)
    return {'ok':True,'count':len(rows),'priced':len(prices),'prices':prices}
