def test(run,kit):
 u=[{'name':'세탁세제','sku':'s','unit':'1','expires_at':9000,'grade':'B','cost':100}]
 assert '실측 B급' in run({'text':'세탁세제 있나요','_units':u},kit)['reply']
 assert '어느 품목' in run({'text':'계란과 두부 주세요','_units':[]},kit)['reply']
 assert '국수' not in run({'text':'두부 있으면 알려주세요','_units':[]},kit)['reply']
 assert '국수' not in run({'text':'게임용 모니터 있으면 알려주세요','_units':[]},kit)['reply']