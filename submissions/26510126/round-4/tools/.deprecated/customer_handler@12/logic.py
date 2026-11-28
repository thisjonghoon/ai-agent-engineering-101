import json,time

def load(path,default):
    try:
        with open(path,encoding='utf-8') as f:return json.load(f)
    except Exception:return default

def run(args,kit):
    text=str(args.get('text','')); low=text.lower()
    path='test_checkout_locks.json' if kit.testing else 'checkout_locks.json'
    locks=load(path,{})
    if not isinstance(locks,dict): locks={}
    if not any(x in low for x in ('구매','주문','결제','buy','checkout')):
        return {'reply':'현재 재고를 확인해 드릴게요. 구매하실 품목을 말씀해 주세요.','state':'completed'}
    card=load('card.json',{})
    raw=card.get('stock',card.get('inventory',card.get('items',[]))) if isinstance(card,dict) else []
    if isinstance(raw,dict): raw=list(raw.values())
    if not isinstance(raw,list): raw=[]
    found=None
    for item in raw:
        if not isinstance(item,dict): continue
        names=[str(item.get(k,'')) for k in ('name','item','product','title','sku','id','display_name')]
        if any(n and n.lower() in low for n in names): found=item; break
    if not found:
        return {'reply':'요청하신 품목은 현재 재고가 없습니다. 결제서와 예약을 만들지 않았습니다.','state':'completed'}
    sku=str(found.get('sku',found.get('id','')))
    if not sku:return {'reply':'요청 품목의 SKU를 확인하지 못했습니다. 결제서와 예약을 만들지 않았습니다.','state':'completed'}
    now=int(time.time()); old=locks.get(sku)
    if isinstance(old,dict) and now-int(old.get('time',now))<10800:
        return {'reply':'죄송합니다. 해당 상품은 잠시 예약 중입니다.','state':'completed'}
    prices=load('prices.json',{}); v=prices.get(sku,found.get('price',5644))
    price=int(v.get('price',v.get('median',found.get('price',5644))) if isinstance(v,dict) else v)
    jwt=kit.sign_jwt({'sku':sku,'quantity':1,'price':price,'shop':kit.shop_url,'ts':now},'shop')
    if not jwt:return {'reply':'죄송합니다. 공식 결제서 생성에 실패해 예약하지 않았습니다.','state':'completed'}
    locks[sku]={'time':now,'customer':args.get('claimed_from','')}
    with open(path,'w',encoding='utf-8') as f:json.dump(locks,f,ensure_ascii=False)
    name=found.get('name',found.get('item',sku)); grade=found.get('grade','미확인'); cert=found.get('certificate_grade',found.get('certificate','미확인')); expiry=found.get('expires_at',found.get('expiry','미확인'))
    return {'reply':f'{name} {price}크레딧입니다. 등급 {grade}, 인증서 등급 {cert}, 잔여시간 {expiry} (측정 기준)입니다. 미확인 조건은 별도 확인이 필요합니다. 공식 서명 결제서를 보냅니다.','data':{'checkout_jwt':jwt,'sku':sku,'price':price},'state':'completed'}
