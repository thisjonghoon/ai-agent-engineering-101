def test(run,kit):
 import json
 with open('test_card.json','w',encoding='utf-8') as f: json.dump({'stock':{'G045659e8':3}},f)
 with open('test_checkout_locks.json','w',encoding='utf-8') as f: json.dump({},f)
 r=run({'text':'국내산 손질 두절 가자미 4미 … 서명 결제서도 부탁','claimed_from':'이난임-60ba'},kit)
 assert r.get('data',{}).get('checkout_jwt')
 assert r['data']['sku']=='G045659e8'