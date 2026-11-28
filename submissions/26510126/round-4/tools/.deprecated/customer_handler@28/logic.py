import json,time,re,httpx

def load(p,d):
 try:
  with open(p,encoding='utf-8') as f:return json.load(f)
 except:return d
def flat(x):
 if isinstance(x,list): return x
 if isinstance(x,dict):
  z=[]
  for k in ('items','inventory','units','data','results','stock'): z+=flat(x.get(k,[]))
  return z
 return []
def sid(e): return str(e.get('sku',e.get('unit_id',e.get('id',e.get('code','')))))
def norm(x): return re.sub(r'[^0-9a-z가-힣]','',str(x or '').lower())
def val(e,*ks):
 for k in ks:
  if e.get(k) is not None:return e[k]
 return None
def run(args,kit):
 test=kit.testing; card=load('test_card.json' if test else 'card.json',{}); stock=card.get('stock',card.get('inventory',{})) or {}
 if test: raw=flat(load('test_catalog.json',[]))
 else:
  raw=[]
  for url in (kit.shop_url+'/api/inventory',kit.shop_url+'/api/stock'):
   try:
    r=httpx.get(url,headers={'authorization':'Bearer '+kit.token('shop')},timeout=8)
    if r.status_code<300: raw=flat(r.json());
    if raw: break
   except: pass
 by={sid(e):e for e in raw if isinstance(e,dict)}; table=[]
 for sku,n in stock.items():
  if int(n or 0)>0 and sku in by:
   e=by[sku]; table.append({'sku':sku,'name':val(e,'name','item_name','product_name','품목명'),'grade':val(e,'grade','등급'),'unit':val(e,'unit','unit_name','단위'),'cost':val(e,'cost','unit_cost','원가'),'certificate_grade':val(e,'certificate_grade','certificate','인증서등급'),'expires_at':val(e,'expires_at','expiry','remaining_time','잔여시간'),'aliases':val(e,'aliases','alias') or []})
 with open('test_catalog.json' if test else 'catalog.json','w',encoding='utf-8') as f: json.dump(table,f,ensure_ascii=False)
 text=str(args.get('text','')); low=norm(text)
 if not any(x in low for x in ('구매','주문','결제','사줘','buy','checkout')): return {'reply':'구매하실 품목을 말씀해 주세요.','state':'completed'}
 found=next((e for e in table if any(norm(x) and norm(x) in low for x in [e['name']]+(e['aliases'] if isinstance(e['aliases'],list) else []))),None)
 if not found:return {'reply':'요청하신 품목은 현재 재고가 없습니다. 결제서와 예약을 만들지 않았습니다.','state':'completed'}
 try: floor=int((float(found['cost'])+210)/.99)+1
 except:return {'reply':'원가를 확인하지 못해 결제서와 예약을 만들지 않았습니다.','state':'completed'}
 lp='test_checkout_locks.json' if test else 'checkout_locks.json'; locks=load(lp,{}); now=int(time.time()); old=locks.get(found['sku'])
 if isinstance(old,dict) and now-int(old.get('time',now))<10800:return {'reply':'해당 상품은 잠시 예약 중입니다.','state':'completed'}
 jwt=kit.sign_jwt({'sku':found['sku'],'quantity':1,'price':floor,'shop':kit.shop_url,'ts':now},'shop')
 if not jwt:return {'reply':'결제서 생성에 실패했습니다.','state':'completed'}
 locks[found['sku']]={'time':now,'customer':args.get('claimed_from','')}
 with open(lp,'w',encoding='utf-8') as f: json.dump(locks,f,ensure_ascii=False)
 return {'reply':f"{found['name']} {floor}크레딧입니다. 등급 {found['grade'] or '미확인'}, 인증서 등급 {found['certificate_grade'] or '미확인'}, 잔여시간 {found['expires_at'] or '미확인'}입니다.",'data':{'checkout_jwt':jwt,'sku':found['sku'],'price':floor},'state':'completed'}
