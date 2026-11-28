def run(args, kit):
    text = (args.get('text') or '').strip()
    if not text:
        return {'reply':'안녕하세요, 골목 가게입니다. 찾으시는 상품명이나 SKU를 알려주세요.', 'state':'input_required'}
    items = [
        ('사과','G13e9d565','1개, C등급, 11월 25일 10:35까지'),
        ('요거트','G5e1cf31d','3개: C등급 2개(11월 26일 19:37까지, 11월 27일 00:09까지), B등급 1개(11월 27일 00:15까지)'),
        ('계란','G02595b69','2개, B등급'),
        ('김치','G02f9f99c','1개, B등급, 11월 29일 22:00까지'),
        ('현미','G2b27288a','1개, A등급')]
    found = [x for x in items if x[0] in text or x[1].lower() in text.lower()]
    if not found:
        return {'reply':'현재 사과·요거트·계란·김치·현미 재고가 있습니다. 상품명이나 SKU를 알려주시면 등급과 소비기한을 정확히 안내드릴게요.', 'state':'completed'}
    lines = ['현재 확인된 재고입니다.']
    for name, sku, detail in found:
        lines.append(f'- {name} ({sku}): {detail}')
    lines.append('가격과 판매 가능 여부는 주문 시 중복 주문·정산 상태를 확인한 뒤 안내드리겠습니다.')
    return {'reply':'\n'.join(lines), 'state':'completed'}
