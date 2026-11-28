import httpx,json,glob,re,os

def run(args,kit):
 r=httpx.get(kit.market+'/api/inventory',headers={'authorization':'Bearer '+kit.token('shop')},timeout=20); r.raise_for_status(); units=r.json().get('units',[])
 issued=set()
 for f in glob.glob('logs/*.jsonl'):
  for line in open(f,encoding='utf8'):
   try: o=json.loads(line)
   except: continue
   if o.get('action')=='make_checkout' and 'eyJhbGciOiJFSVAxOTEiLCJ0eXAiOiJKV1Q' in line:
    u=o.get('args',{}).get('unit')
    if u: issued.add(u)
 card=open('card.json',encoding='utf8').read() if os.path.exists('card.json') else ''
 groups={}
 for u in units:
  key=(u['sku'],u['name'],u['grade']); g=groups.setdefault(key,{'sku':key[0],'name':key[1],'grade':key[2],'count':0,'issued':0,'card_mentioned':key[0] in card or key[1] in card,'units':[]})
  g['count']+=1; g['issued']+=u['unit'] in issued; g['units'].append({'unit':u['unit'],'cost':u['cost'],'expires_at':u.get('expires_at'),'issued':u['unit'] in issued})
 near=sorted([{'unit':u['unit'],'name':u['name'],'grade':u['grade'],'expires_at':u['expires_at'],'issued':u['unit'] in issued} for u in units if u.get('expires_at')],key=lambda x:x['expires_at'])[:15]
 return {'total':len(units),'issued_history':sum(u['unit'] in issued for u in units),'not_mentioned_units':sum(not (u['sku'] in card or u['name'] in card) for u in units),'near':near,'groups':list(groups.values())}
