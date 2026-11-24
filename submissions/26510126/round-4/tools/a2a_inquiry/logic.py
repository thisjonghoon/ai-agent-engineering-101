def run(args, kit):
    text = (args.get('text') or '').strip()
    if not text:
        return {'reply': '안녕하세요, 골목 가게입니다. 찾으시는 상품명이나 SKU를 알려주세요.', 'state': 'input_required'}
    return {'defer': True}
