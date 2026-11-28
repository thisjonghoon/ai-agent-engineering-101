import json
def test(run,kit):
 json.dump({'stock':{'S00':1}},open('test_card.json','w')); json.dump([{'sku':'S00','name':'사과','grade':'A','unit':'개','cost':100}],open('test_catalog.json','w')); json.dump({},open('test_checkout_locks.json','w'))
 a=run({'text':'사과 구매'},kit); assert a['data']['sku']=='S00' and a['data']['price']>=314
