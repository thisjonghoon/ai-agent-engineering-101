def test(run,kit):
 import json
 with open('test_checkout_locks.json','w',encoding='utf-8') as f: json.dump({},f)
 r=run({'text':'귤이나 사과 구매 결제서 부탁','claimed_from':'박수진'},kit)
 assert r.get('data',{}).get('checkout_jwt')
 assert r.get('data',{}).get('sku')=='G36ca7485'
 with open('test_checkout_locks.json',encoding='utf-8') as f: assert 'G36ca7485' in json.load(f)
 with open('test_checkout_locks.json','w',encoding='utf-8') as f: json.dump({},f)
 r=run({'text':'신선한 생선 구매 서명 결제서 보내 주세요','claimed_from':'이난임-60ba'},kit)
 assert not r.get('data',{}).get('checkout_jwt')
 with open('test_checkout_locks.json',encoding='utf-8') as f: assert 'G36ca7485' not in json.load(f)
