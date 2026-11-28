import json, os, time
import httpx

def num(x, default=0):
    try: return float(x)
    except: return default

def ts(e):
    for k in ('ts','timestamp','created_at','time'):
        if k in e:
            v=num(e[k])
            if v>10**12: v/=1000
            return v
    return 0

def kind(e):
    return str(e.get('event',e.get('type',e.get('action',e.get('status',''))))).lower()

def run(args, kit):
    now=time.time()
    rows=[]
    # Fetch public ledger pages; tolerate either list or object response.
    for page in range(1,80):
        url=kit.market+'/api/ledger'
        try:
            r=httpx.get(url,params={'page':page,'limit':1000},timeout=15)
            if r.status_code!=200: break
            d=r.json()
            batch=d if isinstance(d,list) else (d.get('entries') or d.get('ledger') or d.get('items') or d.get('data') or [])
            if isinstance(batch,dict): batch=[batch]
            if not batch: break
            rows.extend(batch)
            if len(batch)<1000: break
        except Exception: break
    out={}
    for hours in (3,24):
        cutoff=now-hours*3600
        sales_n=sales_amt=buy_amt=expired_cost=0.0
        for e in rows:
            t=ts(e)
            if t<cutoff or t>now+300: continue
            k=kind(e)
            amount=num(e.get('amount',e.get('total',e.get('price',0))))
            cost=num(e.get('cost',e.get('unit_cost',e.get('buy_cost',0))))
            qty=num(e.get('qty',e.get('quantity',1)),1)
            if any(x in k for x in ('settle','sale','sold','purchase_sale')) or e.get('shop')==kit.shop_url and e.get('buyer'):
                sales_n+=qty; sales_amt+=amount
            if any(x in k for x in ('buy','wholesale','purchase','stock')) and not any(x in k for x in ('sale','settle')):
                buy_amt+=amount or cost*qty
            if any(x in k for x in ('expire','expired','spoil','discard','waste','void')):
                expired_cost+=cost*qty if cost else amount
        out[str(hours)+'h']={'sales_count':int(sales_n),'sales_amount':round(sales_amt,2),'purchase_amount':round(buy_amt,2),'expired_discard_cost':round(expired_cost,2)}
    # wallet log delta over windows
    wp=os.path.join(os.getcwd(),'logs','wallet.jsonl')
    vals=[]
    try:
        for line in open(wp,encoding='utf-8'):
            try:
                e=json.loads(line); t=ts(e); b=e.get('credits',e.get('balance',e.get('amount')))
                if b is not None: vals.append((t,num(b)))
            except: pass
    except: pass
    vals.sort()
    for h in (3,24):
        cut=now-h*3600; old=[v for t,v in vals if t>=cut and t<=now+300]
        out[str(h)+'h']['wallet_delta']=round((old[-1]-old[0]) if len(old)>=2 else 0,2)
    result={'asof':now,'windows':out,'ledger_rows':len(rows)}
    line='shop_health '+json.dumps(result,ensure_ascii=False,separators=(',',':'))
    try:
        with open('notes.md','a',encoding='utf-8') as f: f.write('\n'+line+'\n')
    except Exception: pass
    return result
