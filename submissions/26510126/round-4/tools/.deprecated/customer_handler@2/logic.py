import json, os, re, time, httpx

def load(p,d):
    try:
        with open(p,encoding='utf-8') as f:return json.load(f)
    except Exception:return d

def run(args,kit):
    text=args.get('text',''); low=text.lower(); inv=load('card.json',{}); prices=load('prices.json',{})
    raw=inv.get('stock',inv.get('inventory',inv.get('items',[])))
    if isinstance(raw,dict): raw=[dict(v,item=k) if isinstance(v,dict) else {'item':k,'quantity':v} for k,v in raw.items()]
    avail=[x for x in raw if isinstance(x,dict) and float(x.get('quantity',x.get('available',1)) or 0)>0]
    def info(x):
        n=x.get('item',x.get('name','상품')); sku=x.get('sku',x.get('id',n)); g=x.get('grade','미확인'); q=x.get('quantity',x.get('available',1)); l=x.get('time_left',x.get('expires_in','미측정')); p=x.get('price',prices.get(n,'문의'))
        return n,sku,g,q,l,p
    if not avail:return {'reply':'현재 확인된 판매 가능 재고가 없습니다.','state':'completed'}
    chosen=[]
    gm=re.search(r'(?:grade|등급)\s*[:=]?\s*([a-z0-9가-힣+-]+)',low)
    for x in avail:
        s=json.dumps(x,ensure_ascii=False).lower()
        if not gm or gm.group(1) in s: chosen.append(x)
    if not chosen: return {'reply':'요청하신 등급의 재고가 없습니다. 현재 조건을 완화하시면 확인해 드리겠습니다.','state':'completed'}
    x=chosen[0]; n,sku,g,q,l,p=info(x)
    buy=any(w in low for w in ['buy','purchase','checkout','구매','살게','사고','주문'])
    if buy:
        locks=load('checkout_locks.json',{}); key=str(x.get('id',sku))
        if key in locks and time.time()-locks[key].get('time',0)<10800:return {'reply':'죄송하지만 해당 상품은 이미 예약 중입니다.','state':'completed'}
        locks[key]={'time':int(time.time()),'customer':args.get('claimed_from',''),'item':n}
        with open('checkout_locks.json','w',encoding='utf-8') as f:json.dump(locks,f,ensure_ascii=False)
        receipt={'sku':sku,'quantity':1,'price':p,'shop':kit.shop_url,'ts':int(time.time())}
        try:
            signed=kit.sign_jwt(receipt,'shop')
            r=httpx.post(kit.shop_url.rstrip('/')+'/checkout_sessions',json={'line_items':[{'id':sku,'quantity':1}],'receipt':signed,'acceptable':[sku]},timeout=8)
            body=r.json(); jwt=body.get('checkout_jwt') or body.get('checkout',{}).get('checkout_jwt')
            if jwt:return {'reply':f'{n} {g}등급, 가격 {p}크레딧, 잔여 {l}입니다. 체크아웃 토큰을 보냅니다. 인증서 등급은 {x.get("certificate_grade","미확인")}입니다.','data':{'checkout_jwt':jwt,'sku':sku,'grade':g,'time_left':l},'state':'completed'}
        except Exception: pass
        return {'reply':f'{n} {g}등급 재고는 확인했지만 체크아웃 세션 생성에 실패했습니다. 가격 {p}크레딧, 잔여 {l}입니다.','state':'completed'}
    lines=[]
    for y in chosen[:8]:
        a,b,c,d,e,f=info(y);lines.append(f'{a}: {c}등급, {d}개, {f}크레딧, 잔여 {e}, 인증서 {y.get("certificate_grade","미확인")}')
    return {'reply':'현재 재고입니다. '+' / '.join(lines)+' 확인하지 못한 조건은 말씀해 주세요.','state':'completed'}
