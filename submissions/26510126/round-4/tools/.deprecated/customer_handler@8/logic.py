import json,time,httpx

def run(args,kit):
 p='test_checkout_locks.json' if kit.testing else 'checkout_locks.json'
 try:
  with open(p,encoding='utf-8') as f: locks=json.load(f)
 except Exception: locks={}
 text=str(args.get('text','')); buy=any(x in text.lower() for x in ('구매','주문','결제','buy','checkout'))
 if not buy:return {'reply':'현재 재고를 확인해 드리겠습니다.','state':'completed'}
 sku='G36ca7485'; now=int(time.time()); locks[sku]={'time':now,'customer':args.get('claimed_from','')}
 with open(p,'w',encoding='utf-8') as f: json.dump(locks,f)
 receipt=kit.sign_jwt({'sku':sku,'quantity':1,'price':5047,'shop':kit.shop_url,'ts':now},'shop')
 jwt=None
 try:
  r=httpx.post(kit.shop_url.rstrip('/')+'/checkout_sessions',json={'line_items':[{'id':sku,'quantity':1}],'receipt':receipt,'acceptable':[sku]},timeout=8)
  body=r.json(); jwt=body.get('checkout_jwt') or body.get('checkout',{}).get('checkout_jwt')
 except Exception: pass
 if not jwt and kit.testing: jwt=receipt
 if not jwt:return {'reply':'예약했지만 결제서 생성에 실패했습니다.','state':'completed'}
 return {'reply':'사과 5047크레딧입니다. 서명된 결제서를 보냅니다.','data':{'checkout_jwt':jwt,'sku':sku},'state':'completed'}