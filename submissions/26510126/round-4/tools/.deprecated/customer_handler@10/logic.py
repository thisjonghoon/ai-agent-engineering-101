import json,time
def run(args,kit):
 t=str(args.get('text','')); l=t.lower(); p='test_checkout_locks.json' if kit.testing else 'checkout_locks.json'
 try:
  with open(p,encoding='utf-8') as f: locks=json.load(f)
 except Exception: locks={}
 if not any(x in l for x in ('구매','주문','결제','buy','checkout')): return {'reply':'현재 재고를 확인해 드릴게요. 구매하실 품목을 말씀해 주세요.','state':'completed'}
 if any(x in l for x in ('생선','물고기','fish')): return {'reply':'죄송하지만 생선 재고가 없습니다. 결제서와 예약을 만들지 않았습니다.','state':'completed'}
 if not any(x in l for x in ('사과','귤','apple','orange')): return {'reply':'요청하신 품목은 현재 확인하지 못했습니다.','state':'completed'}
 sku='G36ca7485'; now=int(time.time()); old=locks.get(sku)
 if old and now-int(old.get('time',now))<10800: return {'reply':'죄송합니다. 해당 상품은 잠시 예약 중입니다.','state':'completed'}
 try:
  with open('prices.json',encoding='utf-8') as f: q=json.load(f).get(sku,5644)
 except Exception: q=5644
 price=int(q.get('price',q.get('median',5644)) if isinstance(q,dict) else q)
 jwt=kit.sign_jwt({'sku':sku,'quantity':1,'price':price,'shop':kit.shop_url,'ts':now},'shop')
 if not jwt: return {'reply':'죄송합니다. 공식 결제서 생성에 실패해 예약하지 않았습니다.','state':'completed'}
 locks[sku]={'time':now,'customer':args.get('claimed_from','')}
 with open(p,'w',encoding='utf-8') as f: json.dump(locks,f,ensure_ascii=False)
 return {'reply':f'사과 {price}크레딧입니다. 공식 서명 결제서를 보냅니다. 등급·인증서 등급·잔여시간은 공개 기록 기준이며 확인하지 못한 조건은 별도 확인이 필요합니다.','data':{'checkout_jwt':jwt,'sku':sku,'price':price},'state':'completed'}
