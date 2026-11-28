import json,time,re

def load(p,d):
 try:
  with open(p,encoding='utf-8') as f:return json.load(f)
 except:return d

def rows(x):
 if isinstance(x,list): return x
 if isinstance(x,dict):
  for k in ('items','catalog','products','results','data'):
   if isinstance(x.get(k),list): return x[k]
  z=[]
  for v in x.values(): z+=rows(v)
  return z
 return []

def sku(e): return str(e.get('sku',e.get('id',e.get('code',''))))
def norm(x): return re.sub(r'[^0-9a-z가-힣]','',str(x).lower())
def get(e,*ks):
 for k in ks:
  if e.get(k) is not None:return e[k]
 return None

def run(args,kit):
 t=kit.testing; card=load('test_card.json' if t else 'card.json',{}); stock=card.get('stock',card.get('inventory',{})) or {}; cp='test_catalog.json' if t else 'catalog.json'; cat=rows(load(cp,[])); by={sku(e):e for e in cat if isinstance(e,dict)}; active=[by[s] for s,n in stock.items() if int(n or 0)>0 and s in by]
 if not t:
  with open(cp,'w',encoding='utf-8') as f: json.dump(active,f,ensure_ascii=False)
 text=str(args.get('text','')); low=norm(text)
 if not any(x in low for x in ('구매','주문','결제','사줘','buy','checkout')): return {'reply':'구매하실 품목을 말씀해 주세요.','state':'completed'}
 found=None
 for e in active:
  ns=[get(e,'name','item_name','품목명','product_name')]; a=get(e,'aliases','alias'); ns+=a if isinstance(a,list) else []
  if any(n and len(norm(n))>=2 and norm(n) in low for n in ns): found=e; break
 if not found:return {'reply':'요청하신 품목은 현재 재고가 없습니다. 결제서와 예약을 만들지 않았습니다.','state':'completed'}
 s=sku(found); c=get(found,'cost','unit_cost','원가')
 try:c=float(c)
 except:c=0
 q=load('prices.json',{}).get(s,0); p=int((q.get('price',q.get('median',0)) if isinstance(q,dict) else q) or 0); floor=int((c+210)/.99)+1 if c>0 else 0
 if c<=0 or p<floor:return {'reply':'원가와 가격을 검증하지 못해 결제서와 예약을 만들지 않았습니다.','state':'completed'}
 lp='test_checkout_locks.json' if t else 'checkout_locks.json'; locks=load(lp,{}); now=int(time.time()); old=locks.get(s)
 if isinstance(old,dict) and now-int(old.get('time',now))<10800:return {'reply':'해당 상품은 잠시 예약 중입니다.','state':'completed'}
 jwt=kit.sign_jwt({'sku':s,'quantity':1,'price':p,'shop':kit.shop_url,'ts':now},'shop')
 if not jwt:return {'reply':'결제서 생성에 실패해 예약하지 않았습니다.','state':'completed'}
 locks[s]={'time':now,'customer':args.get('claimed_from','')}
 with open(lp,'w',encoding='utf-8') as f: json.dump(locks,f,ensure_ascii=False)
 return {'reply':f"{get(found,'name','item_name','품목명')} {p}크레딧입니다. 등급 {get(found,'grade','등급') or '미확인'}, 인증서 등급 {get(found,'certificate_grade','certificate','인증서등급') or '미확인'}, 잔여시간 {get(found,'expires_at','expiry','shelf_life','잔여시간') or '미확인'}입니다.",'data':{'checkout_jwt':jwt,'sku':s,'price':p},'state':'completed'}
