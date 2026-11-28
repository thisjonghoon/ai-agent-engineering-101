def run(args,kit):
 p=args['path']
 if '..' in p or p.startswith('/'): return {'error':'invalid path'}
 try:
  with open(p,encoding='utf8') as f: lines=f.readlines()
  return {'lines':''.join(lines[int(args.get('start',0)):int(args.get('end',1000))])}
 except Exception as e: return {'error':str(e)}
