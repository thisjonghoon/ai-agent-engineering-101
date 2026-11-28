def test(run,kit):
 import json
 json.dump({'stock':{'A':{'quantity':2,'unit':'ua'},'F':{'quantity':2,'unit':'uf'}}},open('test_card.json','w')); json.dump({'A':{'name':'맛있는 사과','cost':5000},'F':{'name':'가자미 생선','cost':6000}},open('test_catalog.json','w')); json.dump({},open('test_checkout_locks.json','w'))
 a=run({'text':'사과 구매'},kit); assert a['data']['sku']=='A'; assert 'data' not in run({'text':'돼지고기'},kit)