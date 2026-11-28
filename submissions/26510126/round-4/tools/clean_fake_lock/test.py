def test(run,kit):
 import json
 with open('test_checkout_locks.json','w') as f:json.dump({'s1':{'item':'사과'},'keep':{'item':'보존'}},f)
 r=run({},kit); assert r['removed']=='s1'
 with open('test_checkout_locks.json') as f:x=json.load(f)
 assert 's1' not in x and 'keep' in x