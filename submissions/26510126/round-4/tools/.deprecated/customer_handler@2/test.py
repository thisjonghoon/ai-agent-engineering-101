def test(run,kit):
 import json
 with open('card.json','w') as f:json.dump({'stock':[{'id':'s1','sku':'s1','item':'사과','grade':'A','quantity':1,'price':1200,'time_left':'2일'}]},f)
 assert '사과' in run({'text':'사과 있나요?'},kit)['reply']
 r=run({'text':'사과 구매','claimed_from':'c'},kit);assert r['state']=='completed'
