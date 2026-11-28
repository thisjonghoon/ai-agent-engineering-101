def test(run,kit):
 import importlib.util
 s=importlib.util.spec_from_file_location('sales','tools/a2a_inquiry/logic.py'); m=importlib.util.module_from_spec(s); s.loader.exec_module(m)
 for i,(name,text) in enumerate([('시험 계란','계란 A등급 있나요?'),('시험 둥굴레차','둥굴레 차 A등급 있나요?')]):
  unit='u-test-only-'+str(i)
  u={'unit':unit,'sku':'G12345678','name':name,'category':name,'cost':1000,'grade':'A','expires_at':None,'cert':{'cert':{'unit':unit},'sig':'test'}}
  x=m.run({'text':text,'task_id':'test-task','_units':[u],'_ledger':[]},kit)
  assert x['state']=='completed' and x['data']['checkout_jwt'] and x['data']['checkout']['task']=='test-task',str(x)
  assert x['data']['checkout']['price'] >= (1210*100+98)//99
