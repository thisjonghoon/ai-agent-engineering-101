import httpx

def run(args, kit):
    sku=args.get('sku'); qty=int(args.get('qty',1)); maximum=args.get('max_total')
    if not sku or qty<1 or qty>20 or maximum is None: return {'error':'need sku, qty 1-20, max_total'}
    h={'authorization':'Bearer '+kit.token('shop')}; url=kit.market+'/api/supply'
    r=httpx.post(url,json={'sku':sku,'qty':qty},headers=h,timeout=30)
    try: q=r.json()
    except Exception: return {'status':r.status_code,'text':r.text[:500]}
    if r.status_code!=402: return {'status':r.status_code,'json':q}
    if args.get('dry'): return {'dry':True,'quote':q}
    units=q.get('units') or []
    if q.get('total') is None or q['total']>float(maximum): return {'aborted':'total above max_total','quote':q}
    if len(units)!=qty or any(u.get('sku')!=sku for u in units): return {'aborted':'units mismatch','quote':q}
    if args.get('grade') and any(u.get('grade')!=args['grade'] for u in units): return {'aborted':'grade mismatch','quote':q}
    if args.get('min_expires_at') and any(not u.get('expires_at') or u['expires_at']<args['min_expires_at'] for u in units): return {'aborted':'expiry mismatch','quote':q}
    pay=q['pay']; tx=kit.pay(pay['to'],int(pay['wei']),pay.get('data') or '0x',role='shop')
    r2=httpx.post(url,json={'quote':q.get('quote'),'tx_hash':tx},headers=h,timeout=60)
    try: res=r2.json()
    except Exception: res=r2.text[:500]
    return {'quote':q,'tx_hash':tx,'status':r2.status_code,'result':res}
