import time

def test(run,kit):
 now=int(time.time())
 units=[{'unit':'n','sku':'S','name':'계란','grade':'B','cost':1,'expires_at':now+9999},
        {'unit':'v','sku':'S','name':'계란','grade':'B','cost':1,'expires_at':now+9999},
        {'unit':'l','sku':'S','name':'계란','grade':'B','cost':1,'expires_at':now+9999}]
 r=run({'_units':units,'_last':{'v':now-11000,'l':now-3600}},kit)
 assert (r['never_issued'],r['voidable'],r['live_checkout'],r['sellable_now'])==(1,1,1,2)
 assert r['groups'][0]['units'][2]['live_until']==now-3600+10800
 return 'ok'
