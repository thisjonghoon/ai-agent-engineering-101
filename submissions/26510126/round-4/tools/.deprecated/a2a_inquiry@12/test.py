def test(run,kit):
 import time,importlib.util,types
 assert run({'text':'환불해주세요'},kit)=={'defer':True}
 assert '없' in run({'text':'우유 있나요?','_units':[],'_ledger':[]},kit)['reply']
 original=importlib.util.spec_from_file_location
 class Loader:
  def create_module(self,spec): return None
  def exec_module(self,mod):
   mod.run=lambda a,k:{'checkout_jwt':'test','payload':{'id':'co-test','task':a['task']}}
 def fake(name,path):
  return importlib.util.spec_from_loader(name,Loader())
 importlib.util.spec_from_file_location=fake
 try:
  now=int(time.time()); units=[{'name':'취나물','sku':'G159be1f8','unit':'short','cost':100,'grade':'B','expires_at':now+3600},{'name':'취나물','sku':'G159be1f8','unit':'long','cost':100,'grade':'B','expires_at':now+90000}]
  x=run({'text':'취나물 B등급 주세요','task_id':'test','_units':units,'_ledger':[]},kit)
  assert x['data']['checkout']['id']=='co-test' and '1일' in x['reply'] and '실물 소비기한' not in x['reply'] and 'B등급' in x['reply'],x
  print('시험 답장 원문: '+x['reply'])
 finally: importlib.util.spec_from_file_location=original
