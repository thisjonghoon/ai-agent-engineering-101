import json
def run(args,kit):
 p='checkout_locks.json'
 try:
  with open(p,encoding='utf-8') as f: locks=json.load(f)
 except Exception as e:return {'error':str(e)}
 key=str(args.get('unit',args.get('sku','')))
 existed=key in locks
 if existed:
  del locks[key]
  with open(p,'w',encoding='utf-8') as f: json.dump(locks,f,ensure_ascii=False)
 return {'removed':key if existed else None,'remaining':locks}