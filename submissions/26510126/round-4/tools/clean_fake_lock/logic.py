import json

def run(args,kit):
 p='test_checkout_locks.json' if getattr(kit,'testing',False) else 'checkout_locks.json'
 try:
  with open(p,encoding='utf-8') as f:x=json.load(f)
 except Exception:x={}
 if isinstance(x,dict): x.pop('s1',None)
 with open(p,'w',encoding='utf-8') as f:json.dump(x,f,ensure_ascii=False)
 return {'ok':True,'removed':'s1'}