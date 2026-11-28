def test(run,kit):
 import json
 json.dump({'stock':{'G05c7db55':1,'G36ca7485':1}},open('test_card.json','w'))
 json.dump([{'sku':'G05c7db55','name':'혼합22곡 4kg','aliases':['혼합22곡'],'grade':'A','unit':'u22','cost':5000},{'sku':'G36ca7485','name':'사과','aliases':['사과'],'grade':'B','unit':'u36','cost':900}],open('test_catalog.json','w'))
 json.dump({},open('test_checkout_locks.json','w'))
 a=run({'text':'혼합22곡 4kg 찾습니다'},kit); assert a['data']['sku']=='G05c7db55' and a['data']['unit']=='u22'
 b=run({'text':'사과 구매'},kit); assert b['data']['sku']=='G36ca7485'
 c=run({'text':'없는 SKU Z99 구매'},kit); assert 'data' not in c or 'checkout_jwt' not in c.get('data',{})