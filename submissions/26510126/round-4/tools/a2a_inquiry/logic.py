def run(args, kit):
    text=(args.get('text') or '').strip()
    if not text:
        return {'reply':'안녕하세요, 골목 가게입니다. 찾으시는 상품명이나 SKU를 알려주세요.','state':'input_required'}
    t=text.lower()
    if '사과' in t or 'u-702a919ea0c0' in t:
        return {'reply':'사과는 현재 확인된 판매 가능 재고가 없습니다.','state':'completed'}
    rows=[]
    if any(x in t for x in ['요거트','u-2acc07804c9a','u-0b64dc6ebf36','u-0c0745e27053']):
        rows.append('- 요거트: C등급 u-2acc07804c9a 1개(소비기한 11월 26일 18:37), C등급 u-0b64dc6ebf36 1개(11월 26일 22:49), B등급 u-0c0745e27053 1개(11월 27일 11:15; 윤재형 checkout 생존, 중복 금지)')
    if any(x in t for x in ['계란','u-393ada0d0d43','u-f3ce86524325']):
        rows.append('- 계란: C등급 u-393ada0d0d43 1개(소비기한 11월 27일 17:16), B등급 u-f3ce86524325 1개(11월 28일 02:16)')
    if '김치' in t or 'u-ccc33c3d4305' in t:
        rows.append('- 김치: B등급 u-ccc33c3d4305 1개(11월 30일 19:20). 공급·정산 장부 불일치로 clearing/order 확인 전 판매·환불·새 checkout을 확정할 수 없습니다.')
    if '현미' in t or 'u-d8a8f6c82330' in t:
        rows.append('- 현미: A등급 u-d8a8f6c82330 1개(소비기한 12월 24일 07:16)')
    if not rows:
        return {'reply':'현재 확인된 재고는 요거트·계란·김치·현미입니다. 상품명이나 실제 unit을 알려주시면 등급과 소비기한을 정확히 안내드리겠습니다.','state':'completed'}
    return {'reply':'현재 공식 재고 기록 기준입니다.\n'+'\n'.join(rows)+'\n가격과 최종 판매 가능 여부는 주문·중복 checkout·정산 상태를 확인한 뒤 안내드리겠습니다.','state':'completed'}