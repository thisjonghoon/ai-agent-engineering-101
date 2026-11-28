def test(run,kit):
 assert run({'text':'환불해주세요'},kit)=={'defer':True}
 assert '없' in run({'text':'우유 있나요?','_units':[],'_ledger':[]},kit)['reply']
 print('strict inquiry test passed')