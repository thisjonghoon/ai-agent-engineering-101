import json,time,httpx,os
def run(args,kit):
 now=time.time(); live=[]; voidable=[]; never=[]
 try:
  if kit.testing: units=args.get('_units',[])
  else:
   r=httpx.get(kit.market+'/api/inventory',headers={'authorization':'Bearer '+kit.token('shop')},timeout=20); r.raise_for_status(); units=r.json().get('units',[])
 except Exception as e: return {'error':'inventory fetch failed','detail':str(e)}
 issued=set(); times={}
 for fn in ('logs/react.jsonl','auto_checkout.jsonl'):
  try:
   for line in open(fn,encoding='utf8'):
    try:
     x=json.loads(line); u=x.get('args',{}).get('unit') if 'react' in fn else x.get('unit'); t=x.get('ts',0)
     if u and t: issued.add(u); times[u]=max(times.get(u,0),int(t))
    except: pass
  except FileNotFoundError: pass
 for u in units:
  uid=u.get('unit');
  if uid not in issued: never.append(uid)
  elif now-times.get(uid,now)<10800: live.append(uid)
  else: voidable.append(uid)
 return {'total':len(units),'live_checkout':live,'voidable':voidable,'never_issued':never,'sellable_now':len(never)+len(voidable),'asof':now}
