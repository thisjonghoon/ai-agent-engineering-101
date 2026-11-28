import json
def test(run,kit):
 json.dump({'stock':{'S00':1,'S01':1,'S02':1}},open('test_card.json','w'))
 json.dump([{'sku':'S00','name':'사과','grade':'A','unit':'개','cost':100},{'sku':'S01','name':'배','grade':'B','unit':'개','cost':100},{'sku':'S02','name':'손질 가자미 특대','grade':'A','unit':'팩','cost':5000}],open('test_catalog.json','w'))
 json.dump({'S00':{'price':314},'S01':{'price':314},'S02':{'price':6000}},open('prices.json','w')); json.dump({},open('test_checkout_locks.json','w'))
 a=run({'text':'사과 구매'},kit); assert a['data']['sku']=='S00' and a['data']['price']>=314
 assert len(json.load(open('test_catalog.json')))==3
 json.dump({},open('test_checkout_locks.json','w')); b=run({'text':'순살 연어구이 240g 구매'},kit); assert 'checkout_jwt' not in b.get('data',{}) and not json.load(open('test_checkout_locks.json'))
 json.dump({},open('test_checkout_locks.json','w')); c=run({'text':'손질 가자미 특대 구매'},kit); assert c['data']['price']>=int((5000+210)/.99)+1
