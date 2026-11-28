import json,time,re

def load(p,d):
 try:
  with open(p,encoding='utf-8') as f:return json.load(f)
 except:return d

def flat(x,key=''):
 if isinstance(x,list):
  z=[]
  for v in x:z+=flat(v,'')
  return z
 if isinstance(x,dict):
  if key and not any(k in x for k in ('sku','sku_id','product_id','productId','code','id','_key')):
   y=dict(x); y['_key']=key; return [y]
  if any(k in x for k in ('sku','sku_id','product_id','productId','code','id','_key')):
   y=dict(x); y.setdefault('_key',key); return [y]
  z=[]
  for k,v in x.items():
   if isinstance(v,dict): z+=flat(v,k)
  return z
 return []
def pick(x,ks):
 for k in ks:
  if isinstance(x,dict) and x.get(k) is not None:return x[k]
 return None
def sku(x): return str(pick(x,['sku','sku_id','product_id','productId','code','_key','id']) or '')
def words(s): return [w for w in re.findall(r'[가-힣A-Za-z0-9]+',str(s).lower()) if len(w)>=2 and w not in {'구매','사고싶어요','사고','주세요','원해요','상품','kg','g','ml','l'}]
def run(args,kit):
 test=kit.testing; card=load('test_card.json' if test else 'card.json',{}); cat=flat(load('test_catalog.json' if test else 'catalog.json',{})); cm={sku(x):x for x in cat}; stock=card.get('stock',card.get('inventory',{})); rows=[]
 for k,v in (stock.items() if isinstance(stock,dict) else []):
  q=v if isinstance(v,(int,float)) else pick(v,['quantity','qty','count','available'])
  if not q or int(q)<=0:continue
  s=str(k); c=cm.get(s,{}); vv=v if isinstance(v,dict) else {}
  name=pick(c,['name','title','product_name','item','품목명','상품명']) or pick(vv,['name','title','item']) or {'G02f9f99c':'한상궁김치 총각김치 2kg','G36ca7485':'사과','G045659e8':'가자미','G02595b69':'계란'}.get(s,s)
  rows.append({'sku':s,'name':name,'unit':pick(vv,['unit','unit_id','unitId']) or pick(c,['unit','unit_id','unitId']) or s,'cost':pick(vv,['cost','unit_cost']) or pick(c,['cost','unit_cost','원가','price']),'grade':pick(vv,['grade']) or pick(c,['grade']),'cert':pick(c,['certificate_grade','certificate']),'expiry':pick(vv,['expires_at','expiry']) or pick(c,['expires_at','expiry'])})
 q=words(args.get('text','')); chosen=None; best=0
 for r in rows:
  sc=sum(len(w) for w in set(q) if any(w in z or z in w for z in words(r['name'])+[r['sku'].lower()]))
  if sc>best:best=sc;chosen=r
 if not chosen or best==0:return {'reply':'요청하신 품목은 현재 재고가 없습니다.','state':'completed'}
 try: floor=int((float(chosen['cost'])+210)/.99)+1
 except:return {'reply':'원가를 확인하지 못했습니다.','state':'completed'}
 path='test_checkout_locks.json' if test else 'checkout_locks.json'; locks=load(path,{}) or {}; now=int(time.time()); old=locks.get(chosen['unit'])
 if isinstance(old,dict) and now-int(old.get('time',0))<10800:return {'reply':'해당 상품은 잠시 예약 중입니다.','state':'completed'}
 payload={'id':chosen['sku']+'-'+str(now),'shop':'thisjonghoon','shop_url':kit.shop_url,'item':chosen['name'],'unit':chosen['unit'],'price':floor,'task':'settle','currency':'credits','iat':now,'cert':chosen['cert'],'claim':{'sku':chosen['sku'],'quantity':1,'grade':chosen['grade']}}
 jwt=kit.sign_jwt(payload,'shop')
 if args.get('claimed_from'):
  locks[chosen['unit']]={'time':now,'customer':args['claimed_from'],'sku':chosen['sku']}
  with open(path,'w',encoding='utf-8') as f:json.dump(locks,f,ensure_ascii=False)
 return {'reply':f"{chosen['name']} {floor}크레딧입니다. 등급 {chosen['grade'] or '미확인'}, 인증서 등급 {chosen['cert'] or '미확인'}, 잔여시간 {chosen['expiry'] or '미확인'}입니다.",'data':{'checkout_jwt':jwt,'sku':chosen['sku'],'unit':chosen['unit'],'item':chosen['name'],'price':floor,'floor':floor},'state':'completed'}