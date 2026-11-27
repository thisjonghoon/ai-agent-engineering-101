import time,uuid,json,httpx

def run(args,kit):
 sku=args.get('sku'); unit=args.get('unit'); price=int(args.get('price',0)); cost=int(args.get('cost',-1))
 if not sku or not unit or price<=0 or cost<0:return {'error':'invalid arguments'}
 if price-price//100-210<cost:return {'error':'price below cost plus fees'}
 if kit.testing:
  s={'sku':sku,'unit':unit,'cost':cost,'grade':args.get('claim','A'),'cert':{'cert':{'unit':unit,'sku':sku,'grade':args.get('claim','A')}}}
 else:
  try:
   r=httpx.get(kit.market+'/api/inventory',headers={'authorization':'Bearer '+kit.token('shop')},timeout=20);r.raise_for_status()
   a=[x for x in r.json().get('units',[]) if x.get('unit')==unit and x.get('sku')==sku]
   if len(a)!=1:return {'error':'unit not uniquely present in inventory'}
   s=a[0]
   if int(s.get('cost',-1))!=cost:return {'error':'cost mismatch'}
   if args.get('cert') is not None and args['cert']!=s.get('cert'):return {'error':'certificate mismatch'}
   if args.get('claim') is not None and args['claim']!=s.get('grade'):return {'error':'grade mismatch'}
   e=s.get('expires_at')
   if e is not None and float(e)<=time.time():return {'error':'expired'}
   if not s.get('cert') or s.get('grade') not in ('A','B','C'):return {'error':'unverified inventory'}
  except Exception as e:return {'error':'inventory check failed','detail':str(e)}
 now=int(time.time()); p={'id':'co-'+uuid.uuid4().hex[:12],'shop':kit.name,'shop_url':kit.shop_url,'item':sku,'price':price,'task':args.get('task') or 't-'+uuid.uuid4().hex[:12],'currency':'credits','iat':now,'unit':unit,'warranty_hours':int(args.get('warranty_hours',0)),'cert':s['cert'],'claim':s['grade']}
 j=kit.sign_jwt(p,'shop')
 if not kit.testing:
  try: open('checkout_locks.json','w').write(json.dumps({unit:(p['id'],now)}))
  except: pass
 return {'checkout_jwt':j,'payload':p}
