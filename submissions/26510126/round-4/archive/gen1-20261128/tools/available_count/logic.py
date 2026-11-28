import httpx,json,glob,os,time

def run(args,kit):
 units=httpx.get(kit.market+'/api/inventory',headers={'authorization':'Bearer '+kit.token('shop')},timeout=20).json()['units']
 issued=set()
 for f in glob.glob('logs/*.jsonl'):
  for line in open(f,encoding='utf8'):
   try:
    o=json.loads(line)
    if o.get('action')=='make_checkout' and 'eyJhbGciOiJFSVAxOTEiLCJ0eXAiOiJKV1Q' in line and o.get('args',{}).get('unit'): issued.add(o['args']['unit'])
   except: pass
 if os.path.exists('auto_checkout.jsonl'):
  for line in open('auto_checkout.jsonl',encoding='utf8'):
   try: issued.add(json.loads(line)['unit'])
   except: pass
 locks={}
 if os.path.exists('checkout_locks.json'):
  locks=json.load(open('checkout_locks.json',encoding='utf8'))
 ids=['Gab7c8b3d','G02f9f99c','G159be1f8','G0746760c','G35745411','G3c4127d8']; groups={}
 for sku in ids:
  us=[u for u in units if u['sku']==sku]; free=[u for u in us if u['unit'] not in issued and u['unit'] not in locks and (not u.get('expires_at') or u['expires_at']>time.time())]
  groups[sku]={'stock':len(us),'no_issuance_or_lock':len(free),'units':[{'unit':u['unit'],'grade':u['grade']} for u in free]}
 return {'groups':groups,'total_stock':sum(v['stock'] for v in groups.values()),'candidate_total':sum(v['no_issuance_or_lock'] for v in groups.values()),'caution':'후보 수는 실제 결제서 발급 성공을 보장하지 않음; 잠금 구조와 과거 기록 확인 필요','lock_type':type(locks).__name__}
