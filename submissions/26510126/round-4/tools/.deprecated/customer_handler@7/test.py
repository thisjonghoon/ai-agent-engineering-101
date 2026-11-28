def test(run,kit):
 import json
 with open('test_card.json','w') as f:json.dump({'stock':{'G36ca7485':1}},f)
 with open('test_prices.json','w') as f:json.dump({'G36ca7485':{'price':5047}},f)
 with open('test_checkout_locks.json','w') as f:json.dump({},f)
 r=run({'text':'귤이나 사과 실제 재고 있나요? 사과 구매, 서명된 결제서 부탁'},kit)
 assert r.get('state')=='completed'
 assert 'checkout_jwt' in r.get('data',{})