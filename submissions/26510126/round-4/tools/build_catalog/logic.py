import httpx,json

def run(args,kit):
 for path in ['/api/catalog','/api/wholesale/catalog','/api/wholesale/items','/api/items','/api/shops']:
  try:
   r=httpx.get(kit.market+path,timeout=5)
   if r.status_code==200:
    x=r.json(); data=x.get('catalog',x.get('items',x.get('products',x.get('result',x)))) if isinstance(x,dict) else x
    if isinstance(data,(list,dict)):
     vals=list(data.values()) if isinstance(data,dict) else data
     if any(isinstance(v,dict) and (v.get('sku') or v.get('id')) for v in vals):
      with open('catalog.json','w',encoding='utf-8') as f: json.dump(data,f,ensure_ascii=False)
      return {'path':path,'count':len(vals)}
  except Exception: pass
 return {'count':0,'error':'catalog endpoint unavailable'}
