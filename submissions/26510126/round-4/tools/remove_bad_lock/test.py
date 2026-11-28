def test(run,kit):
 import json
 with open('checkout_locks.json','w',encoding='utf-8') as f: json.dump({'G36ca7485':{'time':1},'KEEP':{'time':2}},f)
 r=run({'sku':'G36ca7485'},kit)
 assert r['removed']=='G36ca7485'
 assert json.load(open('checkout_locks.json'))=={'KEEP':{'time':2}}
