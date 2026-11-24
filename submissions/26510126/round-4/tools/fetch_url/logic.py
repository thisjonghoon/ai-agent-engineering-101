import httpx
from urllib.parse import urlparse

def select_items(items, keywords, limit):
    return [x for x in items if isinstance(x, dict) and any(k in str(x.get('name', '')) or k in str(x.get('sku', '')) for k in keywords)][:limit]

def run(args, kit):
    url = args.get('url', '')
    p = urlparse(url)
    if p.scheme != 'https' or p.netloc != urlparse(kit.market).netloc:
        return {'error': 'market HTTPS URLs only'}
    r = httpx.get(url, timeout=25, follow_redirects=False)
    keywords = args.get('keywords')
    if keywords:
        obj = r.json()
        items = obj
        if isinstance(obj, dict):
            key = args.get('list_key')
            if key:
                items = obj.get(key)
            else:
                items = next((obj[k] for k in ('agents', 'items', 'shops', 'units') if isinstance(obj.get(k), list)), None)
        if not isinstance(items, list):
            return {'status': r.status_code, 'error': 'no JSON list found', 'keys': list(obj) if isinstance(obj, dict) else []}
        return {'status': r.status_code, 'items': select_items(items, keywords, min(100, max(1, int(args.get('limit', 30)))))}
    return {'status': r.status_code, 'text': r.text[:min(50000, max(1, int(args.get('max', 20000))))]}
