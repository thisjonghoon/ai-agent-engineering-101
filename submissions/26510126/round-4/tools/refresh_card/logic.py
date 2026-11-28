import httpx,json

def run(args,kit):
    r=httpx.get('https://market.ourolabs.ai/api/shops',timeout=10)
    data=r.json()
    me=None
    for x in (data if isinstance(data,list) else data.get('shops',[])):
        if str(x.get('name','')).lower() in ('thisjonghoon','jonghoon') or x.get('wallet','').lower()=='0x1bd3db2c6d412b88fab1ad3e08c32ae417e00166': me=x;break
    card=me or {'name':'thisjonghoon','stock':[]}
    with open('card.json','w',encoding='utf-8') as f:json.dump(card,f,ensure_ascii=False)
    return card
