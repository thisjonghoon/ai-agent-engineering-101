def test(run,kit):
 import json
 json.dump({'stock':{'A':{'quantity':2,'unit':'ua','grade':'B'},'F':{'quantity':2,'unit':'uf','grade':'C'},'K':{'quantity':2,'unit':'uk','grade':'A'}}},open('test_card.json','w'))
 json.dump({'A':{'name':'맛있는 사과','cost':5000},'F':{'name':'가자미 생선','cost':6000},'K':{'name':'김치','cost':7000}},open('test_catalog.json','w'));json.dump({},open('test_checkout_locks.json','w'))
 for q,s in [('사과 구매','A'),('가자미 사고 싶어요','F'),('김치 구매','K')]:
  a=run({'text':q},kit);assert a['data']['sku']==s and a['data']['price']>=a['data']['floor']
 assert json.load(open('test_checkout_locks.json'))=={}
