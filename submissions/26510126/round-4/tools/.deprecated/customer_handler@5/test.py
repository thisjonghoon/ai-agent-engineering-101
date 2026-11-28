def test(run,kit):
 import json
 with open('card.json','w') as f: json.dump({'stock':[{'sku':'s1','item':'사과','grade':'A','quantity':1,'time_left':'2일','certificate_grade':'미확인'},{'sku':'s2','item':'배','grade':'B','quantity':1,'time_left':'1일'}]},f)
 with open('prices.json','w') as f: json.dump({'s1':{'price':1200},'s2':{'price':900}},f)
 with open('checkout_locks.json','w') as f: json.dump({},f)
 a=run({'text':'사과 있나요?'},kit); assert '사과' in a['reply'] and '1200' in a['reply']
 b=run({'text':'사과 구매, 서명된 결제서 부탁'},kit); assert b['state']=='completed' and ('결제서' in b['reply'] or '실패' in b['reply'])
 c=run({'text':'용과 구매, 서명된 결제서 부탁'},kit); assert '없습니다' in c['reply'] and '결제서' not in c.get('data',{})