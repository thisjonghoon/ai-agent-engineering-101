import json, os, re, time, httpx

def read(p, default):
    try:
        with open(p, encoding='utf-8') as f: return json.load(f)
    except Exception: return default

def run(args, kit):
    text=args.get('text',''); low=text.lower()
    card=read('card.json',{}); prices=read('prices.json',{})
    raw=card.get('stock', card.get('inventory', []))
    if isinstance(raw,dict): raw=[dict(v, sku=k) if isinstance(v,dict) else {'sku':k,'quantity':v} for k,v in raw.items()]
    held=read('archive/gen1-20261128/cutover.json',{})
    held_ids=set(held.get('held',held.get('units',[]))) if isinstance(held,dict) else set(held if isinstance(held,list) else [])
    locks=read('checkout_locks.json',{})
    now=time.time(); items=[]
    for z in raw:
        if not isinstance(z,dict): continue
        sku=str(z.get('sku',z.get('id',z.get('item','')))); q=float(z.get('quantity',z.get('available',0)) or 0)
        if q<=0 or sku in held_ids or (sku in locks and now-float(locks[sku].get('time',0))<10800): continue
        items.append((z,sku))
    if not items: return {'reply':'현재 판매 가능한 재고가 없습니다. held 재고와 예약 상태는 판매하지 않습니다.','state':'completed'}
    gm=re.search(r'(?:grade|등급)\\s*[:=]?\\s*([a-z0-9가-힣+-]+)',low)
    def match(z):
        s=json.dumps(z,ensure_ascii=False).lower()
        return not gm or gm.group(1) in s
    items=[v for v in items if match(v[0])]
    if not items: return {'reply':'요청하신 등급의 재고가 없습니다. 조건을 완화하면 확인해 드리겠습니다.','state':'completed'}
    def vals(z,sku):
        name=z.get('item',z.get('name',sku)); grade=z.get('grade','미측정'); qty=z.get('quantity',z.get('available',0)); left=z.get('time_left',z.get('expires_in','미측정')); cert=z.get('certificate_grade','미측정'); price=z.get('price',prices.get(sku,prices.get(name,'문의')))
        return name,grade,qty,left,cert,price
    buy=any(w in low for w in ('buy','purchase','checkout','구매','살게','사고','주문'))
    if not buy:
        out=[]
        for z,sku in items[:8]:
            n,g,q,l,c,p=vals(z,sku); out.append(f'{n}: {g}등급, {q}개, {p}크레딧, 잔여 {l}, 인증서 {c}')
        return {'reply':'현재 재고입니다. '+' / '.join(out)+' 확인하지 못한 조건은 말씀해 주세요.','state':'completed'}
    z,sku=items[0]; n,g,q,l,c,p=vals(z,sku)
    if not isinstance(p,(int,float)): return {'reply':f'{n} 재고는 있지만 가격표가 없어 결제할 수 없습니다. 등급 {g}, 잔여 {l}, 인증서 {c}입니다.','state':'completed'}
    locks[sku]={'time':int(now),'customer':args.get('claimed_from',''),'item':n}
    with open('checkout_locks.json','w',encoding='utf-8') as f: json.dump(locks,f,ensure_ascii=False)
    try:
        receipt={'sku':sku,'quantity':1,'price':int(p),'shop':kit.shop_url,'ts':int(now)}
        signed=kit.sign_jwt(receipt,'shop')
        r=httpx.post(kit.shop_url.rstrip('/')+'/checkout_sessions',json={'line_items':[{'id':sku,'quantity':1}],'receipt':signed,'acceptable':[sku]},timeout=8)
        body=r.json(); jwt=body.get('checkout_jwt') or body.get('checkout',{}).get('checkout_jwt')
        if jwt: return {'reply':f'{n} {g}등급, {p}크레딧, 잔여 {l}입니다. 인증서 등급은 {c}이며 체크아웃 토큰을 보냅니다.','data':{'checkout_jwt':jwt,'sku':sku,'grade':g,'time_left':l,'certificate_grade':c},'state':'completed'}
    except Exception: pass
    return {'reply':f'{n} {g}등급 재고를 예약했지만 체크아웃 생성에 실패했습니다. 가격 {p}크레딧, 잔여 {l}, 인증서 {c}입니다.','state':'completed'}
