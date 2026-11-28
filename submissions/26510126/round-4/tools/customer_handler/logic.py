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
  out=[]
  for v in x.values(): out += rows(v)
  return out
 return []

def sku(e): return str(e.get('sku',e.get('id',e.get('code',''))))
def norm(x): return re.sub(r'[^0-9a-z가-힣]','',str(x).lower())
def meta(e,k,*alts):
 for x in (k,)+alts:
  if x in e and e[x] is not None:return e[x]
 return '미확인'

def run(args,kit):
 test=kit.testing
 card=load('test_card.json' if test else 'card.json',{})
 stock=card.get('stock',card.get('inventory',{})) or {}
 cp='test_catalog.json' if test else 'catalog.json'
 allcat=rows(load(cp,[]))
 if not test:
  allcat=rows(load('catalog.json',[]))
 by={sku(e):e for e in allcat if isinstance(e,dict)}
 wanted=[str(k) for k,v in stock.items() if int(v or 0)>0]
 table=[by[s] for s in wanted if s in by]
 if not test:
  with open(cp,'w',encoding='utf-8') as f: json.dump(table,f,ensure_ascii=False)
 text=str(args.get('text','')); low=norm(text)
 if not any(x in low for x in ('구매','주문','결제','사줘','buy','checkout')):
  return {'reply':'현재 재고를 확인해 드릴게요. 구매하실 품목을 말씀해 주세요.','state':'completed'}
 found=None
 for e in table:
  s=sku(e)
  if int(stock.get(s,0) or 0)<=0: continue
  vals=[]
  for k,v in e.items():
   if k not in ('sku','id','code') and not isinstance(v,(dict,list)): vals.append(norm(v))
  if any(v and (v in low or low in v) for v in vals): found=e; break
 if not found:return {'reply':'요청하신 품목은 현재 재고가 없습니다. 결제서와 예약을 만들지 않았습니다.','state':'completed'}
 s=sku(found); lp='test_checkout_locks.json' if test else 'checkout_locks.json'; locks=load(lp,{})
 now=int(time.time()); old=locks.get(s)
 if isinstance(old,dict) and now-int(old.get('time',now))<10800:return {'reply':'죄송합니다. 해당 상품은 잠시 예약 중입니다.','state':'completed'}
 prices=load('prices.json',{}); q=prices.get(s,found.get('price',0)); price=int((q.get('price',q.get('median',0)) if isinstance(q,dict) else q) or 0)
 cost=float(meta(found,'cost','unit_cost', '원가') or 0); price=max(price,int((cost+210)/.99)+1 if cost else 0)
 jwt=kit.sign_jwt({'sku':s,'quantity':1,'price':price,'shop':kit.shop_url,'ts':now},'shop')
 if not jwt:return {'reply':'공식 결제서 생성에 실패해 예약하지 않았습니다.','state':'completed'}
 locks[s]={'time':now,'customer':args.get('claimed_from','')}
 with open(lp,'w',encoding='utf-8') as f: json.dump(locks,f,ensure_ascii=False)
 grade=meta(found,'grade','등급'); cert=meta(found,'certificate_grade','certificate','인증서등급'); expiry=meta(found,'expires_at','expiry','shelf_life','잔여시간')
 return {'reply':f"{meta(found,'name','item_name', '품목명')} {price}크레딧입니다. 등급 {grade}, 인증서 등급 {cert}, 잔여시간 {expiry}입니다. 공식 서명 결제서를 보냅니다.",'data':{'checkout_jwt':jwt,'sku':s,'price':price},'state':'completed'}
