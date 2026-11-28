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
  keys=('items','inventory','units','data','results','stock','records')
  o=[]
  for k in keys:
   if k in x:o+=flat(x[k])
  if o:return o
  if any(k in x for k in ('sku','sku_id','unit_id','unitId','id','code','product_id','productId')):return [x]
  for k,v in x.items():
   if isinstance(v,dict):
    q=dict(v);q.setdefault('sku',k);o+=flat(q)
  return o
 return []

def val(e,ks):
 for k in ks:
  if e.get(k) is not None:return e[k]
def kid(e):return str(val(e,['sku','sku_id','unit_id','unitId','id','code','product_id','productId']) or '')
def norm(x):return re.sub(r'[^0-9a-z가-힣]','',str(x or '').lower())
def run(args,kit):
 test=kit.testing;cp='test_card.json' if test else 'card.json';lp='test_checkout_locks.json' if test else 'checkout_locks.json'
 card=load(cp,{});stock=card.get('stock',card.get('inventory',{})) or {}
 if isinstance(stock,list): stock={kid(x):1 for x in stock}
 raw=[]
 if test: raw=flat(load('test_catalog.json',[]))
 else:
  try:
   r=httpx.get(kit.market+'/api/inventory',headers={'authorization':'Bearer '+kit.token('shop')},timeout=8)
   if r.status_code<300: raw=flat(r.json())
  except: pass
 if not raw: raw=flat(load('catalog.json',[]))
 by={kid(e):e for e in raw if isinstance(e,dict)};table=[]
 for sku,n in stock.items():
  if int(n or 0)>0 and str(sku) in by:
   e=by[str(sku)];table.append({'sku':str(sku),'name':val(e,['name','item_name','product_name','품목명','title']),'grade':val(e,['grade','등급']),'unit':val(e,['unit','unit_name','단위']),'cost':val(e,['cost','unit_cost','원가','price']),'certificate_grade':val(e,['certificate_grade','certificate','인증서등급']),'expires_at':val(e,['expires_at','expiry','remaining_time','잔여시간']),'aliases':val(e,['aliases','alias']) or []})
 if not test:
  try:
   with open('catalog.json','w',encoding='utf-8') as f: json.dump(table,f,ensure_ascii=False)
  except: pass
 t=str(args.get('text',''));low=norm(t)
 if not any(x in low for x in ('구매','주문','결제','사줘','buy','checkout')):return {'reply':'구매하실 품목을 말씀해 주세요.','state':'completed'}
 f=next((e for e in table if any(norm(x) and norm(x) in low for x in [e['name']]+(e['aliases'] if isinstance(e['aliases'],list) else []))),None)
 if not f:return {'reply':'요청하신 품목은 현재 재고가 없습니다. 결제서와 예약을 만들지 않았습니다.','state':'completed'}
 try:p=int((float(f['cost'])+210)/.99)+1
 except:return {'reply':'원가를 확인하지 못해 결제서와 예약을 만들지 않았습니다.','state':'completed'}
 locks=load(lp,{});now=int(time.time());o=locks.get(f['sku'])
 if isinstance(o,dict) and now-int(o.get('time',now))<10800:return {'reply':'해당 상품은 잠시 예약 중입니다.','state':'completed'}
 jwt=kit.sign_jwt({'sku':f['sku'],'quantity':1,'price':p,'shop':kit.shop_url,'ts':now},'shop')
 if not jwt:return {'reply':'결제서 생성에 실패했습니다.','state':'completed'}
 locks[f['sku']]={'time':now,'customer':args.get('claimed_from','')}
 with open(lp,'w',encoding='utf-8') as z:json.dump(locks,z,ensure_ascii=False)
 return {'reply':f"{f['name']} {p}크레딧입니다. 등급 {f['grade'] or '미확인'}, 인증서 등급 {f['certificate_grade'] or '미확인'}, 잔여시간 {f['expires_at'] or '미확인'}입니다.",'data':{'checkout_jwt':jwt,'sku':f['sku'],'price':p},'state':'completed'}