import time,uuid,json,fcntl,os,httpx
LIVE=10800
_test={}
def hist(unit):
 out=[]
 for fn in ('logs/react.jsonl','auto_checkout.jsonl'):
  try:
   for line in open(fn,encoding='utf8'):
    try:
     r=json.loads(line)
     if fn.endswith('react.jsonl'):
      if r.get('action')!='make_checkout' or r.get('args',{}).get('unit')!=unit: continue
      o=r.get('observation',{}); o=json.loads(o) if isinstance(o,str) else o
      z=o.get('result',{})
      if z.get('checkout_jwt'): out.append((int(r.get('ts',0)),(z.get('payload') or {}).get('id')))
     elif r.get('unit')==unit: out.append((int(r.get('ts',0)),r.get('id')))
    except: pass
  except FileNotFoundError: pass
 return sorted(out)
def run(args,kit):
 sku=args.get('sku'); unit=args.get('unit'); price=int(args.get('price',0)); cost=int(args.get('cost',-1)); now=int(time.time())
 if not sku or not unit or price<=0 or cost<0: return {'error':'invalid arguments'}
 if price-price//100-210<cost and not args.get('allow_loss'): return {'error':'price below cost plus fees','shop_gets':price-price//100-210}
 stock={'cert':args.get('cert'),'grade':args.get('claim')}
 if not kit.testing:
  try:
   r=httpx.get(kit.market+'/api/inventory',headers={'authorization':'Bearer '+kit.token('shop')},timeout=20); r.raise_for_status()
   m=[x for x in r.json().get('units',[]) if x.get('unit')==unit and x.get('sku')==sku]
   if len(m)!=1: return {'error':'unit not uniquely present in inventory'}
   stock=m[0]
   if int(stock.get('cost',-1))!=cost: return {'error':'cost mismatch'}
   if args.get('cert') is not None and args['cert']!=stock.get('cert'): return {'error':'certificate mismatch'}
   if args.get('claim') is not None and args['claim']!=stock.get('grade'): return {'error':'grade mismatch'}
   if stock.get('expires_at',0)<=time.time(): return {'error':'expired'}
  except Exception as e: return {'error':'inventory check failed','detail':str(e)}
 lockpath=None if kit.testing else 'checkout_locks.json'
 locks=_test if kit.testing else {}
 if not kit.testing:
  with open(lockpath,'a+') as f:
   fcntl.flock(f,fcntl.LOCK_EX); f.seek(0)
   try: locks=json.load(f)
   except: locks={}
 prior=hist(unit) if not kit.testing else ([] if unit not in locks else [(locks[unit][1],locks[unit][0])])
 if prior or unit in locks:
  last=max(x[0] for x in prior) if prior else int(locks[unit][1])
  if now<last+LIVE: return {'error':'live checkout','checkout_id':locks.get(unit) or prior[-1][1],'live_until':last+LIVE}
  settled=False
  if isinstance(args.get('_ledger'),list): settled=any(e.get('kind')=='settle' and unit in json.dumps(e) for e in args['_ledger'])
  elif not kit.testing:
   try:
    for p in range(1,80):
     d=httpx.get(kit.market+'/api/ledger',params={'page':p,'limit':1000},timeout=20).json(); es=d if isinstance(d,list) else d.get('entries',[])
     if not es: break
     if any(e.get('kind')=='settle' and unit in json.dumps(e) for e in es): settled=True; break
     if len(es)<1000: break
   except Exception as e: return {'error':'ledger check failed','detail':str(e)}
  if settled: return {'error':'settled on ledger'}
  v={'unit':unit,'voided_checkout_ids':[x[1] for x in prior if x[1]],'last_issued_ts':last,'voided_at':now,'basis':'no settle on public ledger after 3 hours'}
  if not kit.testing:
   with open('checkout_withdrawals.jsonl','a',encoding='utf8') as f: f.write(json.dumps(v,ensure_ascii=False)+'\n')
 payload={'id':'co-'+uuid.uuid4().hex[:12],'shop':kit.name,'shop_url':kit.shop_url,'item':sku,'price':price,'task':args.get('task') or 't-'+uuid.uuid4().hex[:12],'currency':'credits','iat':now,'unit':unit,'warranty_hours':int(args.get('warranty_hours',0))}
 if stock.get('cert'): payload['cert']=stock['cert']
 if stock.get('grade') in ('A','B','C'): payload['claim']=stock['grade']
 jwt=kit.sign_jwt(payload,'shop')
 if kit.testing: locks[unit]=(payload['id'],now)
 else:
  with open('checkout_locks.json','w',encoding='utf8') as f: json.dump({**locks,unit:(payload['id'],now)},f)
 return {'checkout_jwt':jwt,'payload':payload,'voided':bool(prior)}
