def test(run,kit):
 b={'sku':'s','unit':'1','expires_at':9000,'grade':'B','cost':100}
 assert '실측 B급' in run({'text':'세탁세제 있나요','_units':[dict(b,name='세탁세제')]},kit)['reply']
 assert '즉석조리식품' in run({'text':'즉석조리식품 1개 있나요','_units':[dict(b,name='사토노유키 실큰두부 300g 8팩',category='즉석조리식품')]},kit)['reply']
 assert '없어요' in run({'text':'게임용 모니터 있나요','_units':[dict(b,name='사과')]},kit)['reply']
 assert '여러 품목' in run({'text':'과일 있나요','_units':[dict(b,name='사과'),dict(b,unit='2',name='배')]},kit)['reply']