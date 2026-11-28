import json,time

def load(p,d):
 try:
  with open(p,encoding='utf-8') as f:return json.load(f)
 except Exception:return d

def rows(x):
 if isinstance(x,list): return x
 if isinstance(x,dict):
  for k in ('items','catalog','products','results','data'):
   if isinstance(x.get(k),list): return x[k]
  for v in x.values():
   r=rows(v)
   if r:return r
 return []

def sku(e): return str(e.get('sku',e.get('id',e.get('code',''))))

def run(args,kit):
 test=kit.testing
 card=load('test_card.json' if test else 'card.json',{})
 stock=card.get('stock',card.get('inventory',{})) or {}
 wanted={str(k) for k,v in stock.items() if int(v or 0)>0}
 cp='test_catalog.json' if test else 'catalog.json'
 raw=rows(load(cp,[]))
 table=[e for e in raw if isinstance(e,dict) and sku(e) in wanted]
 if len(table)<len(wanted):
  full=rows(load('catalog.json',[]))
  by={sku(e):e for e in full if isinstance(e,dict)}
  table=[by[s] for s in wanted if s in by]
 if not test and table:
  with open(cp,'w',encoding='utf-8') as f: json.dump(table,f,ensure_ascii=False)
 text=str(args.get('text','')); low=text.lower()
 if not any(x in low for x in ('구매','주문','결제','사줘','buy','checkout')):
  return {'reply':'현재 재고를 확인해 드릴게요. 구매하실 품목을 말씀해 주세요.','state':'completed'}
 found=None
 for e in table:
  s=sku(e)
  if int(stock.get(s,0) or 0)<=0: continue
  vals=[str(v).lower() for k,v in e.items() if k not in ('sku','id','code') and not isinstance(v,(dict,list)) and v is not None]
  if any(v and v in low for v in vals): found=(e,s); break
 if not found:return {'reply':'요청하신 품목은 현재 재고가 없습니다. 결제서와 예약을 만들지 않았습니다.','state':'completed'}
 e,s=found; path='test_checkout_locks.json' if test else 'checkout_locks.json'; locks=load(path,{})
 now=int(time.time()); old=locks.get(s)
 if isinstance(old,dict) and now-int(old.get('time',now))<10800:return {'reply':'죄송합니다. 해당 상품은 잠시 예약 중입니다.','state':'completed'}
 prices=load('prices.json',{}); q=prices.get(s,e.get('price',0)); price=int((q.get('price',q.get('median',0)) if isinstance(q,dict) else q) or 0)
 cost=float(e.get('cost',e.get('unit_cost',0)) or 0); floor=int((cost+210)/.99)+1 if cost else 0
 price=max(price,floor)
 jwt=kit.sign_jwt({'sku':s,'quantity':1,'price':price,'shop':kit.shop_url,'ts':now},'shop')
 if not jwt:return {'reply':'공식 결제서 생성에 실패해 예약하지 않았습니다.','state':'completed'}
 locks[s]={'time':now,'customer':args.get('claimed_from','')}
 with open(path,'w',encoding='utf-8') as f: json.dump(locks,f,ensure_ascii=False)
 return {'reply':f"{e.get('name',e.get('unit',s))} {price}크레딧입니다. 등급 {e.get('grade','미확인')}, 인증서 등급 {e.get('certificate_grade',e.get('certificate','미확인'))}, 잔여시간 {e.get('expires_at',e.get('expiry',e.get('shelf_life','미확인')))}입니다. 공식 서명 결제서를 보냅니다.",'data':{'checkout_jwt':jwt,'sku':s,'price':price},'state':'completed'}
