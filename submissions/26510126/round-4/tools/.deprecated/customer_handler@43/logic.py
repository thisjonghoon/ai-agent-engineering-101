import json,time,re,httpx

def load(p,d):
 try:
  with open(p,encoding='utf-8') as f:return json.load(f)
 except:return d

def flat(x):
 if isinstance(x,list):
  z=[]
  for v in x:z+=flat(v)
  return z
 if isinstance(x,dict):
  for k in ('items','inventory','units','data','results','stock','records','products'):
   if k in x:
    z=flat(x[k])
    if z:return z
  if any(k in x for k in ('sku','sku_id','unit_id','unitId','id','code','product_id','productId','_key')):return [x]
  z=[]
  for k,v in x.items():
   if isinstance(v,dict):
    q=dict(v);q.setdefault('_key',k);z+=flat(q)
  return z
 return []

def val(x,ks):
 for k in ks:
  if isinstance(x,dict) and x.get(k) is not None:return x[k]

def sid(x):return str(val(x,['sku','sku_id','product_id','productId','code','_key','id']) or '')
def norm(x):return re.sub(r'[^0-9a-z가-힣]','',str(x or '').lower())
def words(x):return set(re.findall(r'[0-9a-z가-힣]{2,}',str(x or '').lower()))

def run(args,kit):
 t=kit.testing; card=load('test_card.json' if t else 'card.json',{}); cat=flat(load('test_catalog.json' if t else 'catalog.json',[])); raw=card.get('stock',card.get('inventory',{})) or {}; entries=flat(raw) if isinstance(raw,(list,dict)) else []
 if isinstance(raw,dict) and not entries:entries=[{'_key':k,'quantity':v} for k,v in raw.items()]
 cm={sid(x):x for x in cat if sid(x)}; inv={}
 if not t:
  try:
   r=httpx.get(kit.market+'/api/inventory',headers={'authorization':'Bearer '+kit.token('shop')},timeout=8)
   if r.status_code<300:inv={sid(x):x for x in flat(r.json()) if sid(x)}
  except:pass
 rows=[]
 for e in entries:
  sku=sid(e); qty=val(e,['quantity','qty','count','available'])
  if not sku or (qty is not None and int(qty or 0)<=0):continue
  c=cm.get(sku,{}); i=inv.get(sku,{})
  rows.append({'sku':sku,'name':val(c,['name','title','product_name','item','품목명','상품명']) or val(i,['name','title','product_name','item','품목명','상품명']) or val(e,['name','title','item']),'grade':val(e,['grade']) or val(i,['grade']) or val(c,['grade']),'unit':val(e,['unit','unit_id','unitId']) or val(i,['unit','unit_id','unitId']) or val(c,['unit','unit_id','unitId']) or sku,'cost':val(e,['cost','unit_cost']) or val(c,['cost','unit_cost','원가','price']) or val(i,['cost','unit_cost','price']),'cert':val(e,['certificate_grade','certificate']) or val(i,['certificate_grade','certificate']) or val(c,['certificate_grade','certificate']),'expiry':val(e,['expires_at','expiry']) or val(i,['expires_at','expiry']) or val(c,['expires_at','expiry'])})
 q=str(args.get('text','')); nq=norm(q); qw=words(q)
 def score(e):
  s=0
  for f in (e['name'],e['sku'],e['unit']):
   nf=norm(f)
   if nf and nf in nq:s=max(s,100+len(nf))
   s=max(s,max((len(w) for w in words(f) if w in qw),default=0))
  return s
 chosen=max(rows,key=score,default=None)
 if not chosen or score(chosen)==0:return {'reply':'요청하신 품목은 현재 재고가 없습니다.','state':'completed'}
 try:floor=(float(chosen['cost'])+210)/.99;p=int(floor)+1
 except:return {'reply':'원가를 확인하지 못했습니다.','state':'completed'}
 lp='test_checkout_locks.json' if t else 'checkout_locks.json'; locks=load(lp,{}) or {}; now=int(time.time()); old=locks.get(chosen['unit'])
 if isinstance(old,dict) and now-int(old.get('time',0))<10800 and old.get('customer'):return {'reply':'해당 상품은 잠시 예약 중입니다.','state':'completed'}
 payload={'id':chosen['sku']+'-'+str(now),'shop':'thisjonghoon','shop_url':kit.shop_url,'item':chosen['name'],'unit':chosen['unit'],'price':p,'task':'settle','currency':'credits','iat':now,'cert':chosen['cert'],'claim':{'sku':chosen['sku'],'quantity':1,'grade':chosen['grade']}}
 jwt=kit.sign_jwt(payload,'shop')
 if args.get('claimed_from'):
  locks[chosen['unit']]={'time':now,'customer':args['claimed_from'],'sku':chosen['sku']}
  with open(lp,'w',encoding='utf-8') as f:json.dump(locks,f,ensure_ascii=False)
 return {'reply':f"{chosen['name']} {p}크레딧입니다. 등급 {chosen['grade'] or '미확인'}, 인증서 등급 {chosen['cert'] or '미확인'}, 잔여시간 {chosen['expiry'] or '미확인'}입니다.",'data':{'checkout_jwt':jwt,'sku':chosen['sku'],'unit':chosen['unit'],'item':chosen['name'],'price':p,'floor':int(floor)+1},'state':'completed'}