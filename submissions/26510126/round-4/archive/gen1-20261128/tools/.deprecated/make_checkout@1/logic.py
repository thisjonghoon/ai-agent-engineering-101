import time, uuid

def run(args, kit):
    sku = args.get('sku')
    unit = args.get('unit')
    price = args.get('price')
    cost = args.get('cost')
    if not sku or not unit or price is None or cost is None:
        return {'error': 'need sku, unit, price, cost'}
    price = int(price)
    cost = int(cost)
    fee = price // 100
    shop_gets = price - fee - 210
    if shop_gets < cost and not args.get('allow_loss'):
        return {'error': 'price below cost plus fees', 'shop_gets': shop_gets, 'cost': cost}
    wh = int(args.get('warranty_hours', 0))
    if wh < 0 or wh > 72:
        return {'error': 'warranty_hours 0-72'}
    task = args.get('task') or ('t-' + uuid.uuid4().hex[:12])
    payload = {
        'id': 'co-' + uuid.uuid4().hex[:12],
        'shop': kit.name,
        'shop_url': kit.shop_url,
        'item': sku,
        'price': price,
        'task': task,
        'currency': 'credits',
        'iat': int(time.time()),
        'unit': unit,
        'warranty_hours': wh,
    }
    if args.get('cert'):
        payload['cert'] = args['cert']
    if args.get('claim') in ('A', 'B', 'C'):
        payload['claim'] = args['claim']
    jwt = kit.sign_jwt(payload, 'shop')
    return {'checkout_jwt': jwt, 'payload': payload, 'shop_gets': shop_gets}
