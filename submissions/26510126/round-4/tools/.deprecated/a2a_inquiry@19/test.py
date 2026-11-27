def test(run,kit):
 import time
 u={'sku':'pork','unit':'u1','name':'돼지고기','grade':'B','cost':1000,'expires_at':time.time()+7200,'cert':{'x':1}}
 r=run({'text':'돼지고기 1kg 구매 부탁','_units':[u]},kit)
 assert r.get('state')=='completed'
 assert r.get('data',{}).get('checkout_jwt') or '발급' in r.get('reply','')