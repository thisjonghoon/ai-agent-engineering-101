import json,time

def load(p,d):
 try:
  with open(p,encoding='utf-8') as f:return json.load(f)
 except:return d

def rows(x):
 if isinstance(x,list):return x
 if isinstance(x,dict):
  for k in ('items','catalog','products','results','data'):
   if isinstance(x.get(k),list):return x[k]
  for v in x.values():
   r=rows(v)
   if r:return r
 return []
def sid(e):return str(e.get('sku',e.get('id',e.get('code',''))))
def run(args,kit):
 t=kit.testing; card=load('test_card.json' if t else 'card.json',{}); st=card.get('stock',card.get('inventory',{})) or {}; wanted={str(k) for k,v in st.items() if int(v or 0)>0}; cp='test_catalog.json' if t else 'catalog.json'; allc=rows(load(cp,[])); by={sid(e):e for e in allc if isinstance(e,dict)}
 if not t and len(by)<len(wanted):
  full={sid(e):e for e in rows(load('catalog.json',[])) if isinstance(e,dict)}; by.update({s:full[s] for s in wanted if s in full})
 table=[by[s] for s in wanted if s in by]
 if not t:
  with open(cp,'w',encoding='utf-8') as f:json.dump(table,f,ensure_ascii=False)
 text=str(args.get('text','')); low=text.lower()
 if not any(x in low for x in ('구매','주문','결제','사줘','buy','checkout')):return {'reply':'현재 재고를 확인해 드릴게요. 구매하실 품목을 말씀해 주세요.','state':'completed'}
 found=None
 for e in table:
  vals=[str(v).lower() for k,v in e.items() if k not in ('sku','id','code') and not isinstance(v,(dict,list)) and v is not None]
  if int(st.get(sid(e),0) or 0)>0 and any(v and v in low for v in vals):found=e;break
 if not found:return {'reply':'요청하신 품목은 현재 재고가 없습니다. 결제서와 예약을 만들지 않았습니다.','state':'completed'}
 s=sid(found); p='test_checkout_locks.json' if t else 'checkout_locks.json'; locks=load(p,{}); now=int(time.time()); old=locks.get(s)
 if isinstance(old,dict) and now-int(old.get('time',now))<10800:return {'reply':'죄송합니다. 해당 상품은 잠시 예약 중입니다.','state':'completed'}
 q=load('prices.json',{}).get(s,found.get('price',0)); price=int((q.get('price',q.get('median',0)) if isinstance(q,dict) else q) or 0); cost=float(found.get('cost',found.get('unit_cost',0)) or 0); price=max(price,int((cost+210)/.99)+1 if cost else 0); jwt=kit.sign_jwt({'sku':s,'quantity':1,'price':price,'shop':kit.shop_url,'ts':now},'shop')
 if not jwt:return {'reply':'공식 결제서 생성에 실패해 예약하지 않았습니다.','state':'completed'}
 locks[s]={'time':now,'customer':args.get('claimed_from','')}
 with open(p,'w',encoding='utf-8') as f:json.dump(locks,f,ensure_ascii=False)
 return {'reply':f"{found.get('name',found.get('unit',s))} {price}크레딧입니다. 등급 {found.get('grade','미확인')}, 인증서 등급 {found.get('certificate_grade',found.get('certificate','미확인'))}, 잔여시간 {found.get('expires_at',found.get('expiry',found.get('shelf_life','미확인')))}입니다. 공식 서명 결제서를 보냅니다.",'data':{'checkout_jwt':jwt,'sku':s,'price':price},'state':'completed'}
