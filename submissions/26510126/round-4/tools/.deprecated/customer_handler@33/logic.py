import json,time,re,httpx

def load(p,d):
 try:
  with open(p,encoding='utf-8') as f:return json.load(f)
 except:return d

def flat(x):
 if isinstance(x,list):
  out=[]
  for v in x: out += flat(v)
  return out
 if isinstance(x,dict):
  for k in ('items','inventory','units','data','results','stock','records'):
   if k in x:
    q=flat(x[k])
    if q:return q
  if any(k in x for k in ('sku','sku_id','unit_id','unitId','id','code','product_id','productId')): return [x]
  out=[]
  for k,v in x.items():
   if isinstance(v,dict):
    q=dict(v); q.setdefault('sku',k); out += flat(q)
  return out
 return []

def get(e,keys):
 for k in keys:
  if isinstance(e,dict) and e.get(k) is not None:return e[k]

def sku(e): return str(get(e,['sku','sku_id','unit_id','unitId','id','code','product_id','productId']) or '')
def norm(x): return re.sub(r'[^0-9a-z가-힣]','',str(x or '').lower())
def run(args,kit):
 test=kit.testing; cp='test_card.json' if test else 'card.json'; lp='test_checkout_locks.json' if test else 'checkout_locks.json'
 card=load(cp,{}); st=card.get('stock',card.get('inventory',{})) or {}
 if isinstance(st,list): st={sku(x):1 for x in st}
 raw=flat(load('test_catalog.json',[])) if test else []
 if not test:
  try:
   r=httpx.get(kit.market+'/api/inventory',headers={'authorization':'Bearer '+kit.token('shop')},timeout=8)
   if r.status_code<300: raw=flat(r.json())
  except Exception: pass
 by={sku(e):e for e in raw if isinstance(e,dict) and sku(e)}
 rows=[]
 for s,n in st.items():
  if int(n or 0)>0 and str(s) in by:
   e=by[str(s)]; rows.append({'sku':str(s),'name':get(e,['name','item_name','product_name','품목명','title']),'grade':get(e,['grade','등급']),'unit':get(e,['unit','unit_name','단위']),'cost':get(e,['cost','unit_cost','원가','price']),'certificate_grade':get(e,['certificate_grade','certificate','인증서등급']),'expires_at':get(e,['expires_at','expiry','remaining_time','잔여시간']),'aliases':get(e,['aliases','alias']) or []})
 if not test:
  try:
   with open('catalog.json','w',encoding='utf-8') as f: json.dump(rows,f,ensure_ascii=False)
  except Exception: pass
 text=str(args.get('text','')); low=norm(text)
 if not any(x in low for x in ('구매','주문','결제','사줘','buy','checkout')): return {'reply':'구매하실 품목을 말씀해 주세요.','state':'completed'}
 chosen=None
 for e in rows:
  names=[e.get('name'),e.get('unit')]+(e.get('aliases') if isinstance(e.get('aliases'),list) else [])
  if any(norm(x) and norm(x) in low for x in names): chosen=e; break
 if not chosen:return {'reply':'요청하신 품목은 현재 재고가 없습니다. 결제서와 예약을 만들지 않았습니다.','state':'completed'}
 try: price=int((float(chosen['cost'])+210)/.99)+1
 except Exception:return {'reply':'원가를 확인하지 못해 결제서와 예약을 만들지 않았습니다.','state':'completed'}
 locks=load(lp,{}); now=int(time.time()); old=locks.get(chosen['sku'])
 if isinstance(old,dict) and now-int(old.get('time',now))<10800:return {'reply':'해당 상품은 잠시 예약 중입니다.','state':'completed'}
 jwt=kit.sign_jwt({'sku':chosen['sku'],'quantity':1,'price':price,'shop':kit.shop_url,'ts':now},'shop')
 if not jwt:return {'reply':'결제서 생성에 실패했습니다.','state':'completed'}
 locks[chosen['sku']]={'time':now,'customer':args.get('claimed_from','')}
 with open(lp,'w',encoding='utf-8') as f: json.dump(locks,f,ensure_ascii=False)
 return {'reply':f"{chosen['name']} {price}크레딧입니다. 등급 {chosen['grade'] or '미확인'}, 인증서 등급 {chosen['certificate_grade'] or '미확인'}, 잔여시간 {chosen['expires_at'] or '미확인'}입니다.",'data':{'checkout_jwt':jwt,'sku':chosen['sku'],'price':price},'state':'completed'}