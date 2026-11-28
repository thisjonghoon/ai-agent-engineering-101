import json,time,re,httpx
def load(p,d):
 try:
  with open(p,encoding='utf-8') as f:return json.load(f)
 except:return d
def flat(x,k=''):
 if isinstance(x,list):
  z=[]
  for v in x:z+=flat(v,k)
  return z
 if not isinstance(x,dict):return []
 if any(a in x for a in ['sku','sku_id','product_id','productId','code','unit','unit_id','unitId']):
  y=dict(x);y['_key']=k;return [y]
 z=[]
 for a,v in x.items():
  if isinstance(v,(dict,list)):z+=flat(v,a)
 return z
def get(d,ks):return next((d.get(k) for k in ks if d.get(k)!=None),None)
def sid(d):return str(get(d,['sku','sku_id','product_id','productId','code','_key','id']) or '')
def tok(x):return set(re.findall(r'[가-힣A-Za-z]+',str(x).lower()))
def run(a,kit):
 test=kit.testing;card=load('test_card.json' if test else 'card.json',{});cat=flat(load('test_catalog.json' if test else 'catalog.json',{}));meta={sid(x):x for x in cat};inv=[]
 if not test:
  try:
   r=httpx.get(kit.market+'/api/inventory',headers={'authorization':'Bearer '+kit.token('shop')},timeout=8)
   if r.status_code<300:inv=flat(r.json())
  except:pass
 rows=[];seen=set()
 for v in flat(card.get('stock',card.get('inventory',card)))+inv:
  s=sid(v);m=meta.get(s,{});u=get(v,['unit','unit_id','unitId','unit_code']) or get(m,['unit','unit_id','unitId','unit_code']);q=get(v,['quantity','qty','count','available'])
  if not s or not u or u in seen or (q!=None and float(q)<=0):continue
  seen.add(u);rows.append({'sku':s,'unit':u,'name':get(v,['name','title','item','product_name','품목명','상품명']) or get(m,['name','title','item','product_name','품목명','상품명']) or s,'cost':get(v,['cost','unit_cost','원가']) or get(m,['cost','unit_cost','원가','price']),'grade':get(v,['grade']) or get(m,['grade']),'cert':get(v,['certificate_grade','certificate']) or get(m,['certificate_grade','certificate']),'expiry':get(v,['expires_at','expiry']) or get(m,['expires_at','expiry'])})
 stop={'구매','사고싶어요','사고','주세요','원해요','상품','문의','신선한','국내산','가정용','특','대','중','소','한돈','뒷다리살','튀김','소보로','생선'};q=tok(a.get('text',''))-stop
 cand=[r for r in rows if (q & (tok(r['name'])-stop))]
 if not cand:return {'reply':'요청하신 품목은 현재 재고가 없습니다.','state':'completed'}
 c=cand[0]
 try:f=int((float(c['cost'])+210)/.99)+1
 except:return {'reply':'해당 품목의 원가를 확인하지 못했습니다.','state':'completed'}
 pth='test_checkout_locks.json' if test else 'checkout_locks.json';locks=load(pth,{}) or {};now=int(time.time());old=locks.get(c['unit'])
 if isinstance(old,dict) and now-int(old.get('time',0))<10800:return {'reply':'해당 상품은 잠시 예약 중입니다.','state':'completed'}
 payload={'id':c['sku']+'-'+str(now),'shop':'thisjonghoon','shop_url':kit.shop_url,'item':c['sku'],'unit':c['unit'],'price':f,'task':'settle','currency':'credits','iat':now,'cert':c['cert'],'claim':{'sku':c['sku'],'quantity':1,'grade':c['grade']}}
 jwt=kit.sign_jwt(payload,'shop')
 if a.get('claimed_from'):
  locks[c['unit']]={'time':now,'customer':a['claimed_from'],'sku':c['sku']}
  with open(pth,'w') as h:json.dump(locks,h,ensure_ascii=False)
 return {'reply':f"{c['name']} {f}크레딧입니다. 등급 {c['grade'] or '미확인'}, 인증서 등급 {c['cert'] or '미확인'}, 잔여시간 {c['expiry'] if c['expiry'] is not None else '미확인'}입니다.",'data':{'checkout_jwt':jwt,'item':c['sku'],'sku':c['sku'],'unit':c['unit'],'price':f,'floor':f},'state':'completed'}