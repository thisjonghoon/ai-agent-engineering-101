import time,uuid,json,os,fcntl,httpx

def run(args,kit):
 sku=args.get('sku'); unit=args.get('unit'); price=args.get('price'); cost=args.get('cost')
 if not sku or not unit or price is None or cost is None: return {'error':'need sku, unit, price, cost'}
 price=int(price); cost=int(cost)
 if price<=0 or cost<0: return {'error':'invalid price or cost'}
 if not kit.testing:
  try:
   r=httpx.get(kit.market.rstrip('/')+'/api/inventory',headers={'authorization':'Bearer '+kit.token('shop')},timeout=15); r.raise_for_status(); inv=r.json()
   matches=[u for u in inv.get('units',[]) if u.get('unit')==unit and u.get('sku')==sku]
   if len(matches)!=1: return {'error':'unit not uniquely present in inventory'}
   stock=matches[0]
   if stock.get('cost') is None or not isinstance(stock.get('cert'),dict): return {'error':'inventory cost or certificate unavailable'}
   if cost!=int(stock['cost']): return {'error':'cost does not match inventory','actual_cost':stock['cost']}
   if args.get('cert') is not None and args['cert']!=stock['cert']: return {'error':'certificate differs from inventory'}
   if args.get('claim') is not None and args['claim']!=stock.get('grade'): return {'error':'claim differs from current grade','actual_grade':stock.get('grade')}
  except Exception as e: return {'error':'inventory check failed','detail':str(e)}
 else: stock={'cost':cost,'cert':args.get('cert'), 'grade':args.get('claim')}
 gets=price-price//100-210
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
  if stock.get('cert'): payload['cert']=stock['cert']
  if stock.get('grade') in ('A','B','C'): payload['claim']=stock['grade']
  locks[unit]=payload['id']; f.seek(0); f.truncate(); json.dump(locks,f); f.flush(); os.fsync(f.fileno())
  return {'checkout_jwt':kit.sign_jwt(payload,'shop'),'payload':payload,'shop_gets':gets}
