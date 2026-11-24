import httpx

def run(args, kit):
    r=httpx.get(kit.market+'/api/ledger',timeout=20)
    data=r.json()
    terms=[str(args.get(k,'')) for k in ('tx_hash','checkout_id','unit','sku') if args.get(k)]
    hits=[]
    for e in data if isinstance(data,list) else []:
        s=str(e)
        if any(t.lower() in s.lower() for t in terms): hits.append(e)
    return {'count':len(hits),'matches':hits}
