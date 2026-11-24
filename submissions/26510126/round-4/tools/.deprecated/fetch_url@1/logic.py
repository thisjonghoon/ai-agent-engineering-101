import httpx

def run(args, kit):
    url = args.get('url')
    mx = int(args.get('max', 20000))
    if not url or not url.startswith(kit.market):
        return {'error': 'url must start with ' + kit.market}
    r = httpx.get(url, timeout=25, follow_redirects=True)
    return {'status': r.status_code, 'text': r.text[:mx]}
