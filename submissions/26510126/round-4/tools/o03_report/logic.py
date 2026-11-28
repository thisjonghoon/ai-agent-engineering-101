import json

def load(p,d):
 try:
  with open(p,encoding='utf-8') as f:return json.load(f)
 except:return d

def flat(x):
 if isinstance(x,list): return x
 if isinstance(x,dict):
  z=[]
  for v in x.values(): z+=flat(v)
  return z
 return []

def run(args,kit):
 card=load('card.json',{}); stock=card.get('stock',card.get('inventory',{})) or {}; raw=load('catalog.json',[])
 if isinstance(raw,dict): raw=flat(raw)
 by={str(e.get('sku',e.get('id',e.get('code','')))):e for e in raw if isinstance(e,dict)}
 rows=[]
 for sku,n in stock.items():
  if int(n or 0)>0 and str(sku) in by:
   e=by[str(sku)]; c=e.get('cost',e.get('unit_cost',e.get('원가')))
   try: floor=int((float(c)+210)/.99)+1
   except: floor=None
   rows.append({'sku':sku,'name':e.get('name',e.get('item_name',e.get('품목명'))),'grade':e.get('grade',e.get('등급')),'unit':e.get('unit',e.get('단위')),'cost':c,'floor':floor})
 msgs=[]
 try:
  for line in open('logs/talk.jsonl',encoding='utf-8'):
   x=json.loads(line); ts=float(x.get('ts',x.get('time',0)) or 0)
   if ts>=1795867200: msgs.append(x)
 except: pass
 out={'sku_rows':rows[:20],'sku_count':min(20,len(rows)),'messages_after_ts':msgs,'message_count':len(msgs)}
 with open('o03_report.json','w',encoding='utf-8') as f: json.dump(out,f,ensure_ascii=False)
 return out