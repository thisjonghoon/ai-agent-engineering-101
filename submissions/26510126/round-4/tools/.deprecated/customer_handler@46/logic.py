import json,time,re,httpx

def load(p,d):
 try:
  with open(p,encoding='utf-8') as f:return json.load(f)
 except:return d

def rec(x,key=None):
 if isinstance(x,list):
  return sum((rec(v) for v in x),[])
 if not isinstance(x,dict):return []
 y=dict(x)
 if key is not None:y.setdefault('_key',key)
 if any(k in y for k in ('sku','sku_id','unit_id','unitId','id','code','product_id','productId','_key')):return [y]
 return sum((rec(v,k) for k,v in x.items() if isinstance(v,dict)),[])

def val(x,ks):
 for k in ks:
  if x.get(k) is not None:return x[k]
def sid(x):return str(val(x,['sku','sku_id','product_id','productId','code','_key','id']) or '')
def words(x):return [w for w in re.findall(r'[가-힣A-Za-z]{2,}',str(x or '').lower()) if w not in {'구매','사고싶어요','사고','주세요','찾아요','원해요','안팎','소포장','조리된','반찬','국내산','가정용','혼합'}]

def run(args,kit):
 t=kit.testing;card=load('test_card.json' if t else 'card.json',{});cat=rec(load('test_catalog.json' if t else 'catalog.json',{}));raw=card.get('stock',card.get('inventory',{}));entries=rec(raw);cm={sid(x):x for x in cat};inv={}
 if not t:
  try:
   r=httpx.get(kit.market+'/api/inventory',headers={'authorization':'Bearer '+kit.token('shop')},timeout=8)
   if r.status_code<300:inv={sid(x):x for x in rec(r.json())}
  except:pass
 rows=[]
 for e in entries:
  sku=sid(e);qty=val(e,['quantity','qty','count','available'])
  if not sku or (qty is not None and int(qty or 0)<=0):continue
  c=cm.get(sku,{});i=inv.get(sku,{})
  rows.append({'sku':sku,'name':val(c,['name','title','product_name','item','품목명','상품명']) or val(i,['name','title','product_name','item','품목명','상품명']) or val(e,['name','title','item']) or sku,'grade':val(e,['grade']) or val(i,['grade']) or val(c,['grade']),'unit':val(e,['unit','unit_id','unitId']) or val(i,['unit','unit_id','unitId']) or val(c,['unit','unit_id','unitId']) or sku,'cost':val(e,['cost','unit_cost']) or val(c,['cost','unit_cost','원가','price']) or val(i,['cost','unit_cost','price']),'cert':val(e,['certificate_grade','certificate']) or val(i,['certificate_grade','certificate']) or val(c,['certificate_grade','certificate']),'expiry':val(e,['expires_at','expiry']) or val(i,['expires_at','expiry']) or val(c,['expires_at','expiry'])})
 q=str(args.get('text','')).lower();qw=words(q);chosen=None;best=0
 for e in rows:
  n=str(e['name']).lower();s=sum(len(w) for w in qw if w in n or w in str(e['sku']).lower())
  if s>best:best=s;chosen=e
 if not chosen:return {'reply':'요청하신 품목은 현재 재고가 없습니다.','state':'completed'}
 try:floor=(float(chosen['cost'])+210)/.99;price=int(floor)+1
 except:return {'reply':'원가를 확인하지 못했습니다.','state':'completed'}
 lp='test_checkout_locks.json' if t else 'checkout_locks.json';locks=load(lp,{}) or {};now=int(time.time());old=locks.get(chosen['unit'])
 if isinstance(old,dict) and now-int(old.get('time',0))<10800 and old.get('customer'):return {'reply':'해당 상품은 잠시 예약 중입니다.','state':'completed'}
 payload={'id':chosen['sku']+'-'+str(now),'shop':'thisjonghoon','shop_url':kit.shop_url,'item':chosen['name'],'unit':chosen['unit'],'price':price,'task':'settle','currency':'credits','iat':now,'cert':chosen['cert'],'claim':{'sku':chosen['sku'],'quantity':1,'grade':chosen['grade']}}
 jwt=kit.sign_jwt(payload,'shop')
 if args.get('claimed_from'):
  locks[chosen['unit']]={'time':now,'customer':args['claimed_from'],'sku':chosen['sku']}
  with open(lp,'w',encoding='utf-8') as f:json.dump(locks,f,ensure_ascii=False)
 return {'reply':f"{chosen['name']} {price}크레딧입니다. 등급 {chosen['grade'] or '미확인'}, 인증서 등급 {chosen['cert'] or '미확인'}, 잔여시간 {chosen['expiry'] or '미확인'}입니다.",'data':{'checkout_jwt':jwt,'sku':chosen['sku'],'unit':chosen['unit'],'item':chosen['name'],'price':price,'floor':int(floor)+1},'state':'completed'}
