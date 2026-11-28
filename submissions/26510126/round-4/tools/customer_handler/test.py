def test(run,kit):
 import json
 json.dump({'stock':[{'sku':'G36ca7485','name':'박수진 사과','quantity':2,'unit':'ua','cost':5000},{'sku':'G045659e8','name':'이난임 가자미','quantity':2,'unit':'uf','cost':6000},{'sku':'G35745411','name':'시금치','quantity':2,'unit':'us','cost':6000}]},open('test_card.json','w'));json.dump({},open('test_catalog.json','w'));json.dump({},open('test_checkout_locks.json','w'))
 assert run({'text':'박수진 사과 구매','claimed_from':'x'},kit)['data']['item']=='G36ca7485'
 assert run({'text':'이난임 22:51 가자미','claimed_from':'y'},kit)['data']['item']=='G045659e8'
 for x in ['남정욱 빵','튀김소보로','돼지고기 1kg','한돈 뒷다리살','이영구 김치','가정용 사과 2kg','혼합22곡','유태희 세탁세제']:
  assert 'data' not in run({'text':x,'claimed_from':'z'},kit)