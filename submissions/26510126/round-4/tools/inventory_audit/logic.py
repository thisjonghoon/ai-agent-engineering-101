import json,time,httpx

def _issued_from_logs():
    issued={}
    for fn in ('logs/react.jsonl','auto_checkout.jsonl'):
        try:
            with open(fn,encoding='utf8') as f:
                for line in f:
                    try:
                        x=json.loads(line)
                        if 'react' in fn:
                            if x.get('action')!='make_checkout': continue
                            o=x.get('observation',{})
                            if isinstance(o,str):
                                try:o=json.loads(o)
                                except:continue
                            r=o.get('result',{}) if isinstance(o,dict) else {}
                            if not r.get('checkout_jwt'): continue
                            p=r.get('payload') or {}
                            u=p.get('unit') or x.get('args',{}).get('unit')
                            t=x.get('ts',0)
                        else:
                            if not x.get('checkout_jwt'): continue
                            u=x.get('unit') or (x.get('payload') or {}).get('unit')
                            t=x.get('ts',0)
                        if u and t:
                            issued[u]=max(float(t),float(issued.get(u,0)))
                    except Exception: pass
        except FileNotFoundError: pass
    return issued

def run(args,kit):
    now=time.time()
    if kit.testing: units=args.get('_units',[])
    else:
        try:
            r=httpx.get(kit.market+'/api/inventory',headers={'authorization':'Bearer '+kit.token('shop')},timeout=20); r.raise_for_status(); units=r.json().get('units',[])
        except Exception as e:return {'error':'inventory fetch failed','detail':str(e)}
    issued=_issued_from_logs(); live=[]; voidable=[]; never=[]
    for u in units:
        uid=u.get('unit'); t=issued.get(uid)
        if not t: never.append(uid)
        elif now-float(t)<10800: live.append(uid)
        else: voidable.append(uid)
    return {'total':len(units),'live_checkout':live,'voidable':voidable,'never_issued':never,'sellable_now':len(never)+len(voidable),'asof':now}
