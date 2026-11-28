import httpx

def run(args,kit):
 n=int(args.get('n',20))
 if n<0 or n>500: return {'error':'n must be 0-500'}
 if n==0: return {'count':0,'tail':[]}
 r=httpx.get(kit.market.rstrip('/')+'/api/ledger',params={'after':-1},timeout=20); r.raise_for_status(); x=r.json()
 rows=x if isinstance(x,list) else x.get('entries',[])
 if not rows: return {'count':0,'tail':[]}
 last=rows[-1]['seq']; start=max(0,last-n)
 r=httpx.get(kit.market.rstrip('/')+'/api/ledger',params={'after':start},timeout=20); r.raise_for_status(); x=r.json(); rows=x if isinstance(x,list) else x.get('entries',[])
 rows=[e for e in rows if e['seq']<=last]
 return {'count':len(rows),'tail':rows[-n:],'snapshot_last_seq':last}
