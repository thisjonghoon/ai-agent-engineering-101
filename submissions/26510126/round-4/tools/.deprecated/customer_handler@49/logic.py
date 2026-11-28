import json,time,re

def load(p,d):
 try:
  with open(p,encoding='utf-8') as f:return json.load(f)
 except:return d

def val(d,ks):
 return next((d[k] for k in ks if isinstance(d,dict) and d.get(k) is not None),None)
def sid(d,key=''):
 return str(val(d,['sku','sku_id','product_id','productId','code','_key','id']) or key)
def records(x,key=''):
 if isinstance(x,list):
  out=[]
  for z in x: out+=records(z,'')
  return out
 if not isinstance(x,dict): return []
 if any(k in x for k in ['sku','sku_id','product_id','productId','code','unit','unit_id','unitId']):
  y=dict(x); y['_key']=key; return [y]
 out=[]
 for k,v in x.items():
  if isinstance(v,(dict,list)): out+=records(v,k)
  elif isinstance(v,(int,float)) and v>0: out.append({'_key':k,'quantity':v})
 return out
def toks(s): return [w for w in re.findall(r'[가-힣A-Za-z0-9]+',str(s).lower()) if len(w)>=2 and w not in {'구매','사고싶어요','사고','주세요','원해요','상품'}]
def run(args,kit):
 test=kit.testing; card=load('test_card.json' if test else 'card.json',{}); cat=records(load('test_catalog.json' if test else 'catalog.json',{})); cm={sid(x):x for x in cat}; raw=card.get('stock',card.get('inventory',card)); rows=[]
 for v in records(raw):
  q=val(v,['quantity','qty','count','available']); q=1 if q is None and val(v,['unit','unit_id','unitId']) else q
  if not q or float(q)<=0: continue
  s=sid(v); c=cm.get(s,{})
  name=val(v,['name','title','item','product_name']) or val(c,['name','title','item','product_name','품목명','상품명']) or s
  rows.append({'sku':s,'name':name,'unit':val(v,['unit','unit_id','unitId']) or val(c,['unit','unit_id','unitId']) or s,'cost':val(v,['cost','unit_cost']) or val(c,['cost','unit_cost','원가','price']),'grade':val(v,['grade']) or val(c,['grade']),'cert':val(v,['certificate_grade','certificate']) or val(c,['certificate_grade','certificate']),'expiry':val(v,['expires_at','expiry']) or val(c,['expires_at','expiry'])})
 q=toks(args.get('text','')); chosen=max(rows,key=lambda r:sum(1 for w in set(q) if any(w in z or z in w for z in toks(r['name'])+[r['sku'].lower()])),default=None); score=sum(1 for w in set(q) if chosen and any(w in z or z in w for z in toks(chosen['name'])+[chosen['sku'].lower()]))
 if not chosen or not score:return {'reply':'요청하신 품목은 현재 재고가 없습니다.','state':'completed'}
 try: floor=int((float(chosen['cost'])+210)/.99)+1
 except:return {'reply':'원가를 확인하지 못했습니다.','state':'completed'}
 path='test_checkout_locks.json' if test else 'checkout_locks.json'; locks=load(path,{}) or {}; now=int(time.time()); old=locks.get(chosen['unit'])
 if isinstance(old,dict) and now-int(old.get('time',0))<10800:return {'reply':'해당 상품은 잠시 예약 중입니다.','state':'completed'}
 payload={'id':chosen['sku']+'-'+str(now),'shop':'thisjonghoon','shop_url':kit.shop_url,'item':chosen['name'],'unit':chosen['unit'],'price':floor,'task':'settle','currency':'credits','iat':now,'cert':chosen['cert'],'claim':{'sku':chosen['sku'],'quantity':1,'grade':chosen['grade']}}
 jwt=kit.sign_jwt(payload,'shop')
 if args.get('claimed_from'):
  locks[chosen['unit']]={'time':now,'customer':args['claimed_from'],'sku':chosen['sku']}
  with open(path,'w',encoding='utf-8') as f: json.dump(locks,f,ensure_ascii=False)
 return {'reply':f"{chosen['name']} {floor}크레딧입니다. 등급 {chosen['grade'] or '미확인'}, 인증서 등급 {chosen['cert'] or '미확인'}, 잔여시간 {chosen['expiry'] or '미확인'}입니다.",'data':{'checkout_jwt':jwt,'sku':chosen['sku'],'unit':chosen['unit'],'item':chosen['name'],'price':floor,'floor':floor},'state':'completed'}