import time
def test(run,kit):
 u={'name':'총각김치 2kg','sku':'kimchi','unit':'u1','grade':'B','cost':9000,'expires_at':time.time()+100000}
 assert run({'text':'배추김치 필요해서요… 총각김치는 안 삽니다','_units':[u]},kit).get('defer') is True
 assert run({'text':'우유 24팩보다 작은 것','_units':[u]},kit).get('defer') is True
