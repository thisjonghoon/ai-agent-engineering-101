def test(run,kit):
 import json
 json.dump({'stock':{'G02f9f99c':3}},open('test_card.json','w'))
 json.dump({'G02f9f99c':{'name':'김치','grade':'A','unit':'u','cost':5000}},open('test_catalog.json','w'))
 json.dump({},open('test_checkout_locks.json','w'))
 a=run({'text':'김치 구매','claimed_from':'customer1'},kit)
 assert a.get('data',{}).get('sku')=='G02f9f99c'
 assert a['data']['price']>=5263
 assert a['data']['unit']=='u'
 assert '김치' in a['reply']