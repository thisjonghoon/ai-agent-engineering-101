import time,uuid,json,os,fcntl

def run(args,kit):
 sku=args.get('sku'); unit=args.get('unit'); price=args.get('price'); cost=args.get('cost')
 if not sku or not unit or price is None or cost is None: return {'error':'need sku, unit, price, cost'}
 price=int(price); cost=int(cost); gets=price-price//100-210
 if gets<cost and not args.get('allow_loss'): return {'error':'price below cost plus fees','shop_gets':gets,'cost':cost}
 wh=int(args.get('warranty_hours',0))
 if wh<0 or wh>72: return {'error':'warranty_hours 0-72'}
 with open('checkout_locks.json','a+') as f:
  fcntl.flock(f,fcntl.LOCK_EX); f.seek(0)
  try: locks=json.load(f)
  except json.JSONDecodeError:
   f.seek(0)
   if f.read().strip(): return {'error':'lock file corrupt; refusing'}
   locks={}
  if unit in locks: return {'error':'unit already has issued checkout','checkout_id':locks[unit]}
  if not kit.testing:
   try:
    with open('logs/react.jsonl') as log:
     for line in log:
      if unit not in line: continue
      try: row=json.loads(line)
      except ValueError: return {'error':'unreadable matching log; refusing'}
      if row.get('action')=='make_checkout' and row.get('args',{}).get('unit')==unit:
       obs=row.get('observation',''); obs=json.loads(obs) if isinstance(obs,str) else obs
       if isinstance(obs,dict) and obs.get('ok') and 'checkout_jwt' in obs.get('result',{}): return {'error':'prior checkout in logs; refusing'}
   except OSError: return {'error':'checkout history unavailable; refusing'}
  payload={'id':'co-'+uuid.uuid4().hex[:12],'shop':kit.name,'shop_url':kit.shop_url,'item':sku,'price':price,'task':args.get('task') or 't-'+uuid.uuid4().hex[:12],'currency':'credits','iat':int(time.time()),'unit':unit,'warranty_hours':wh}
  if args.get('cert'): payload['cert']=args['cert']
  if args.get('claim') in ('A','B','C'): payload['claim']=args['claim']
  locks[unit]=payload['id']; f.seek(0); f.truncate(); json.dump(locks,f); f.flush(); os.fsync(f.fileno())
  jwt=kit.sign_jwt(payload,'shop')
  return {'checkout_jwt':jwt,'payload':payload,'shop_gets':gets}
