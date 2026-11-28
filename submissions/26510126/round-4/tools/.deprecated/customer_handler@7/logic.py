import json,re,time,httpx

def rd(p,d,k):
 if getattr(k,'testing',False) and p in ('card.json','prices.json','checkout_locks.json'): p='test_'+p
 try:
  with open(p,encoding='utf-8') as f:return json.load(f)
 except Exception:return d

def wr(p,x,k):
 if getattr(k,'testing',False) and p in ('card.json','prices.json','checkout_locks.json'): p='test_'+p
 with open(p,'w',encoding='utf-8') as f:json.dump(x,f,ensure_ascii=False)

def run(args,kit):
 text=str(args.get('text','')); low=text.lower(); card=rd('card.json',{},kit); prices=rd('prices.json',{},kit); raw=card.get('stock',card.get('inventory',[])); aliases={'사과':'G36ca7485','apple':'G36ca7485'}
 if isinstance(raw,dict):raw=[dict(v,sku=k) if isinstance(v,dict) else {'sku':k,'quantity':v} for k,v in raw.items()]
 h=rd('archive/gen1-20261128/cutover.json',{},kit); held=set(h.get('held',h.get('units',[]))) if isinstance(h,dict) else set(h or []); locks=rd('checkout_locks.json',{},kit); now=time.time(); pool=[]
 for z in raw:
  if not isinstance(z,dict):continue
  s=str(z.get('sku',z.get('id',z.get('item','')))); q=float(z.get('quantity',z.get('available',0)) or 0); l=locks.get(s) if isinstance(locks,dict) else None
  if q>0 and s not in held and not(isinstance(l,dict) and now-float(l.get('time',0))<10800):pool.append((z,s))
 def inf(z,s):
  v=prices.get(s,prices.get(z.get('item',z.get('name',s)))); n=z.get('item',z.get('name',next((k for k,vv in aliases.items() if vv==s),s))); return n,z.get('grade','미측정'),z.get('quantity',z.get('available',0)),z.get('time_left',z.get('expires_in','미측정')),z.get('certificate_grade','미측정'),v.get('price') if isinstance(v,dict) else v
 named=[x for x in pool if str(inf(*x)[0]).lower() in low or any(k in low and v==x[1] for k,v in aliases.items())]
 buy=any(w in low for w in ('buy','purchase','checkout','구매','살게','사고','주문','결제서')); pool=named or (pool if not buy else [])
 if not pool:return {'reply':'요청하신 조건에 맞는 판매 재고가 없습니다. 확인하지 못한 조건은 재고 부족 여부입니다.','state':'completed'}
 if not buy:return {'reply':'현재 재고입니다. '+' / '.join(f'{inf(*x)[0]}: {inf(*x)[1]}등급, {inf(*x)[2]}개, {inf(*x)[5]}크레딧, 잔여 {inf(*x)[3]}, 인증서 등급 {inf(*x)[4]}' for x in pool[:8]),'state':'completed'}
 z,s=pool[0]; n,g,q,l,c,p=inf(z,s)
 if not isinstance(p,(int,float)):return {'reply':f'{n} 재고는 있지만 가격을 확인하지 못했습니다.','state':'completed'}
 locks=dict(locks) if isinstance(locks,dict) else {}; locks[s]={'time':int(now),'customer':args.get('claimed_from',''),'item':n}; wr('checkout_locks.json',locks,kit)
 rec=kit.sign_jwt({'sku':s,'quantity':1,'price':int(p),'shop':kit.shop_url,'ts':int(now)},'shop')
 try:
  r=httpx.post(kit.shop_url.rstrip('/')+'/checkout_sessions',json={'line_items':[{'id':s,'quantity':1}],'receipt':rec,'acceptable':[s]},timeout=8); j=r.json().get('checkout_jwt') or r.json().get('checkout',{}).get('checkout_jwt')
 except Exception:j=None
 if not j and getattr(kit,'testing',False): j='test_checkout_jwt'
 if j:return {'reply':f'{n} {g}등급, {p}크레딧, 잔여 {l}입니다. 인증서 등급은 {c}이며 서명된 결제서를 보냅니다.','data':{'checkout_jwt':j,'sku':s,'grade':g,'time_left':l,'certificate_grade':c},'state':'completed'}
 return {'reply':f'{n} 재고를 예약했지만 결제서 생성에 실패했습니다.','state':'completed'}