import httpx

def run(args, kit):
    url=args.get('url','')
    if not url.startswith('https://market.ourolabs.ai/'):
        return {'error':'URL not allowed'}
    r=httpx.get(url,timeout=20)
    text=r.text
    return {'status':r.status_code,'content_type':r.headers.get('content-type',''),'text':text[:int(args.get('max_chars',30000))]}
