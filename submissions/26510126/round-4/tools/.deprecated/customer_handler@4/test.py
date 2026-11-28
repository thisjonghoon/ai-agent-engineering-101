def test(run,kit):
 import json
 with open('card.json','w') as f:json.dump({'stock':[{'sku':'s1','item':'사과','grade':'A','quantity':1,'time_left':'2일'}]},f)
 with open('prices.json','w') as f:json.dump({'s1':{'price':1200,'grade':'A'}},f)
 with open('checkout_locks.json','w') as f:json.dump({},f)
 assert '1200' in run({'text':'사과 있나요?'},kit)['reply']
 assert run({'text':'사과 구매'},kit)['state']=='completed'
