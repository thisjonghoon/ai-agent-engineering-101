def test(run,kit):
 import json
 json.dump({'stock':{'G02f9f99c':{'quantity':3,'unit':'unit-k','grade':'A'}}},open('test_card.json','w'))
 json.dump({'G02f9f99c':{'name':'김치','grade':'A','cost':5000}},open('test_catalog.json','w'))
 json.dump({},open('test_checkout_locks.json','w'))
 a=run({'text':'김치 구매','claimed_from':'customer1'},kit)
 assert a['data']['sku']=='G02f9f99c' and a['data']['unit']=='unit-k'
 assert a['data']['price']>=5263
 assert '김치' in a['reply']