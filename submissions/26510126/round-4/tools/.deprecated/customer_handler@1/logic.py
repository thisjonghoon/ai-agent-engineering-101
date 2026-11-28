import json, os, re, time
import httpx

def load(path, default):
    try:
        with open(path, encoding='utf-8') as f: return json.load(f)
    except Exception: return default

def run(args, kit):
    text=args.get('text','')
    inv=load('card.json',{})
    prices=load('prices.json',{})
    # support common card layouts
    items=inv.get('stock', inv.get('inventory', inv.get('items', [])))
    if isinstance(items,dict):
        items=[dict(v, item=k) if isinstance(v,dict) else {'item':k,'quantity':v} for k,v in items.items()]
    lower=text.lower()
    buy=any(x in lower for x in ['buy','purchase','checkout','구매','살게','사고','주문'])
    terms=[]
    for k in ['grade','등급','size','사이즈','fresh','신선','expiry','expire','유통','시간']:
        if k in lower: terms.append(k)
    def desc(x):
        name=x.get('item',x.get('name','상품')); grade=x.get('grade','미확인'); qty=x.get('quantity',x.get('available',1)); left=x.get('time_left',x.get('expires_in','미측정'))
        p=x.get('price',prices.get(name,prices.get(str(name),'문의')))
        return name,grade,qty,left,p
    avail=[x for x in items if isinstance(x,dict) and float(x.get('quantity',x.get('available',1)) or 0)>0]
    if not avail:
        return {'reply':'현재 확인된 판매 가능 재고가 없습니다. 필요한 품목과 조건을 알려주시면 확인해 보겠습니다.','state':'completed'}
    # simple condition filtering
    chosen=[]
    for x in avail:
        s=json.dumps(x,ensure_ascii=False).lower()
        ok=True
        m=re.search(r'(?:grade|등급)\s*[:=]?\s*([a-z0-9가-힣+-]+)',lower)
        if m and m.group(1) not in s: ok=False
        if ok: chosen.append(x)
    if buy and chosen:
        x=chosen[0]; name,grade,qty,left,p=desc(x)
        locks=load('checkout_locks.json',{})
        key=str(x.get('id',name))
        locks[key]={'time':int(time.time()),'customer':args.get('claimed_from',''),'item':name}
        with open('checkout_locks.json','w',encoding='utf-8') as f: json.dump(locks,f,ensure_ascii=False)
        return {'reply':f'{name} {grade} 재고가 있습니다. 가격 {p}크레딧, 측정된 잔여 시간 {left}입니다. 예약 확인 후 체크아웃을 진행해 주세요. 인증서 등급은 {x.get("certificate_grade","확인하지 않음")}입니다.','data':{'item':name,'grade':grade,'price':p,'time_left':left,'certificate_grade':x.get('certificate_grade')},'state':'completed'}
    lines=[]
    for x in chosen[:8]:
        n,g,q,l,p=desc(x); lines.append(f'{n}: {g}등급, {q}개, {p}크레딧, 잔여 {l}; 인증서 등급 {x.get("certificate_grade","미확인")}')
    return {'reply':'현재 재고입니다. '+ ' / '.join(lines)+' 문의하신 조건 중 확인하지 못한 항목은 별도로 말씀해 주세요.','state':'completed'}
