import httpx,json,glob,os,time

LIVE=10800   # goal: a checkout is live for 3 hours; after that make_checkout voids it (no settle on the ledger) and sells again

def last_issued(units):
 """unit -> ts of its latest checkout, from react.jsonl (and other logs) and auto_checkout.jsonl."""
 last={}
 for f in glob.glob('logs/*.jsonl'):
  for line in open(f,encoding='utf8'):
   if 'eyJhbGciOiJFSVAxOTEiLCJ0eXAiOiJKV1Q' not in line or '"make_checkout"' not in line: continue
   try: o=json.loads(line)
   except Exception: continue
   u=o.get('args',{}).get('unit')
   if o.get('action')=='make_checkout' and u in units: last[u]=max(last.get(u,0),int(o.get('ts',0)))
 if os.path.exists('auto_checkout.jsonl'):
  for line in open('auto_checkout.jsonl',encoding='utf8'):
   try: a=json.loads(line)
   except Exception: continue
   if a.get('unit') in units: last[a['unit']]=max(last.get(a['unit'],0),int(a.get('ts',0)))
 return last

def run(args,kit):
 if kit.testing: units=args.get('_units',[]); last=args.get('_last',{}); card=''
 else:
  r=httpx.get(kit.market+'/api/inventory',headers={'authorization':'Bearer '+kit.token('shop')},timeout=20); r.raise_for_status(); units=r.json().get('units',[])
  last=last_issued({u['unit'] for u in units})
  card=open('card.json',encoding='utf8').read() if os.path.exists('card.json') else ''
 now=time.time()
 def state(u):
  t=last.get(u['unit'])
  if not t: return 'never_issued'
  return 'live_checkout' if now<t+LIVE else 'voidable'   # voidable: make_checkout re-sells it after the ledger check
 groups={}
 for u in units:
  key=(u['sku'],u['name'],u['grade']); s=state(u)
  g=groups.setdefault(key,{'sku':key[0],'name':key[1],'grade':key[2],'count':0,'sellable_now':0,'live_checkout':0,'card_mentioned':key[0] in card or key[1] in card,'units':[]})
  g['count']+=1; g['sellable_now']+=s!='live_checkout'; g['live_checkout']+=s=='live_checkout'
  g['units'].append({'unit':u['unit'],'cost':u.get('cost'),'expires_at':u.get('expires_at'),'state':s,'live_until':last[u['unit']]+LIVE if s=='live_checkout' else None})
 near=sorted([{'unit':u['unit'],'name':u['name'],'grade':u['grade'],'expires_at':u['expires_at'],'state':state(u)} for u in units if u.get('expires_at')],key=lambda x:x['expires_at'])[:15]
 count=lambda s: sum(state(u)==s for u in units)
 return {'total':len(units),'never_issued':count('never_issued'),'voidable':count('voidable'),'live_checkout':count('live_checkout'),
         'sellable_now':len(units)-count('live_checkout'),'not_mentioned_units':sum(not (u['sku'] in card or u['name'] in card) for u in units),
         'note':'voidable = last checkout over 3 hours ago; make_checkout voids it when the ledger has no settle and issues a new one',
         'near':near,'groups':list(groups.values())}
