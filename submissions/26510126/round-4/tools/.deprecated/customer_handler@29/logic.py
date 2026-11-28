import json,time,re,httpx

def load(p,d):
 try:
  with open(p,encoding='utf-8') as f:return json.load(f)
 except:return d

def flat(x):
 if isinstance(x,list): return x
 if isinstance(x,dict):
  out=[]
  for k in ('items','inventory','units','data','results','stock','records'): out += flat(x.get(k,[]))
  return out
 return []

def first(e,keys):
 for k in keys:
  if e.get(k) is not None:return e[k]
 return None

def key(e): return str(first(e,['sku','sku_id','unit_id','unitId','id','code','product_id','productId']) or '')
def norm(x): return re.sub(r'[^0-9a-z가-힣]','',str(x or '').lower())

def run(args,kit):
 test=kit.testing
 card=load('test_card.json' if test else 'card.json',{})
 stock=card.get('stock',card.get('inventory',{})) or {}
 if isinstance(stock,list): stock={key(x):1 for x in stock}
 if test: raw=flat(load('test_catalog.json',[]))
 else:
  raw=[]
  for url in (kit.shop_url+'/api/inventory',kit.shop_url+'/api/stock'):
   try:
    r=httpx.get(url,headers={'authorization':'Bearer '+kit.token('shop')},timeout=8)
    if r.status_code<300:
     got=flat(r.json())
     if got: raw=got; break
   except Exception: pass
 by={key(e):e for e in raw if isinstance(e,dict) and key(e)}
 table=[]
 for sku,n in stock.items():
  if int(n or 0)<=0: continue
  e=by.get(str(sku))
  if not e:
   e=next((x for x in raw if str(first(x,['sku','sku_id','product_id','productId']) or '')==str(sku)),None)
  if not e: continue
  table.append({'sku':str(sku),'name':first(e,['name','item_name','product_name','품목명','title']),'grade':first(e,['grade','등급']),'unit':first(e,['unit','unit_name','단위']),'cost':first(e,['cost','unit_cost','원가','price']),'certificate_grade':first(e,['certificate_grade','certificate','인증서등급']),'expires_at':first(e,['expires_at','expiry','remaining_time','잔여시간']),'aliases':first(e,['aliases','alias']) or []})
 with open('test_catalog.json' if test else 'catalog.json','w',encoding='utf-8') as f: json.dump(table,f,ensure_ascii=False)
 text=str(args.get('text','')); low=norm(text)
 if not any(x in low for x in ('구매','주문','결제','사줘','buy','checkout')): return {'reply':'구매하실 품목을 말씀해 주세요.','state':'completed'}
 found=next((e for e in table if any(norm(x) and norm(x) in low for x in [e['name']]+(e['aliases'] if isinstance(e['aliases'],list) else []))),None)
 if not found:return {'reply':'요청하신 품목은 현재 재고가 없습니다. 결제서와 예약을 만들지 않았습니다.','state':'completed'}
 try: floor=int((float(found['cost'])+210)/.99)+1
 except:return {'reply':'원가를 확인하지 못해 결제서와 예약을 만들지 않았습니다.','state':'completed'}
 lp='test_checkout_locks.json' if test else 'checkout_locks.json'; locks=load(lp,{})
 now=int(time.time()); old=locks.get(found['sku'])
 if isinstance(old,dict) and now-int(old.get('time',now))<10800:return {'reply':'해당 상품은 잠시 예약 중입니다.','state':'completed'}
 jwt=kit.sign_jwt({'sku':found['sku'],'quantity':1,'price':floor,'shop':kit.shop_url,'ts':now},'shop')
 if not jwt:return {'reply':'결제서 생성에 실패했습니다.','state':'completed'}
 locks[found['sku']]={'time':now,'customer':args.get('claimed_from','')}
 with open(lp,'w',encoding='utf-8') as f: json.dump(locks,f,ensure_ascii=False)
 return {'reply':f"{found['name']} {floor}크레딧입니다. 등급 {found['grade'] or '미확인'}, 인증서 등급 {found['certificate_grade'] or '미확인'}, 잔여시간 {found['expires_at'] or '미확인'}입니다.",'data':{'checkout_jwt':jwt,'sku':found['sku'],'price':floor},'state':'completed'}
