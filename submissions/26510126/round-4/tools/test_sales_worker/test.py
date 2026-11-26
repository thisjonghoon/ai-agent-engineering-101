def test(run,kit):
 import importlib.util
 s=importlib.util.spec_from_file_location('sales','tools/a2a_inquiry/logic.py'); m=importlib.util.module_from_spec(s); s.loader.exec_module(m)
 u={'unit':'u-test-only','sku':'G12345678','name':'시험 계란','category':'계란','cost':1000,'grade':'A','expires_at':None,'cert':{'cert':{'unit':'u-test-only'},'sig':'test'}}
 x=m.run({'text':'계란 A등급 있나요?','task_id':'test-task','_units':[u],'_ledger':[]},kit)
 assert x['state']=='completed' and x['data']['checkout_jwt'] and x['data']['checkout']['task']=='test-task',str(x)
 assert x['data']['checkout']['price'] >= (1210*100+98)//99
