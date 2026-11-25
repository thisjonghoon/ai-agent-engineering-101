import httpx
from collections import defaultdict

def run(args, kit):
    r=httpx.get(kit.market.rstrip('/')+'/api/ledger',timeout=20); r.raise_for_status()
    raw=r.json(); rows=raw if isinstance(raw,list) else raw.get('entries',[]) if isinstance(raw,dict) else []
    totals=defaultdict(int); names={}; sales=[]
    for x in rows:
        if not isinstance(x,dict): continue
        kind=str(x.get('kind','')).lower(); d=x.get('data',{})
        if not isinstance(d,dict): d={}
        text=' '.join(str(d.get(k,'')) for k in ('kind','type','event','action','status')).lower()
        if not (any(k in kind for k in ('sale','sell')) or any(k in text for k in ('sale','sell','checkout','purchase'))): continue
        t=x.get('ts',x.get('timestamp',x.get('created_at')))
        if args.get('since') is not None and t is not None and float(t)<float(args['since']): continue
        if args.get('until') is not None and t is not None and float(t)>float(args['until']): continue
        sku=d.get('sku') or x.get('sku'); unit=d.get('unit') or d.get('unit_id') or x.get('unit')
        if isinstance(unit,dict): sku=sku or unit.get('sku')
        if not sku: continue
        q=d.get('qty',d.get('quantity',x.get('qty',1)))
        try:q=int(q)
        except:q=1
        totals[sku]+=q; names[sku]=d.get('name') or d.get('item') or names.get(sku)
        sales.append({'seq':x.get('seq'),'sku':sku,'qty':q,'unit':unit,'name':names[sku],'ts':t})
    return {'count':len(sales),'by_sku':[{'sku':k,'name':names.get(k),'sold_qty':v} for k,v in sorted(totals.items(),key=lambda z:-z[1])],'sales':sales[-int(args.get('max',100)):]}