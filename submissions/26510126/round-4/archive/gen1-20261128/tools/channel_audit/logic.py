import json,collections,httpx

def run(args,kit):
 rows=[]
 with open('logs/react.jsonl') as f:
  for line in f:
   try: rows.append(json.loads(line))
   except: pass
 roles=collections.Counter(); empty=0; n=0
 for x in rows:
  if x.get('action')!='forum_thread': continue
  n+=1
  try:
   ob=x.get('observation',{}); ob=json.loads(ob) if isinstance(ob,str) else ob
   posts=ob.get('result',{}).get('posts',[])
   if not posts: empty+=1
   for p in posts: roles[p.get('role','?')]+=1
  except: pass
 replies=[]
 for x in rows:
  if x.get('action')=='reply':
   a=x.get('args',{}); ob=x.get('observation',''); replies.append({'ts':x.get('ts'),'to':a.get('to'),'text':str(a.get('text',''))[:180],'observation':str(ob)[:300]})
 return {'forum_calls':n,'empty':empty,'roles':dict(roles),'recent_replies':replies[-35:]}
