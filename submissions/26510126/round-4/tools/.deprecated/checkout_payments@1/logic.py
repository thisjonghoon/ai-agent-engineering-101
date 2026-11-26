import json,re,glob,hashlib,base64,concurrent.futures,time
import httpx

def run(args,kit):
 units=args.get('units',[]); found={u:{} for u in units}
 for f in glob.glob('logs/*.jsonl'):
  for line in open(f,encoding='utf8'):
   try: o=json.loads(line)
   except: continue
   if o.get('action')!='make_checkout': continue
   u=o.get('args',{}).get('unit')
   if u not in found: continue
   for tok in re.findall(r'eyJhbGciOiJFSVAxOTEiLCJ0eXAiOiJKV1QifQ\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+',line):
    found[u]['0x'+hashlib.sha256(tok.encode()).hexdigest()] = o.get('ts',0)
 if kit.testing: return {'hashes':{u:list(x) for u,x in found.items()},'complete':False}
 c=httpx.Client(timeout=15)
 def rpc(method,params):
  r=c.post('https://rpc-testnet.maroo.io',json={'jsonrpc':'2.0','id':1,'method':method,'params':params}); r.raise_for_status(); j=r.json()
  if 'error' in j: raise RuntimeError(str(j['error']))
  return j['result']
 latest=int(rpc('eth_blockNumber',[]),16)
 def block(n,full=False): return rpc('eth_getBlockByNumber',[hex(n),full])
 start=args.get('start') or min((t for d in found.values() for t in d.values()),default=int(time.time()))-60
 lo,hi=0,latest
 while lo<hi:
  mid=(lo+hi)//2; b=block(mid)
  if int(b['timestamp'],16)<start: lo=mid+1
  else: hi=mid
 begin=lo; end=min(latest,int(args.get('end',latest))); limit=min(int(args.get('max_blocks',2500)),10000); stop=min(end,begin+limit-1)
 targets={h:u for u,d in found.items() for h in d}; wallet=kit.address('shop').lower(); matches=[]; errors=[]
 def scan(n):
  try:
   b=block(n,True); out=[]
   for t in b.get('transactions',[]):
    if isinstance(t,dict) and (t.get('to') or '').lower()==wallet and t.get('input','').lower() in targets:
     out.append({'unit':targets[t['input'].lower()],'hash':t['hash'],'from':t['from'],'value':t['value'],'block':n,'timestamp':int(b['timestamp'],16)})
   return out,None
  except Exception as e: return [],str(e)
 with concurrent.futures.ThreadPoolExecutor(max_workers=16) as ex:
  for n,(rows,err) in zip(range(begin,stop+1),ex.map(scan,range(begin,stop+1))):
   matches+=rows
   if err: errors.append({'block':n,'error':err})
 return {'hashes':{u:list(d) for u,d in found.items()},'start_block':begin,'end_block':stop,'latest':latest,'complete':stop==end and not errors and all(found.values()),'errors':errors[:20],'matches':matches}
