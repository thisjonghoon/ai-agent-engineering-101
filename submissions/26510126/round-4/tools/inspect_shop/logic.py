import httpx,json

def run(args,kit):
 base=kit.shop_url.rstrip('/')
 paths=['/.well-known/agent-card.json','/.well-known/acp.json','/card.json','/api/stock']
 out={}
 for p in paths:
  try:
   r=httpx.get(base+p,timeout=6);out[p]={'status':r.status_code,'text':r.text[:20000]}
  except Exception as e:out[p]={'error':str(e)}
 with open('shop_inspect.json','w',encoding='utf-8') as f:json.dump(out,f,ensure_ascii=False)
 return out
