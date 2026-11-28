import httpx
from collections import defaultdict

def run(args,kit):
 rows=[]; after=0
 with httpx.Client(timeout=20) as c:
  for page in range(10000):
   r=c.get(kit.market.rstrip('/')+'/api/ledger',params={'after':after}); r.raise_for_status(); batch=r.json()
   if isinstance(batch,dict): batch=batch.get('entries',[])
   if not isinstance(batch,list): raise ValueError('unexpected ledger response')
   batch=[x for x in batch if isinstance(x,dict) and int(x.get('seq',0))>after]
   if not batch: break
   rows.extend(batch); new=max(int(x['seq']) for x in batch)
   if new<=after: raise ValueError('ledger did not advance')
   after=new
  else: raise ValueError('page limit reached')
 totals=defaultdict(int); names={}; out=[]; sealed=0
 for x in rows:
  if str(x.get('kind','')).lower()!='settle': continue
  t=x.get('ts')
  if args.get('since') is not None and float(t)<float(args['since']): continue
  if args.get('until') is not None and float(t)>float(args['until']): continue
  d=x.get('data',{}); sku=d.get('sku')
  if not sku:
   if d.get('sealed'): sealed+=1
   continue
  try:q=int(d.get('qty',1))
  except:q=1
  totals[sku]+=q; names[sku]=d.get('name',names.get(sku)); out.append({'seq':x.get('seq'),'ts':t,'sku':sku,'qty':q,'name':d.get('name'),'unit':d.get('unit'),'shop':d.get('shop'),'amount':d.get('amount')})
 return {'count':len(out),'sealed_count':sealed,'last_seq':after,'entries_scanned':len(rows),'by_sku':[{'sku':k,'name':names.get(k),'sold_qty':v} for k,v in sorted(totals.items(),key=lambda z:-z[1])],'sales':out[-int(args.get('max',100)):]}