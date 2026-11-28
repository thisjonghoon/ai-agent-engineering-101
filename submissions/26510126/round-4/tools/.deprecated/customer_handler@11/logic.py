import json,time

def run(args,kit):
    text=str(args.get('text',''))
    low=text.lower()
    path='test_checkout_locks.json' if kit.testing else 'checkout_locks.json'
    try:
        with open(path,encoding='utf-8') as f:
            locks=json.load(f)
        if not isinstance(locks,dict):
            locks={}
    except Exception:
        locks={}
    buy=any(x in low for x in ('구매','주문','결제','buy','checkout'))
    if not buy:
        return {'reply':'현재 재고를 확인해 드릴게요. 구매하실 품목을 말씀해 주세요.','state':'completed'}
    if any(x in low for x in ('생선','물고기','fish')):
        return {'reply':'죄송하지만 생선 재고가 없습니다. 결제서와 예약을 만들지 않았습니다.','state':'completed'}
    if not any(x in low for x in ('사과','귤','apple','orange')):
        return {'reply':'요청하신 품목은 현재 확인하지 못했습니다.','state':'completed'}
    sku='G36ca7485'
    now=int(time.time())
    old=locks.get(sku)
    if isinstance(old,dict) and now-int(old.get('time',now))<10800:
        return {'reply':'죄송합니다. 해당 상품은 잠시 예약 중입니다.','state':'completed'}
    try:
        with open('prices.json',encoding='utf-8') as f: prices=json.load(f)
        value=prices.get(sku,5644)
        price=int(value.get('price',value.get('median',5644)) if isinstance(value,dict) else value)
    except Exception:
        price=5644
    if price<5310: price=5644
    jwt=kit.sign_jwt({'sku':sku,'quantity':1,'price':price,'shop':kit.shop_url,'ts':now},'shop')
    if not jwt:
        return {'reply':'죄송합니다. 공식 결제서 생성에 실패해 예약하지 않았습니다.','state':'completed'}
    locks[sku]={'time':now,'customer':args.get('claimed_from','')}
    with open(path,'w',encoding='utf-8') as f: json.dump(locks,f,ensure_ascii=False)
    return {'reply':f'사과 {price}크레딧입니다. 공식 서명 결제서를 보냅니다. 등급·인증서 등급·잔여시간은 공개 기록 기준이며 확인하지 못한 조건은 별도 확인이 필요합니다.','data':{'checkout_jwt':jwt,'sku':sku,'price':price},'state':'completed'}
