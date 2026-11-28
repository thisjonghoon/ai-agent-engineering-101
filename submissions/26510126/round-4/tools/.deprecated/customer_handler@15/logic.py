import json,time,httpx

def load(p,d):
 try:
  with open(p,encoding='utf-8') as f:return json.load(f)
 except:return d

def catalog(kit):
 p='test_catalog.json' if kit.testing else 'catalog.json'; c=load(p,{})
 if c:return c
 for u in [kit.market+'/api/catalog',kit.market+'/api/wholesale/catalog',kit.market+'/api/shops']:
  try:
   r=httpx.get(u,timeout=5)
   if r.status_code==200:
    x=r.json()
    if isinstance(x,dict):
     for k in ('catalog','items','products','result'):
      if k in x and isinstance(x[k],(list,dict)): return x[k]
  except: pass
 return {}

def run(args,kit):
 text=str(args.get('text','')); low=text.lower()
 if not any(x in low for x in ('구매','주문','결제','buy','checkout')): return {'reply':'현재 재고를 확인해 드릴게요. 구매하실 품목을 말씀해 주세요.','state':'completed'}
 card=load('test_card.json' if kit.testing else 'card.json',{}); stock=card.get('stock',card.get('inventory',{})); stock=stock if isinstance(stock,dict) else {}
 cat=catalog(kit); entries=list(cat.values()) if isinstance(cat,dict) else cat
 if not isinstance(entries,list): entries=[]
 found=None
 for e in entries:
  if not isinstance(e,dict): continue
  sku=str(e.get('sku',e.get('id','')))
  if sku not in stock or not stock[sku]: continue
  vals=[e.get(k,'') for k in ('name','item','product','title','display_name','unit','category')]
  if any(str(v) and str(v).lower() in low for v in vals): found=(e,sku); break
 if not found:return {'reply':'요청하신 품목은 현재 재고가 없습니다. 결제서와 예약을 만들지 않았습니다.','state':'completed'}
 e,sku=found; path='test_checkout_locks.json' if kit.testing else 'checkout_locks.json'; locks=load(path,{})
 now=int(time.time()); old=locks.get(sku)
 if isinstance(old,dict) and now-int(old.get('time',now))<10800:return {'reply':'죄송합니다. 해당 상품은 잠시 예약 중입니다.','state':'completed'}
 p=load('prices.json',{}).get(sku,e.get('price',0)); price=int(p.get('price',p.get('median',0)) if isinstance(p,dict) else p); cost=float(e.get('cost',0) or 0)
 if cost and price < (cost+210)/.99: price=int((cost+210)/.99)+1
 jwt=kit.sign_jwt({'sku':sku,'quantity':1,'price':price,'shop':kit.shop_url,'ts':now},'shop')
 if not jwt:return {'reply':'공식 결제서 생성에 실패해 예약하지 않았습니다.','state':'completed'}
 locks[sku]={'time':now,'customer':args.get('claimed_from','')}
 with open(path,'w',encoding='utf-8') as f:json.dump(locks,f,ensure_ascii=False)
 return {'reply':f"{e.get('name',e.get('unit',sku))} {price}크레딧입니다. 등급 {e.get('grade','미확인')}, 인증서 등급 {e.get('certificate_grade',e.get('certificate','미확인'))}, 잔여시간 {e.get('expires_at',e.get('expiry','미확인'))}입니다. 공식 서명 결제서를 보냅니다.",'data':{'checkout_jwt':jwt,'sku':sku,'price':price},'state':'completed'}
