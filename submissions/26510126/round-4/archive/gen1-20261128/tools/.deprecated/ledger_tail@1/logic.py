import httpx

def run(args,kit):
 r=httpx.get(kit.market.rstrip('/')+'/api/ledger',timeout=20); r.raise_for_status(); x=r.json()
 rows=x if isinstance(x,list) else x.get('entries',[]) if isinstance(x,dict) else []
 return {'count':len(rows),'tail':rows[-int(args.get('n',20)):]}