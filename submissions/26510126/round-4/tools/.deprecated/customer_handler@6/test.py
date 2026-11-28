def test(run,kit):
 import json
 with open('test_card.json','w') as f:json.dump({'stock':[{'sku':'s1','item':'사과','grade':'A','quantity':1,'time_left':'2일','certificate_grade':'미확인'},{'sku':'s2','item':'배','grade':'B','quantity':1,'time_left':'1일'}]},f)
 with open('test_prices.json','w') as f:json.dump({'s1':{'price':1200},'s2':{'price':900}},f)
 with open('test_checkout_locks.json','w') as f:json.dump({},f)
 assert '1200' in run({'text':'사과 있나요?'},kit)['reply']
 assert run({'text':'사과 구매, 서명된 결제서 부탁'},kit)['state']=='completed'
 assert '없습니다' in run({'text':'용과 구매'},kit)['reply']