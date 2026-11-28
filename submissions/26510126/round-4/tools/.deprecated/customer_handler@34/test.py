def test(run,kit):
 import json
 json.dump({'stock':{'S00':1}},open('test_card.json','w'))
 json.dump([{'sku':'S00','name':'한상궁김치 총각김치','aliases':['김치'],'grade':'A','unit':'팩','cost':100}],open('test_catalog.json','w'))
 json.dump({},open('test_checkout_locks.json','w'))
 a=run({'text':'김치 구매'},kit)
 assert a['data']['sku']=='S00' and a['data']['price']>=314