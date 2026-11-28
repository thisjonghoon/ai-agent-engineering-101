import httpx

def run(args,kit):
 if kit.testing: return {'posts':[],'complete':True}
 thread=int(args['thread']); cursor=int(args.get('since',thread-1)); posts=[]; pages=0
 with httpx.Client(timeout=15) as c:
  while pages<100:
   r=c.get(kit.market+'/api/forum',params={'since':cursor,'limit':100}); r.raise_for_status(); rows=r.json(); pages+=1
   if not rows: return {'posts':posts,'complete':True,'last_id':cursor,'pages':pages}
   posts += [x for x in rows if x.get('thread')==thread]
   cursor=max(x['id'] for x in rows)
   if len(rows)<100: return {'posts':posts,'complete':True,'last_id':cursor,'pages':pages}
 return {'posts':posts,'complete':False,'last_id':cursor,'pages':pages}
