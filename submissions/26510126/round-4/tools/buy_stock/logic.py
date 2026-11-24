import httpx

def run(args, kit):
    sku = args.get('sku')
    qty = int(args.get('qty', 1))
    max_total = args.get('max_total')
    if not sku or qty < 1 or qty > 20 or max_total is None:
        return {'error': 'need sku, qty 1-20, max_total'}
    h = {'authorization': 'Bearer ' + kit.token('shop')}
    url = kit.market + '/api/supply'
    r = httpx.post(url, json={'sku': sku, 'qty': qty}, headers=h, timeout=30)
    try:
        q = r.json()
    except Exception:
        return {'status': r.status_code, 'text': r.text[:500]}
    if r.status_code != 402:
        return {'status': r.status_code, 'json': q}
    if args.get('dry'):
        return {'dry': True, 'quote': q}
    total = q.get('total')
    if total is None or total > float(max_total):
        return {'aborted': 'total above max_total', 'quote': q}
    pay = q.get('pay') or {}
    data = pay.get('data') or '0x'
    tx = kit.pay(pay['to'], int(pay['wei']), data, role='shop')
    r2 = httpx.post(url, json={'quote': q.get('quote'), 'tx_hash': tx}, headers=h, timeout=60)
    try:
        res = r2.json()
    except Exception:
        res = r2.text[:500]
    return {'quote_total': total, 'tx_hash': tx, 'status': r2.status_code, 'result': res}
