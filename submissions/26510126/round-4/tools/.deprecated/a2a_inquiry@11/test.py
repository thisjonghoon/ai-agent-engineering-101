def test(run,kit):
 assert run({'text':'환불해주세요'},kit)=={'defer':True}
 for text in ['세제 있나요?','우유 있나요?','둥굴레차 있나요?','둥굴레 차 있나요?']:
  x=run({'text':text,'_units':[],'_ledger':[]},kit)
  assert '없' in x['reply'] and x['state']=='completed'
