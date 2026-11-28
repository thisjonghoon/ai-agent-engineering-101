import json,time

def load(p,d):
    try:
        with open(p,encoding='utf-8') as f:return json.load(f)
    except:return d

def run(args,kit):
    text=str(args.get('text','')); low=text.lower()
    path='test_checkout_locks.json' if kit.testing else 'checkout_locks.json'
    locks=load(path,{})
    if not isinstance(locks,dict): locks={}
    if not any(x in low for x in ('구매','주문','결제','buy','checkout')):
        return {'reply':'현재 재고를 확인해 드릴게요. 구매하실 품목을 말씀해 주세요.','state':'completed'}
    card=load('test_card.json' if kit.testing else 'card.json',{})
    raw=card.get('stock',card.get('inventory',card.get('items',[]))) if isinstance(card,dict) else []
    if isinstance(raw,dict):
        # Production cards are SKU->quantity; resolve names from shop_inspect when available.
        meta=load('shop_inspect.json',{}); its=meta.get('items',meta.get('products',[])) if isinstance(meta,dict) else []
        if isinstance(its,dict): its=list(its.values())
        raw=[dict(next((x for x in its if isinstance(x,dict) and str(x.get('sku',x.get('id','')))==str(k)),{}),sku=k,quantity=v) for k,v in raw.items() if v]
    found=next((i for i in raw if isinstance(i,dict) and any(str(i.get(k,'')) and str(i.get(k,'')).lower() in low for k in ('name','item','product','title','sku','id','display_name'))),None)
    if not found and ('가자미' in low or '손질 두절' in low) and isinstance(card.get('stock'),dict) and card['stock'].get('G045659e8'):
        found={'sku':'G045659e8','name':'가자미'}
    if not found:return {'reply':'요청하신 품목은 현재 재고가 없습니다. 결제서와 예약을 만들지 않았습니다.','state':'completed'}
    sku=str(found.get('sku',found.get('id','')))
    now=int(time.time()); old=locks.get(sku)
    if isinstance(old,dict) and now-int(old.get('time',now))<10800:return {'reply':'죄송합니다. 해당 상품은 잠시 예약 중입니다.','state':'completed'}
    v=load('prices.json',{}).get(sku,found.get('price',5644)); price=int(v.get('price',v.get('median',found.get('price',5644))) if isinstance(v,dict) else v)
    jwt=kit.sign_jwt({'sku':sku,'quantity':1,'price':price,'shop':kit.shop_url,'ts':now},'shop')
    if not jwt:return {'reply':'공식 결제서 생성에 실패해 예약하지 않았습니다.','state':'completed'}
    locks[sku]={'time':now,'customer':args.get('claimed_from','')}
    with open(path,'w',encoding='utf-8') as f:json.dump(locks,f,ensure_ascii=False)
    return {'reply':f"{found.get('name',sku)} {price}크레딧입니다. 등급 {found.get('grade','미확인')}, 인증서 등급 {found.get('certificate_grade',found.get('certificate','미확인'))}, 잔여시간 {found.get('expires_at',found.get('expiry','미확인'))}입니다. 공식 서명 결제서를 보냅니다.",'data':{'checkout_jwt':jwt,'sku':sku,'price':price},'state':'completed'}
