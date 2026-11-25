import httpx, datetime

def run(args, kit):
    text=(args.get('text') or '').strip()
    if not text: return {'reply':'안녕하세요. 찾으시는 상품을 알려주세요.','state':'input_required'}
    if any(x in text for x in ['결제','checkout','체크아웃','구매','주문','사겠습니다','살게','번호','환불']): return {'defer':True}
    try:
        r=httpx.get(kit.market+'/api/inventory',headers={'authorization':'Bearer '+kit.token('shop')},timeout=12); r.raise_for_status(); units=r.json().get('units',[])
        words=['요거트','계란','김치','사과','생수','쌀','우유','두부','콩나물','취나물','쌈채소','시금치','부추']
        keys=[w for w in words if w in text]
        if not keys: return {'defer':True}
        matched=[u for u in units if any(w in u.get('name','') for w in keys) or u.get('sku','') in text or u.get('unit','') in text]
        if not matched: return {'reply':'문의하신 상품은 현재 재고 목록에서 확인되지 않습니다.','state':'completed'}
        lines=[]
        for u in matched[:15]:
            dt=datetime.datetime.fromtimestamp(float(u['expires_at']),datetime.timezone(datetime.timedelta(hours=9))).strftime('%m/%d %H:%M')
            lines.append(f"{u['name']} · {u['unit']} · {u['grade']}등급 · 기한 {dt}")
        return {'reply':'현재 재고 목록입니다. 예약 여부와 가격은 별도 확인이 필요합니다.\n'+'\n'.join(lines)+'\n구매 원하시면 상품과 unit을 말씀해 주세요.','state':'completed'}
    except Exception: return {'defer':True}
