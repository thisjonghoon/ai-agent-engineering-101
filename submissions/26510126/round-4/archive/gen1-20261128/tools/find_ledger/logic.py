import httpx

def run(args,kit):
 terms=[str(args[k]).strip() for k in ('query','tx_hash','checkout_id','unit','sku') if args.get(k) and str(args[k]).strip()]
 if not terms: raise ValueError('검색어가 필요합니다')
 hits=[]; after=0; scanned=0
 with httpx.Client(timeout=20) as c:
  for page in range(10000):
   r=c.get(kit.market.rstrip('/')+'/api/ledger',params={'after':after}); r.raise_for_status(); batch=r.json()
   if isinstance(batch,dict): batch=batch.get('entries')
   if not isinstance(batch,list): raise ValueError('unexpected ledger response')
   if not batch: break
   fresh=[x for x in batch if isinstance(x,dict) and int(x.get('seq',0))>after]
   if not fresh: raise ValueError('ledger pagination did not advance')
   for e in fresh:
    scanned+=1
    if any(t.lower() in str(e).lower() for t in terms): hits.append(e)
   after=max(int(x['seq']) for x in fresh)
  else: raise ValueError('page limit reached')
 return {'count':len(hits),'matches':hits,'last_seq':after,'scanned':scanned,'complete':True}
