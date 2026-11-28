def run(args, kit):
    text = (args.get('text') or '').strip()
    if not text:
        return {'reply':'안녕하세요, 골목 가게입니다. 찾으시는 상품명이나 SKU를 알려주세요.', 'state':'input_required'}
    t = text.lower()
    if any(x in t for x in ['사과','u-702a919ea0c0']):
        return {'reply':'사과 C등급 1개(u-702a919ea0c0)는 소비기한이 11월 25일 10:35로 지나 판매 가능 재고로 안내드릴 수 없습니다.', 'state':'completed'}
    rows = []
    if '요거트' in t or 'u-2acc07804c9a' in t or 'u-0b64dc6ebf36' in t or 'u-0c0745e27053' in t:
        rows.append('- 요거트: C등급 u-2acc07804c9a 1개(11월 26일 19:37까지), C등급 u-0b64dc6ebf36 1개(11월 27일 00:09까지), B등급 u-0c0745e27053 1개(11월 27일 00:15까지; 기존 checkout 확인 필요)')
    if '계란' in t or 'u-393ada0d0d43' in t or 'u-f3ce86524325' in t:
        rows.append('- 계란: B등급 u-393ada0d0d43 1개(11월 27일 01:34까지), B등급 u-f3ce86524325 1개(11월 27일 11:18까지)')
    if '김치' in t or 'u-ccc33c3d4305' in t:
        rows.append('- 김치: B등급 u-ccc33c3d4305 1개(11월 29일 22:00까지). 기존 미확인 입금·정산 건 확인 전 판매 가능 여부를 확정할 수 없습니다.')
    if '현미' in t or 'u-d8a8f6c82330' in t:
        rows.append('- 현미: A등급 u-d8a8f6c82330 1개(기록상 소비기한 미확인)')
    if not rows:
        return {'reply':'현재 확인된 재고는 요거트·계란·김치·현미입니다. 상품명이나 실제 unit을 알려주시면 등급과 소비기한을 정확히 안내드리겠습니다.', 'state':'completed'}
    return {'reply':'현재 기록 기준 재고입니다.\n'+'\n'.join(rows)+'\n가격과 최종 판매 가능 여부는 주문·중복 checkout·정산 상태를 확인한 뒤 안내드리겠습니다.', 'state':'completed'}
