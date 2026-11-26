import httpx,collections,time

def aggregate(entries,shops):
 aliases=collections.defaultdict(set)
 for s in shops:
  if s.get('url'): aliases[s['url'].rstrip('/')].add(s['name'])
 for e in entries:
  d=e.get('data',{})
  if e.get('kind')=='join' and d.get('role')=='shop' and d.get('url') and d.get('name'): aliases[d['url'].rstrip('/')].add(d['name'])
 stats=collections.defaultdict(collections.Counter); urls=collections.defaultdict(collections.Counter); unresolved=collections.Counter()
 for e in entries:
  d=e.get('data',{}); raw=d.get('shop'); k=e.get('kind')
  if not raw: continue
  raw=str(raw).rstrip('/')
  if raw.startswith('http'):
   names=aliases.get(raw,set())
   if len(names)!=1: unresolved[raw]+=1; continue
   name=next(iter(names))
  else: name=raw
  s=stats[name]; s[k]+=1
  if k=='supply': s['supply_total']+=d.get('total',0) or 0; s['supply_qty']+=d.get('qty',0) or 0
  if k=='settle':
   urls[name][raw]+=1
   if d.get('sealed'): s['sealed']+=1
   else: s['sale_amount']+=d.get('amount',0) or 0
 return stats,urls,unresolved

def run(args,kit):
 with httpx.Client(timeout=25) as c:
  board=c.get(kit.market+'/api/board').json()['shops']; shops=c.get(kit.market+'/api/shops').json()['shops']; by={s['name']:s for s in shops}; entries=[]; after=0
  while True:
   batch=c.get(kit.market+'/api/ledger',params={'after':after}).json()
   if isinstance(batch,dict): batch=batch.get('entries',[])
   batch=[e for e in batch if e.get('seq',0)>after]
   if not batch: break
   entries.extend(batch); after=max(e['seq'] for e in batch)
  stats,urls,unresolved=aggregate(entries,shops); rows=[]
  for b in board:
   name=b['name']; shop=by.get(name,{}); row={'name':name,'rank':b.get('rank'),'stats':dict(stats[name]),'settle_urls':dict(urls[name])}
   if shop.get('pubkey'):
    row['stock_qty']=sum(shop.get('stock',{}).values()); row['address']=shop['pubkey']
    try:
     j=c.post('https://rpc-testnet.maroo.io',json={'jsonrpc':'2.0','id':1,'method':'eth_getBalance','params':[shop['pubkey'],'latest']}).json(); row['balance']=round(int(j['result'],16)/10**15,2)
    except Exception as ex: row['balance_error']=str(ex)
   rows.append(row)
  return {'timestamp':time.time(),'last_seq':after,'unresolved_url_events':dict(unresolved),'rows':[r for r in rows if (r['rank'] or 9999)<=10 or r['name']==kit.name],'highest_cash':sorted([r for r in rows if 'balance' in r],key=lambda x:-x['balance'])[:5]}
