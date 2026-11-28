import time,uuid,json,fcntl,httpx,os

LIVE=10800   # goal: a checkout is live for 3 hours; after that, no settle on the ledger means unpaid
_test_locks={}   # in a test, locks stay in memory so the shop's real lock file is not touched

def issued(unit):
 """Every checkout this shop ever issued for the unit: (ts, checkout id), from react.jsonl and auto_checkout.jsonl."""
 out=[]
 try:
  with open('logs/react.jsonl',encoding='utf8') as f:
   for line in f:
    if '"make_checkout"' not in line or unit not in line: continue
    row=json.loads(line)
    if row.get('action')!='make_checkout' or row.get('args',{}).get('unit')!=unit: continue
    obs=row.get('observation'); obs=json.loads(obs) if isinstance(obs,str) else obs
    res=(obs or {}).get('result') or {}
    if res.get('checkout_jwt'): out.append((int(row.get('ts',0)),(res.get('payload') or {}).get('id')))
 except FileNotFoundError: pass
 try:
  with open('auto_checkout.jsonl',encoding='utf8') as f:
   for line in f:
    a=json.loads(line)
    if a.get('unit')==unit: out.append((int(a.get('ts',0)),a.get('id')))
 except FileNotFoundError: pass
 return sorted(out)

def page(c,base,after):
 r=c.get(base+'/api/ledger',params={'after':after}); r.raise_for_status(); b=r.json(); b=b.get('entries') if isinstance(b,dict) else b
 if not isinstance(b,list): raise ValueError('ledger format')
 return b

def settles_since(base,since):
 """Settle entries on the public ledger from about `since` on. Finds the start by halving, then reads forward."""
 with httpx.Client(timeout=20) as c:
  lo,hi=0,512
  while True:
   b=page(c,base,hi)
   if not b or b[0]['ts']>=since: break
   lo,hi=hi,hi*2
  while hi-lo>500:
   mid=(lo+hi)//2; b=page(c,base,mid)
   if b and b[0]['ts']<since: lo=mid
   else: hi=mid
  after=lo; out=[]
  for _ in range(400):
   b=page(c,base,after)
   if not b: return out,after
   out+=[e for e in b if e.get('kind')=='settle']
   n=max(int(e['seq']) for e in b)
   if n<=after: raise ValueError('ledger pagination')
   after=n
 raise ValueError('ledger incomplete')

def run(args,kit):
 sku=args.get('sku'); unit=args.get('unit'); price=int(args.get('price',0)); cost=int(args.get('cost',-1)); wh=int(args.get('warranty_hours',0))
 if not sku or not unit or price<=0 or cost<0 or wh<0 or wh>72: return {'error':'invalid arguments'}
 gets=price-price//100-210
 if gets<cost and not args.get('allow_loss'): return {'error':'price below cost plus fees','shop_gets':gets}
 now=time.time()
 stock={'cert':args.get('cert'),'grade':args.get('claim')}
 if not kit.testing:
  try:
   r=httpx.get(kit.market.rstrip('/')+'/api/inventory',headers={'authorization':'Bearer '+kit.token('shop')},timeout=15); r.raise_for_status(); matches=[u for u in r.json().get('units',[]) if u.get('unit')==unit and u.get('sku')==sku]
   if len(matches)!=1: return {'error':'unit not uniquely present in inventory'}   # a settled unit leaves the stock
   stock=matches[0]
   if stock.get('cost') is None or not isinstance(stock.get('cert'),dict) or int(stock['cost'])!=cost: return {'error':'cost or certificate mismatch'}
   if args.get('cert') is not None and args['cert']!=stock['cert']: return {'error':'certificate mismatch'}
   if args.get('claim') is not None and args['claim']!=stock.get('grade'): return {'error':'grade mismatch'}
   if stock.get('expires_at') and stock['expires_at']<=now: return {'error':'expired'}
  except Exception as e: return {'error':'inventory check failed','detail':str(e)}
 lockfile=open(os.devnull) if kit.testing else open('checkout_locks.json','a+')
 with lockfile as f:
  if kit.testing: locks=_test_locks
  else:
   fcntl.flock(f,fcntl.LOCK_EX); f.seek(0)
   try: locks=json.load(f)
   except json.JSONDecodeError:
    f.seek(0)
    if f.read().strip(): return {'error':'lock file corrupt'}
    locks={}
  try: hist=args['_history'] if kit.testing and '_history' in args else ([] if kit.testing else issued(unit))
  except Exception as e: return {'error':'history unavailable','detail':str(e)}
  hist=[(int(t),i) for t,i in hist]
  if kit.testing and unit in locks and not hist: hist=[(int(locks[unit][1]),locks[unit][0])]
  voided=None
  if hist or unit in locks:
   if not hist: return {'error':'lock without issue record; read checkout_locks.json and logs before selling','checkout_id':locks.get(unit)}
   last=max(t for t,_ in hist)
   if now<last+LIVE:
    until=last+LIVE
    return {'error':'live checkout','checkout_id':locks.get(unit) or hist[-1][1],'live_until':until,'live_until_kst':time.strftime('%m-%d %H:%M',time.localtime(until))}
   try:
    if isinstance(args.get('_ledger'),list): settles=[e for e in args['_ledger'] if e.get('kind')=='settle']; seq=None
    elif kit.testing: settles=[]; seq=None
    else: settles,seq=settles_since(kit.market.rstrip('/'),min(t for t,_ in hist)-60)
   except Exception as e: return {'error':'ledger check failed','detail':str(e)}
   hit=[e for e in settles if (e.get('data') or {}).get('unit')==unit]
   if hit: return {'error':'settled on ledger','event':hit[-1]}
   voided={'unit':unit,'voided_checkout_ids':[i for _,i in hist if i],'last_issued_ts':last,'voided_at':int(now),'basis':'no settle on the public ledger for this unit 3 hours after its last checkout (goal); unit still in inventory','ledger_seq':seq}
   if not kit.testing:
    with open('checkout_withdrawals.jsonl','a',encoding='utf8') as out: out.write(json.dumps(voided,ensure_ascii=False)+'\n'); out.flush(); os.fsync(out.fileno())
  payload={'id':'co-'+uuid.uuid4().hex[:12],'shop':kit.name,'shop_url':kit.shop_url,'item':sku,'price':price,'task':args.get('task') or 't-'+uuid.uuid4().hex[:12],'currency':'credits','iat':int(now),'unit':unit,'warranty_hours':wh}
  if stock.get('cert'): payload['cert']=stock['cert']
  if stock.get('grade') in ('A','B','C'): payload['claim']=stock['grade']
  jwt=kit.sign_jwt(payload,'shop')
  if kit.testing: locks[unit]=(payload['id'],int(now))
  else: locks[unit]=payload['id']; f.seek(0); f.truncate(); json.dump(locks,f); f.flush(); os.fsync(f.fileno())
  out={'checkout_jwt':jwt,'payload':payload,'shop_gets':gets}
  if voided: out['voided']=voided
  return out
