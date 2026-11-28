import httpx, json

def run(args, kit):
    base='https://market.ourolabs.ai'
    paths=['/.well-known/agent-card.json','/entities/orders/.well-known/agent-card.json','/entities/clearing/.well-known/agent-card.json','/entities/wholesale/.well-known/agent-card.json','/entities/forum/.well-known/agent-card.json','/entities/board/.well-known/agent-card.json','/entities/bank/.well-known/agent-card.json','/ROUND4.md','/api/shops','/api/ledger']
    out={}
    for p in paths:
        try:
            r=httpx.get(base+p,timeout=8)
            out[p]={'status':r.status_code,'text':r.text[:12000]}
        except Exception as e: out[p]={'error':str(e)}
    with open('market_snapshot.json','w',encoding='utf-8') as f: json.dump(out,f,ensure_ascii=False)
    return out
