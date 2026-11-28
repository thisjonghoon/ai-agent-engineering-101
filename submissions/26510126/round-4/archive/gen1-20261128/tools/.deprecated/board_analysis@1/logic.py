import httpx, collections, time

def run(args,kit):
 if kit.testing: return {'test':True}
 with httpx.Client(timeout=25) as c:
  board=c.get(kit.market+'/api/board').json()['shops']; shops=c.get(kit.market+'/api/shops').json()['shops']; by={s['name']:s for s in shops}; stats=collections.defaultdict(lambda:collections.Counter()); after=0; kinds=collections.Counter()
  while True:
   batch=c.get(kit.market+'/api/ledger',params={'after':after}).json()
   if isinstance(batch,dict): batch=batch.get('entries',[])
   batch=[x for x in batch if x.get('seq',0)>after]
   if not batch: break
   for e in batch:
    d=e.get('data',{}); name=d.get('shop'); k=e.get('kind'); kinds[k]+=1
    if name:
     s=stats[name]; s[k]+=1
     if k=='supply': s['supply_total']+=d.get('total',0); s['supply_qty']+=d.get('qty',0)
     if k=='settle':
      if d.get('sealed'): s['sealed']+=1
      else: s['sale_amount']+=d.get('amount',0) or 0
   after=max(e['seq'] for e in batch)
  results=[]
  for b in board:
   name=b['name']; shop=by.get(name); row={'name':name,'rank':b.get('rank'),'stats':dict(stats[name])}
   if shop and shop.get('pubkey'):
    row['stock_qty']=sum(shop.get('stock',{}).values()); row['address']=shop['pubkey']
    try:
     j=c.post('https://rpc-testnet.maroo.io',json={'jsonrpc':'2.0','id':1,'method':'eth_getBalance','params':[shop['pubkey'],'latest']}).json(); row['balance']=round(int(j['result'],16)/10**15,2)
    except Exception as e: row['balance_error']=str(e)
   results.append(row)
  return {'timestamp':time.time(),'last_seq':after,'kinds':dict(kinds),'rows':results}
