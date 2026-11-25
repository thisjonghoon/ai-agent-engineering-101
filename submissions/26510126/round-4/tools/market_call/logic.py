import httpx

def run(args, kit):
    method=(args.get('method') or 'GET').upper()
    path=args.get('path') or ''
    if not path.startswith('/api/'):
        return {'error':'path must start with /api/'}
    headers={'authorization':'Bearer '+kit.token('shop')}
    if method=='POST':
        r=httpx.post(kit.market+path,json=args.get('body') or {},headers=headers,timeout=30)
    else:
        r=httpx.get(kit.market+path,headers=headers,timeout=30)
    try:
        data=r.json()
        keywords=args.get('keywords')
        if keywords and isinstance(data,dict) and isinstance(data.get('units'),list):
            data['units']=[u for u in data['units'] if any(str(k).lower() in (str(u.get('name',''))+' '+str(u.get('category',''))+' '+str(u.get('sku',''))).lower() for k in keywords)]
        return {'status':r.status_code,'json':data}
    except ValueError:
        return {'status':r.status_code,'text':r.text[:int(args.get('max',20000))]}
