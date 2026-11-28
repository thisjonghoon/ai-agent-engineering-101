import json,time,re,httpx

def load(p,d):
 try:
  with open(p,encoding='utf-8') as f:return json.load(f)
 except:return d

def flat(x):
 if isinstance(x,list):
  z=[]
  for v in x:z+=flat(v)
  return z
 if isinstance(x,dict):
  for k in ('items','inventory','units','data','results','stock','records','products'):
   if k in x:
    z=flat(x[k])
    if z:return z
  if any(k in x for k in ('sku','sku_id','unit_id','unitId','id','code','product_id','productId','_key')):return [x]
  z=[]
  for k,v in x.items():
   if isinstance(v,dict):
    q=dict(v);q.setdefault('_key',k);z+=flat(q)
  return z
 return []

def val(x,ks):
 for k in ks:
  if isinstance(x,dict) and x.get(k) is not None:return x[k]

def sid(x):return str(val(x,['sku','sku_id','product_id','productId','code','_key','id']) or '')
def norm(x):return re.sub(r'[^0-9a-z가-힣]','',str(x or '').lower())
def run(args,kit):
 test=kit.testing; card=load('test_card.json' if test else 'card.json',{}); cat=flat(load('test_catalog.json' if test else 'catalog.json',[])); stock=card.get('stock',card.get('inventory',{})) or {}
 if isinstance(stock,list):stock={sid(x):1 for x in stock}
 cm={sid(x):x for x in cat if sid(x)}; inv={}
 if not test:
  try:
   r=httpx.get(kit.market+'/api/inventory',headers={'authorization':'Bearer '+kit.token('shop')},timeout=8)
   if r.status_code<300:inv={sid(x):x for x in flat(r.json()) if sid(x)}
  except:pass
 rows=[]
 for sku,n in stock.items():
  if int(n or 0)<=0:continue
  c=cm.get(str(sku),{}); i=inv.get(str(sku),{})
  if not c and not i:continue
  rows.append({'sku':str(sku),'name':val(c,['name','title','product_name','item']) or val(i,['name','title','product_name','item']),'aliases':val(c,['aliases','alias']) or [],'grade':val(i,['grade']) or val(c,['grade']),'unit':val(i,['unit','unit_id','unitId']) or val(c,['unit','unit_id','unitId']) or str(sku),'cost':val(c,['cost','unit_cost','원가','price']) or val(i,['cost','unit_cost','price']),'cert':val(i,['certificate_grade','certificate']) or val(c,['certificate_grade','certificate']),'expiry':val(i,['expires_at','expiry']) or val(c,['expires_at','expiry'])})
 q=norm(args.get('text','')); chosen=None
 for e in rows:
  terms=[e['sku'],e['name'],e['unit']]+(e['aliases'] if isinstance(e['aliases'],list) else [])
  if any(norm(t) and norm(t) in q for t in terms):chosen=e;break
 if not chosen:return {'reply':'요청하신 품목은 현재 재고가 없습니다. 결제서와 예약을 만들지 않았습니다.','state':'completed'}
 try:p=int((float(chosen['cost'])+210)/.99)+1
 except:return {'reply':'원가를 확인하지 못해 결제서와 예약을 만들지 않았습니다.','state':'completed'}
 lp='test_checkout_locks.json' if test else 'checkout_locks.json'; locks=load(lp,{})
 if not isinstance(locks,dict):locks={}
 now=int(time.time()); old=locks.get(chosen['sku'])
 if isinstance(old,dict) and now-int(old.get('time',0))<10800:return {'reply':'해당 상품은 잠시 예약 중입니다.','state':'completed'}
 payload={'id':chosen['sku']+'-'+str(now),'shop':'thisjonghoon','shop_url':kit.shop_url,'item':chosen['name'],'unit':chosen['unit'],'price':p,'task':'settle','currency':'credits','iat':now,'cert':chosen['cert'],'claim':{'sku':chosen['sku'],'quantity':1,'grade':chosen['grade']}}
 jwt=kit.sign_jwt(payload,'shop');locks[chosen['sku']]={'time':now,'customer':args.get('claimed_from','')};open(lp,'w',encoding='utf-8').write(json.dumps(locks,ensure_ascii=False))
 return {'reply':f"{chosen['name']} {p}크레딧입니다. 등급 {chosen['grade'] or '미확인'}, 인증서 등급 {chosen['cert'] or '미확인'}, 잔여시간 {chosen['expiry'] or '미확인'}입니다.",'data':{'checkout_jwt':jwt,'sku':chosen['sku'],'unit':chosen['unit'],'price':p},'state':'completed'}