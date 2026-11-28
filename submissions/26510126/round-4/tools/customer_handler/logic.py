import json,time,re,httpx

def load(p,d):
 try:
  with open(p,encoding='utf-8') as f:return json.load(f)
 except:return d

def flatten(x,key=''):
 if isinstance(x,list):
  out=[]
  for v in x: out+=flatten(v,key)
  return out
 if not isinstance(x,dict): return []
 keys=['sku','sku_id','product_id','productId','code','unit','unit_id','unitId']
 if any(k in x for k in keys):
  y=dict(x); y['_key']=key; return [y]
 out=[]
 for k,v in x.items():
  if isinstance(v,(dict,list)): out+=flatten(v,k)
  elif isinstance(v,(int,float)) and v>0: out.append({'_key':k,'quantity':v})
 return out

def first(d,ks):
 return next((d.get(k) for k in ks if isinstance(d,dict) and d.get(k) is not None),None)

def sku(d): return str(first(d,['sku','sku_id','product_id','productId','code','_key','id']) or '')
def words(s): return set(re.findall(r'[가-힣A-Za-z0-9]+',str(s).lower()))

def run(args,kit):
 test=kit.testing
 card=load('test_card.json' if test else 'card.json',{})
 cat=flatten(load('test_catalog.json' if test else 'catalog.json',{}))
 meta={sku(x):x for x in cat if sku(x)}
 inv=[]
 if not test:
  try:
   r=httpx.get(kit.market+'/api/inventory',headers={'authorization':'Bearer '+kit.token('shop')},timeout=8)
   if r.status_code<300: inv=flatten(r.json())
  except Exception: pass
 stock=flatten(card.get('stock',card.get('inventory',card)))+inv
 rows=[]; seen=set()
 for v in stock:
  s=sku(v); m=meta.get(s,{})
  q=first(v,['quantity','qty','count','available'])
  u=first(v,['unit','unit_id','unitId','unit_code']) or first(m,['unit','unit_id','unitId','unit_code'])
  if not s or not u or (q is not None and float(q)<=0): continue
  if u in seen: continue
  seen.add(u)
  name=first(v,['name','title','item','product_name','품목명','상품명']) or first(m,['name','title','item','product_name','품목명','상품명']) or s
  rows.append({'sku':s,'unit':u,'name':name,'cost':first(v,['cost','unit_cost','원가']) or first(m,['cost','unit_cost','원가','price']),'grade':first(v,['grade']) or first(m,['grade']),'cert':first(v,['certificate_grade','certificate']) or first(m,['certificate_grade','certificate']),'expiry':first(v,['expires_at','expiry']) or first(m,['expires_at','expiry'])})
 t=words(args.get('text',''))
 stop={'구매','사고싶어요','사고','주세요','원해요','상품','문의','신선한'}
 t-=stop
 cand=[r for r in rows if (t & words(r['name']))]
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
  with open(path,'w',encoding='utf-8') as f: json.dump(locks,f,ensure_ascii=False)
 exp=c['expiry'] if c['expiry'] is not None else '미확인'
 return {'reply':f"{c['name']} {floor}크레딧입니다. 등급 {c['grade'] or '미확인'}, 인증서 등급 {c['cert'] or '미확인'}, 잔여시간 {exp}입니다.",'data':{'checkout_jwt':jwt,'sku':c['sku'],'unit':c['unit'],'item':c['sku'],'name':c['name'],'price':floor,'floor':floor},'state':'completed'}