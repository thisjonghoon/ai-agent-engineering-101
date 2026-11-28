import json,time,re,httpx

def load(p,d):
 try:
  with open(p,encoding='utf-8') as f:return json.load(f)
 except:return d

def val(d,ks): return next((d[k] for k in ks if isinstance(d,dict) and d.get(k) is not None),None)
def sid(d,key=''): return str(val(d,['sku','sku_id','product_id','productId','code','_key','id']) or key)
def records(x,key=''):
 if isinstance(x,list):
  o=[]
  for z in x:o+=records(z,'')
  return o
 if not isinstance(x,dict): return []
 if any(k in x for k in ['sku','sku_id','product_id','productId','code','unit','unit_id','unitId']):
  y=dict(x);y['_key']=key;return [y]
 o=[]
 for k,v in x.items():
  if isinstance(v,(dict,list)):o+=records(v,k)
  elif isinstance(v,(int,float)) and v>0:o.append({'_key':k,'quantity':v})
 return o
def toks(s): return [w for w in re.findall(r'[가-힣A-Za-z0-9]+',str(s).lower()) if len(w)>=2 and w not in {'구매','사고싶어요','사고','주세요','원해요','상품','문의'}]
def run(args,kit):
 test=kit.testing; card=load('test_card.json' if test else 'card.json',{}); cat=records(load('test_catalog.json' if test else 'catalog.json',{})); cm={sid(x):x for x in cat}; inv=[]
 if not test:
  try:
   r=httpx.get(kit.market+'/api/inventory',headers={'authorization':'Bearer '+kit.token('shop')},timeout=8)
   if r.status_code<300: inv=records(r.json())
  except Exception: pass
 rows=[]; raw=card.get('stock',card.get('inventory',card))
 for v in records(raw)+inv:
  s=sid(v); c=cm.get(s,{}); q=val(v,['quantity','qty','count','available']); q=1 if q is None and val(v,['unit','unit_id','unitId']) else q
  if not q or float(q)<=0: continue
  name=val(v,['name','title','item','product_name','품목명','상품명']) or val(c,['name','title','item','product_name','품목명','상품명']) or s
  unit=val(v,['unit','unit_id','unitId']) or val(c,['unit','unit_id','unitId'])
  if unit: rows.append({'sku':s,'name':name,'unit':unit,'cost':val(v,['cost','unit_cost','원가']) or val(c,['cost','unit_cost','원가','price']),'grade':val(v,['grade']) or val(c,['grade']),'cert':val(v,['certificate_grade','certificate']) or val(c,['certificate_grade','certificate']),'expiry':val(v,['expires_at','expiry']) or val(c,['expires_at','expiry'])})
 terms=toks(args.get('text',''))
 cand=[r for r in rows if (set(terms)&set(toks(r['name']))) and (len(terms)<=1 or len(set(terms)&set(toks(r['name'])))>=2)]
 if not cand:return {'reply':'요청하신 품목은 현재 재고가 없습니다.','state':'completed'}
 c=cand[0]
 try: floor=int((float(c['cost'])+210)/.99)+1
 except:return {'reply':'해당 품목의 원가를 확인하지 못했습니다.','state':'completed'}
 path='test_checkout_locks.json' if test else 'checkout_locks.json'; locks=load(path,{}) or {}; now=int(time.time())
 old=locks.get(c['unit'])
 if isinstance(old,dict) and now-int(old.get('time',0))<10800:return {'reply':'해당 상품은 잠시 예약 중입니다.','state':'completed'}
 payload={'id':c['sku']+'-'+str(now),'shop':'thisjonghoon','shop_url':kit.shop_url,'item':c['sku'],'unit':c['unit'],'price':floor,'task':'settle','currency':'credits','iat':now,'cert':c['cert'],'claim':{'sku':c['sku'],'quantity':1,'grade':c['grade']}}
 jwt=kit.sign_jwt(payload,'shop')
 if args.get('claimed_from'):
  locks[c['unit']]={'time':now,'customer':args['claimed_from'],'sku':c['sku']}
  with open(path,'w',encoding='utf-8') as f:json.dump(locks,f,ensure_ascii=False)
 return {'reply':f"{c['name']} {floor}크레딧입니다. 등급 {c['grade'] or '미확인'}, 인증서 등급 {c['cert'] or '미확인'}, 잔여시간 {c['expiry'] or '미확인'}입니다.",'data':{'checkout_jwt':jwt,'sku':c['sku'],'unit':c['unit'],'item':c['sku'],'name':c['name'],'price':floor,'floor':floor},'state':'completed'}