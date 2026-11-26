import time,uuid,json,fcntl,httpx,hashlib,concurrent.futures,os

def covered(rows,unit,targets,lo):
 ranges=[]
 for row in rows:
  if row.get('action')!='checkout_payments': continue
  try:
   ob=row['observation']; ob=json.loads(ob) if isinstance(ob,str) else ob
   if not ob.get('ok'): continue
   r=ob['result']; hs=set(r['hashes'][unit])
   if not targets.issubset(hs) or r['errors'] or r['matches']: continue
   a=int(r['start_block']); b=int(r['end_block'])
   if a<=b and b<=int(r['latest']): ranges.append((a,b))
  except (KeyError,TypeError,ValueError): continue
 end=lo-1
 for a,b in sorted(ranges):
  if a>end+1: break
  end=max(end,b)
 return end

def run(args,kit):
 sku=args.get('sku'); unit=args.get('unit'); price=int(args.get('price',0)); cost=int(args.get('cost',-1)); wh=int(args.get('warranty_hours',0))
 if not sku or not unit or price<=0 or cost<0 or wh<0 or wh>72: return {'error':'invalid arguments'}
 gets=price-price//100-210
 if gets<cost and not args.get('allow_loss'): return {'error':'price below cost plus fees','shop_gets':gets}
 stock={'cert':args.get('cert'),'grade':args.get('claim')}
 if not kit.testing:
  try:
   r=httpx.get(kit.market.rstrip('/')+'/api/inventory',headers={'authorization':'Bearer '+kit.token('shop')},timeout=15); r.raise_for_status(); matches=[u for u in r.json().get('units',[]) if u.get('unit')==unit and u.get('sku')==sku]
   if len(matches)!=1: return {'error':'unit not uniquely present in inventory'}
   stock=matches[0]
   if stock.get('cost') is None or not isinstance(stock.get('cert'),dict) or int(stock['cost'])!=cost: return {'error':'cost or certificate mismatch'}
   if args.get('cert') is not None and args['cert']!=stock['cert']: return {'error':'certificate mismatch'}
   if args.get('claim') is not None and args['claim']!=stock.get('grade'): return {'error':'grade mismatch'}
   if stock.get('expires_at') and stock['expires_at']<=time.time(): return {'error':'expired'}
  except Exception as e: return {'error':'inventory check failed','detail':str(e)}
 with open('checkout_locks.json','a+') as f:
  fcntl.flock(f,fcntl.LOCK_EX); f.seek(0)
  try: locks=json.load(f)
  except json.JSONDecodeError:
   f.seek(0)
   if f.read().strip(): return {'error':'lock file corrupt'}
   locks={}
  prior=[]; rows=[]
  if not kit.testing:
   try:
    with open('logs/react.jsonl',encoding='utf8') as log:
     for line in log:
      row=json.loads(line); rows.append(row)
      if row.get('action')!='make_checkout' or row.get('args',{}).get('unit')!=unit: continue
      obs=row.get('observation',''); obs=json.loads(obs) if isinstance(obs,str) else obs
      res=obs.get('result',{}) if isinstance(obs,dict) else {}
      if obs.get('ok') and res.get('checkout_jwt'): prior.append({'jwt':res['checkout_jwt'],'payload':res['payload']})
   except Exception as e: return {'error':'history unavailable','detail':str(e)}
  if unit in locks or prior:
   if kit.testing or not args.get('withdrawal_post'): return {'error':'unit already has issued checkout','checkout_id':locks.get(unit)}
   if not prior or locks.get(unit)!=prior[-1]['payload']['id']: return {'error':'lock/history mismatch'}
   try:
    pid=int(args['withdrawal_post']); c=httpx.Client(timeout=20)
    r=c.get(kit.market.rstrip('/')+'/api/forum',params={'since':pid-1,'limit':1}); r.raise_for_status(); posts=r.json(); p=posts[0] if posts else {}
    text=p.get('text',''); last=prior[-1]['payload']; now=time.time()
    if p.get('id')!=pid or p.get('author')!=kit.name or p.get('role')!='shop' or unit not in text or last['id'] not in text or '철회' not in text: return {'error':'withdrawal notice not verified'}
    if p['ts']<last['iat']+10800 or now<p['ts']+1800: return {'error':'withdrawal timing incomplete'}
    after=0
    for page in range(10000):
     r=c.get(kit.market.rstrip('/')+'/api/ledger',params={'after':after}); r.raise_for_status(); batch=r.json(); batch=batch.get('entries') if isinstance(batch,dict) else batch
     if not isinstance(batch,list): raise ValueError('ledger format')
     if not batch: break
     fresh=[x for x in batch if int(x.get('seq',0))>after]
     if not fresh: raise ValueError('ledger pagination')
     for e in fresh:
      if e.get('kind')!='supply' and (unit in json.dumps(e,ensure_ascii=False) or any(x['payload']['id'] in json.dumps(e) for x in prior)): return {'error':'ledger event requires review','event':e}
     after=max(int(x['seq']) for x in fresh)
    else: raise ValueError('ledger incomplete')
    def rpc(method,params):
     q=c.post('https://rpc-testnet.maroo.io',json={'jsonrpc':'2.0','id':1,'method':method,'params':params}); q.raise_for_status(); j=q.json()
     if 'error' in j: raise ValueError(str(j['error']))
     return j['result']
    latest=int(rpc('eth_blockNumber',[]),16); start=min(x['payload']['iat'] for x in prior)-60
    lo=0; hi=latest
    while lo<hi:
     mid=(lo+hi)//2; b=rpc('eth_getBlockByNumber',[hex(mid),False])
     if int(b['timestamp'],16)<start: lo=mid+1
     else: hi=mid
    targets={'0x'+hashlib.sha256(x['jwt'].encode()).hexdigest() for x in prior}; address=kit.address('shop').lower()
    end=covered(rows,unit,targets,lo); scanfrom=max(lo,end+1)
    if latest-scanfrom>10000: return {'error':'chain verification requires additional chunks','start_block':scanfrom,'latest':latest}
    def scan(n):
     b=rpc('eth_getBlockByNumber',[hex(n),True])
     if not isinstance(b,dict) or not isinstance(b.get('transactions'),list): raise ValueError('missing block')
     return [t['hash'] for t in b['transactions'] if isinstance(t,dict) and (t.get('to') or '').lower()==address and t.get('input','').lower() in targets]
    with concurrent.futures.ThreadPoolExecutor(max_workers=24) as ex:
     for hit in ex.map(scan,range(scanfrom,latest+1)):
      if hit: return {'error':'chain payment requires review','transactions':hit}
    if stock.get('expires_at') and stock['expires_at']<=time.time(): return {'error':'expired during verification'}
    record={'unit':unit,'checkout_ids':[x['payload']['id'] for x in prior],'withdrawal_post':pid,'withdrawal_ts':p['ts'],'verified_at':int(time.time()),'ledger_seq':after,'chain_from':lo,'chain_to':latest,'reused_through':end,'jwt_hashes':list(targets)}
    with open('checkout_withdrawals.jsonl','a',encoding='utf8') as out: out.write(json.dumps(record,ensure_ascii=False)+'\n'); out.flush(); os.fsync(out.fileno())
   except Exception as e: return {'error':'withdrawal verification failed','detail':str(e)}
  payload={'id':'co-'+uuid.uuid4().hex[:12],'shop':kit.name,'shop_url':kit.shop_url,'item':sku,'price':price,'task':args.get('task') or 't-'+uuid.uuid4().hex[:12],'currency':'credits','iat':int(time.time()),'unit':unit,'warranty_hours':wh}
  if stock.get('cert'): payload['cert']=stock['cert']
  if stock.get('grade') in ('A','B','C'): payload['claim']=stock['grade']
  locks[unit]=payload['id']; f.seek(0); f.truncate(); json.dump(locks,f); f.flush(); os.fsync(f.fileno())
  return {'checkout_jwt':kit.sign_jwt(payload,'shop'),'payload':payload,'shop_gets':gets}
