def test(run,kit):
 import json
 with open('test_checkout_locks.json','w') as f: json.dump({},f)
 r=run({'text':'사과 구매 결제서 부탁'},kit)
 assert r.get('state')=='completed'
 assert r.get('data',{}).get('checkout_jwt')
 assert r['data']['checkout_jwt']!='test_checkout_jwt'