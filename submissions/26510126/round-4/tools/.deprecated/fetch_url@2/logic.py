import httpx
from urllib.parse import urlparse

def select_items(items, keywords, limit):
    return [x for x in items if isinstance(x, dict) and any(k in str(x.get('name', '')) or k in str(x.get('sku', '')) for k in keywords)][:limit]

def run(args, kit):
    url = args.get('url', '')
    if urlparse(url).scheme != 'https' or urlparse(url).netloc != urlparse(kit.market).netloc:
        return {'error': 'market HTTPS URLs only'}
    r = httpx.get(url, timeout=25, follow_redirects=False)
    keywords = args.get('keywords')
    if keywords:
        items = r.json()
        if not isinstance(items, list):
            return {'status': r.status_code, 'error': 'expected a JSON list'}
        return {'status': r.status_code, 'items': select_items(items, keywords, min(100, max(1, int(args.get('limit', 30)))))}
    return {'status': r.status_code, 'text': r.text[:min(50000, max(1, int(args.get('max', 20000))))]}
