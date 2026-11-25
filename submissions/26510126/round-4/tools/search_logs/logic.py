import os,json

def run(args,kit):
 q=args['query']; out=[]
 for p in ['logs/react.jsonl','logs/forge.jsonl']:
  if os.path.exists(p):
   with open(p,encoding='utf-8') as f:
    for line in f:
     if q in line: out.append({'file':p,'line':line[-12000:]})
 return {'matches':out[-int(args.get('limit',10)):]}