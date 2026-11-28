import json,re,time,httpx

def rd(p,d):
 try:
  with open(p,encoding='utf-8') as f:return json.load(f)
 except Exception:return d

def run(args,kit):
 text=str(args.get('text','')); low=text.lower(); card=rd('card.json',{}); prices=rd('prices.json',{})
 raw=card.get('stock',card.get('inventory',[]))
 if isinstance(raw,dict): raw=[dict(v,sku=k) if isinstance(v,dict) else {'sku':k,'quantity':v} for k,v in raw.items()]
 held=rd('archive/gen1-20261128/cutover.json',{}); held=set(held.get('held',held.get('units',[]))) if isinstance(held,dict) else set(held or [])
 locks=rd('checkout_locks.json',{}); now=time.time(); candidates=[]
 for z in raw:
  if not isinstance(z,dict): continue
  sku=str(z.get('sku',z.get('id',z.get('item','')))); q=float(z.get('quantity',z.get('available',0)) or 0)
  lk=locks.get(sku) if isinstance(locks,dict) else None
  if q>0 and sku not in held and not (isinstance(lk,dict) and now-float(lk.get('time',0))<10800): candidates.append((z,sku))
 def info(z,s):
  pv=prices.get(s,prices.get(z.get('item',z.get('name',s))))
  return (z.get('item',z.get('name',s)),z.get('grade','미측정'),z.get('quantity',z.get('available',0)),z.get('time_left',z.get('expires_in','미측정')),z.get('certificate_grade','미측정'),pv.get('price') if isinstance(pv,dict) else pv)
 # Match explicit item words against item/name/sku; never silently choose unrelated stock.
 named=[]
 for z,s in candidates:
  n,_,_,_,_,_=info(z,s)
  if str(n).lower() in low or s.lower() in low: named.append((z,s))
 pool=named or ([x for x in candidates if not any(k in low for k in ('구매','주문','checkout','결제서','사고','살게','buy','purchase'))] and candidates or [])
 gm=re.search(r'(?:grade|등급)\s*[:=]?\s*([a-z0-9가-힣+-]+)',low)
 if gm: pool=[x for x in pool if gm.group(1) in str(info(*x)[1]).lower()]
 if not pool:
  return {'reply':'요청하신 조건에 맞는 판매 재고가 없습니다. 확인하지 못한 조건은 재고 부족 여부입니다.','state':'completed'}
 def line(x):
  n,g,q,l,c,p=info(*x); return f'{n}: {g}등급, {q}개, {p if isinstance(p,(int,float)) else "가격 미확인"}크레딧, 잔여 {l}, 인증서 등급 {c}'
 buy=any(w in low for w in ('buy','purchase','checkout','구매','살게','사고','주문','결제서'))
 if not buy:return {'reply':'현재 재고입니다. '+' / '.join(line(x) for x in pool[:8])+' 확인하지 못한 조건은 말씀해 주세요.','state':'completed'}
 z,s=pool[0]; n,g,q,l,c,p=info(z,s)
 if not isinstance(p,(int,float)): return {'reply':f'{n} 재고는 있지만 가격을 확인하지 못했습니다. {g}등급, 잔여 {l}, 인증서 등급 {c}입니다.','state':'completed'}
 locks=dict(locks) if isinstance(locks,dict) else {}; locks[s]={'time':int(now),'customer':args.get('claimed_from',''),'item':n}
 with open('checkout_locks.json','w',encoding='utf-8') as f: json.dump(locks,f,ensure_ascii=False)
 try:
  receipt=kit.sign_jwt({'sku':s,'quantity':1,'price':int(p),'shop':kit.shop_url,'ts':int(now)},'shop')
  r=httpx.post(kit.shop_url.rstrip('/')+'/checkout_sessions',json={'line_items':[{'id':s,'quantity':1}],'receipt':receipt,'acceptable':[s]},timeout=8); b=r.json(); jwt=b.get('checkout_jwt') or b.get('checkout',{}).get('checkout_jwt')
  if jwt:return {'reply':f'{n} {g}등급, {p}크레딧, 잔여 {l}입니다. 인증서 등급은 {c}이며 서명된 결제서를 보냅니다.','data':{'checkout_jwt':jwt,'sku':s,'grade':g,'time_left':l,'certificate_grade':c},'state':'completed'}
 except Exception: pass
 return {'reply':f'{n} 재고를 예약했지만 결제서 생성에 실패했습니다. 가격 {p}크레딧, {g}등급, 잔여 {l}, 인증서 등급 {c}입니다.','state':'completed'}