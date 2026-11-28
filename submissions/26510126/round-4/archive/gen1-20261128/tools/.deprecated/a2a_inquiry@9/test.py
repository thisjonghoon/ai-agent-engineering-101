def test(run,kit):
 assert run({'text':'환불해주세요'},kit)=={'defer':True}
 x=run({'text':'세제 있나요?','_units':[],'_ledger':[]},kit)
 assert '없' in x['reply'] and x['state']=='completed'
