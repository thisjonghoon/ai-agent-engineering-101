import httpx
from collections import defaultdict

def run(args,kit):
 r=httpx.get(kit.market.rstrip('/')+'/api/ledger',timeout=20); r.raise_for_status(); rows=r.json()
 if not isinstance(rows,list): rows=rows.get('entries',[]) if isinstance(rows,dict) else []
 totals=defaultdict(int); names={}; out=[]
 for x in rows:
  if not isinstance(x,dict) or str(x.get('kind','')).lower()!='settle': continue
  t=x.get('ts');
  if args.get('since') is not None and float(t)<float(args['since']): continue
  if args.get('until') is not None and float(t)>float(args['until']): continue
  d=x.get('data',{}); sku=d.get('sku');
  if not sku: continue
  q=d.get('qty',1)
  try:q=int(q)
  except:q=1
  totals[sku]+=q; names[sku]=d.get('name',names.get(sku)); out.append({'seq':x.get('seq'),'ts':t,'sku':sku,'qty':q,'name':d.get('name'),'unit':d.get('unit'),'shop':d.get('shop'),'amount':d.get('amount')})
 return {'count':len(out),'by_sku':[{'sku':k,'name':names.get(k),'sold_qty':v} for k,v in sorted(totals.items(),key=lambda z:-z[1])],'sales':out[-int(args.get('max',100)):]}