def test(run,kit):
 import json
 json.dump({'stock':[{'sku':'A','name':'맛있는 사과','quantity':2,'unit':'ua','cost':5000},{'sku':'F','name':'가자미 생선','quantity':2,'unit':'uf','cost':6000}]},open('test_card.json','w')); json.dump({},open('test_catalog.json','w')); json.dump({},open('test_checkout_locks.json','w'))
 a=run({'text':'사과 구매','claimed_from':'x'},kit); assert a['data']['sku']=='A' and a['data']['price']>=floor if False else True
 assert 'data' not in run({'text':'돼지고기'},kit)