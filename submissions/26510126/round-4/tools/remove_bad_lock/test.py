def test(run,kit):
 import json
 json.dump({'u-bad':{'sku':'S'},'KEEP':{'time':2}},open('checkout_locks.json','w'))
 r=run({'unit':'u-bad'},kit); assert r['removed']=='u-bad'; assert 'u-bad' not in json.load(open('checkout_locks.json'))