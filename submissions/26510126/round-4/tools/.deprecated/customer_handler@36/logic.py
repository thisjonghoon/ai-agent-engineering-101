import json,time,re,httpx

def load(p,d):
 try:
  with open(p,encoding='utf-8') as f:return json.load(f)
 except:return d

def flat(x):
 if isinstance(x,list):
  o=[]
  for v in x:o+=flat(v)
  return o
 if isinstance(x,dict):
  for k in ('items','inventory','units','data','results','stock','records'):
   if k in x:
    q=flat(x[k])
    if q:return q
  if any(k in x for k in ('sku','sku_id','unit_id','unitId','id','code','product_id')):return [x]
  o=[]
  for k,v in x.items():
   if isinstance(v,dict):
    q=dict(v);q.setdefault('sku',k);o+=flat(q)
  return o
 return []

def val(e,ks):
 for k in ks:
  if isinstance(e,dict) and e.get(k) is not None:return e[k]

def sid(e):return str(val(e,['sku','sku_id','id','code','product_id','productId']) or '')
def norm(x):return re.sub(r'[^0-9a-z가-힣]','',str(x or '').lower())
def run(args,kit):
 test=kit.testing; cp='test_card.json' if test else 'card.json'; lp='test_checkout_locks.json' if test else 'checkout_locks.json'
 card=load(cp,{}); stock=card.get('stock',card.get('inventory',{})) or {}
 if isinstance(stock,list):stock={sid(x):1 for x in stock}
 cat=flat(load('test_catalog.json' if test else 'catalog.json',[])); cm={sid(x):x for x in cat if isinstance(x,dict) and sid(x)}
 inv={}
 if not test:
  try:
   r=httpx.get(kit.market+'/api/inventory',headers={'authorization':'Bearer '+kit.token('shop')},timeout=8)
   if r.status_code<300:inv={sid(x):x for x in flat(r.json()) if isinstance(x,dict) and sid(x)}
  except: pass
 rows=[]
 for sku,n in stock.items():
  if int(n or 0)<=0 or str(sku) not in cm: continue
  c=cm[str(sku)]; i=inv.get(str(sku),{})
  rows.append({'sku':str(sku),'name':val(c,['name','title']) or val(i,['name','title']),'grade':val(i,['grade']) or val(c,['grade']),'unit':val(i,['unit','unit_id','unitId']) or val(c,['unit','unit_id','unitId']),'cost':val(c,['cost','unit_cost','원가','price']),'certificate_grade':val(i,['certificate_grade','certificate']) or val(c,['certificate_grade','certificate']),'expires_at':val(i,['expires_at','expiry']) or val(c,['expires_at','expiry']),'aliases':val(c,['aliases','alias']) or []})
 text=str(args.get('text','')); low=norm(text)
 if not low or (any(x in low for x in ('안녕','가격','얼마','문의')) and not any(x in low for x in ('구매','주문','결제','사줘','찾','소량'))): return {'reply':'구매하실 품목을 말씀해 주세요.','state':'completed'}
 chosen=None
 for e in rows:
  terms=[e['sku'],e.get('unit'),e.get('name')]+(e['aliases'] if isinstance(e['aliases'],list) else [])
  if any(norm(t) and norm(t) in low for t in terms): chosen=e; break
 if not chosen:return {'reply':'요청하신 품목은 현재 재고가 없습니다. 결제서와 예약을 만들지 않았습니다.','state':'completed'}
 try: price=int((float(chosen['cost'])+210)/.99)+1
 except:return {'reply':'원가를 확인하지 못해 결제서와 예약을 만들지 않았습니다.','state':'completed'}
 locks=load(lp,{})
 if not isinstance(locks,dict):locks={}
 now=int(time.time()); old=locks.get(chosen['sku'])
 if isinstance(old,dict) and now-int(old.get('time',0))<10800:return {'reply':'해당 상품은 잠시 예약 중입니다.','state':'completed'}
 payload={'id':chosen['sku']+'-'+str(now),'shop':'thisjonghoon','shop_url':kit.shop_url,'item':chosen['name'],'unit':chosen['unit'],'price':price,'task':'settle','currency':'credits','iat':now,'cert':chosen['certificate_grade'],'claim':{'sku':chosen['sku'],'quantity':1,'grade':chosen['grade']}}
 jwt=kit.sign_jwt(payload,'shop')
 locks[chosen['sku']]={'time':now,'customer':args.get('claimed_from','')};open(lp,'w',encoding='utf-8').write(json.dumps(locks,ensure_ascii=False))
 return {'reply':f"{chosen['name']} {price}크레딧입니다. 등급 {chosen['grade'] or '미확인'}, 인증서 등급 {chosen['certificate_grade'] or '미확인'}, 잔여시간 {chosen['expires_at'] or '미확인'}입니다.",'data':{'checkout_jwt':jwt,'sku':chosen['sku'],'unit':chosen['unit'],'price':price},'state':'completed'}