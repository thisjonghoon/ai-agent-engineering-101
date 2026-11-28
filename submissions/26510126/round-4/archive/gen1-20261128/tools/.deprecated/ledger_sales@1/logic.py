import httpx
from collections import defaultdict

def run(args, kit):
    url=kit.market.rstrip('/')+'/api/ledger'
    r=httpx.get(url, timeout=20)
    r.raise_for_status()
    data=r.json()
    rows=data if isinstance(data,list) else data.get('entries',data.get('ledger',data.get('items',[]))) if isinstance(data,dict) else []
    since=args.get('since'); until=args.get('until')
    totals=defaultdict(int); names={}; sales=[]
    for x in rows:
        if not isinstance(x,dict): continue
        typ=str(x.get('type',x.get('event',x.get('action','')))).lower()
        if typ and not any(k in typ for k in ('sale','sell','checkout','purchase')): continue
        t=x.get('timestamp',x.get('created_at',x.get('time')))
        if since is not None and t is not None and str(t)<str(since): continue
        if until is not None and t is not None and str(t)>str(until): continue
        sku=x.get('sku') or x.get('product_sku')
        if not sku:
            unit=x.get('unit') or x.get('unit_id')
            if isinstance(unit,dict): sku=unit.get('sku')
        if not sku: continue
        q=x.get('qty',x.get('quantity',1))
        try:q=int(q)
        except:q=1
        totals[sku]+=q
        names[sku]=x.get('name') or x.get('item') or names.get(sku)
        sales.append({'sku':sku,'qty':q,'name':names[sku],'time':t})
    return {'count':len(sales),'by_sku':[{'sku':k,'name':names.get(k),'sold_qty':v} for k,v in sorted(totals.items(),key=lambda z:-z[1])],'sales':sales[-int(args.get('max',100)):]}