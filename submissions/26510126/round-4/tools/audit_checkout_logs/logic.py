import json,re,glob

def run(args,kit):
 rows=[]
 for f in glob.glob('logs/*.jsonl'):
  for line in open(f,encoding='utf8'):
   try: o=json.loads(line)
   except: continue
   if o.get('action') not in ('make_checkout','reply'): continue
   s=json.dumps(o,ensure_ascii=False)
   if args.get('unit') and args['unit'] not in s and o.get('action')=='make_checkout': continue
   tokens=re.findall(r'eyJhbGciOiJFSVAxOTEiLCJ0eXAiOiJKV1QifQ\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+',s)
   if tokens: rows.append((o.get('ts',0),o.get('action'),o.get('args',{}),tokens,o.get('observation')))
 out=[]
 for ts,act,a,toks,obs in rows:
  if act!='make_checkout': continue
  for tok in set(toks):
   matches=[]
   for rt,ra,ar,tt,ro in rows:
    if ra=='reply' and ts<=rt<ts+7200:
     for t in set(tt):
      if tok.split('.')[1]==t.split('.')[1]: matches.append({'ts':rt,'to':ar.get('to'),'exact':t==tok,'length':len(t),'sent':ro=='sent','observation':ro})
   out.append({'ts':ts,'unit':a.get('unit'),'length':len(tok),'replies':matches})
 return {'comparisons':out}
