import httpx

def run(args, kit):
    method = (args.get('method') or 'GET').upper()
    path = args.get('path') or ''
    mx = int(args.get('max', 20000))
    if not path.startswith('/api/'):
        return {'error': 'path must start with /api/'}
    headers = {'authorization': 'Bearer ' + kit.token('shop')}
    url = kit.market + path
    if method == 'POST':
        r = httpx.post(url, json=args.get('body') or {}, headers=headers, timeout=30)
    else:
        r = httpx.get(url, headers=headers, timeout=30)
    try:
        return {'status': r.status_code, 'json': r.json()}
    except Exception:
        return {'status': r.status_code, 'text': r.text[:mx]}
