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
   if tokens: rows.append((o.get('ts'),o.get('action'),o.get('args',{}),tokens))
 issue=[r for r in rows if r[1]=='make_checkout']
 out=[]
 for ts,act,a,toks in issue:
  for tok in set(toks):
   matches=[]
   for rt,ra,ar,tt in rows:
    if ra=='reply' and rt>=ts and rt-ts<7200:
     for t in set(tt):
      if tok.split('.')[1]==t.split('.')[1]: matches.append({'ts':rt,'to':ar.get('to'),'exact':t==tok,'length':len(t)})
   out.append({'ts':ts,'unit':a.get('unit'),'length':len(tok),'replies':matches})
 return {'comparisons':out}
