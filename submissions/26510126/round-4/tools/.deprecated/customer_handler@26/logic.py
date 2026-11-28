import json,time,re

def load(p,d):
 try:
  with open(p,encoding='utf-8') as f:return json.load(f)
 except:return d

def flat(x):
 if isinstance(x,list): return x
 if isinstance(x,dict):
  z=[]
  for k in ('items','catalog','products','results','data'):
   if isinstance(x.get(k),list): z+=x[k]
  if z:return z
  for v in x.values(): z+=flat(v)
  return z
 return []

def sid(e): return str(e.get('sku',e.get('id',e.get('code',''))))
def nm(x): return re.sub(r'[^0-9a-z가-힣]','',str(x or '').lower())
def get(e,*ks):
 for k in ks:
  if e.get(k) is not None:return e[k]
 return None

def run(args,kit):
 test=kit.testing; card=load('test_card.json' if test else 'card.json',{}); stock=card.get('stock',card.get('inventory',{})) or {}
 cp='test_catalog.json' if test else 'catalog.json'; raw=flat(load(cp,[])); by={sid(e):e for e in raw if isinstance(e,dict)}
 table=[]
 for s,n in stock.items():
  if int(n or 0)>0 and s in by:
   e=by[s]; table.append({'sku':s,'name':get(e,'name','item_name','품목명','product_name'),'grade':get(e,'grade','등급'),'unit':get(e,'unit','unit_name','단위'),'cost':get(e,'cost','unit_cost','원가'),'certificate_grade':get(e,'certificate_grade','certificate','인증서등급'),'expires_at':get(e,'expires_at','expiry','shelf_life','잔여시간'),'aliases':get(e,'aliases','alias') or []})
 with open(cp,'w',encoding='utf-8') as f: json.dump(table,f,ensure_ascii=False)
 text=str(args.get('text','')); low=nm(text)
 if not any(x in low for x in ('구매','주문','결제','사줘','buy','checkout')): return {'reply':'구매하실 품목을 말씀해 주세요.','state':'completed'}
 found=None
 for e in table:
  ns=[e.get('name')]+(e.get('aliases') if isinstance(e.get('aliases'),list) else [])
  if any(nm(x) and len(nm(x))>=2 and nm(x) in low for x in ns): found=e; break
 if not found:return {'reply':'요청하신 품목은 현재 재고가 없습니다. 결제서와 예약을 만들지 않았습니다.','state':'completed'}
 try: cost=float(found.get('cost') or 0)
 except: cost=0
 prices=load('prices.json',{}); q=prices.get(found['sku'],0); p=int((q.get('price',q.get('median',0)) if isinstance(q,dict) else q) or 0); floor=int((cost+210)/.99)+1
 if cost<=0 or p<floor:return {'reply':'원가와 가격을 검증하지 못해 결제서와 예약을 만들지 않았습니다.','state':'completed'}
 lp='test_checkout_locks.json' if test else 'checkout_locks.json'; locks=load(lp,{})
 old=locks.get(found['sku']); now=int(time.time())
 if isinstance(old,dict) and now-int(old.get('time',now))<10800:return {'reply':'해당 상품은 잠시 예약 중입니다.','state':'completed'}
 jwt=kit.sign_jwt({'sku':found['sku'],'quantity':1,'price':p,'shop':kit.shop_url,'ts':now},'shop')
 if not jwt:return {'reply':'결제서 생성에 실패해 예약하지 않았습니다.','state':'completed'}
 locks[found['sku']]={'time':now,'customer':args.get('claimed_from','')}
 with open(lp,'w',encoding='utf-8') as f: json.dump(locks,f,ensure_ascii=False)
 return {'reply':f"{found.get('name')} {p}크레딧입니다. 등급 {found.get('grade') or '미확인'}, 인증서 등급 {found.get('certificate_grade') or '미확인'}, 잔여시간 {found.get('expires_at') or '미확인'}입니다.",'data':{'checkout_jwt':jwt,'sku':found['sku'],'price':p},'state':'completed'}
