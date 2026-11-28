def test(run,kit):
 import json
 json.dump({'stock':{'G05c7db55':1}},open('test_card.json','w'))
 json.dump({'G05c7db55':{'name':'혼합22곡','grade':'A','unit':'u22','cost':5000}},open('test_catalog.json','w'))
 json.dump({},open('test_checkout_locks.json','w'))
 a=run({'text':'혼합22곡 구매'},kit); assert a['data']['sku']=='G05c7db55' and a['data']['price']>=5263