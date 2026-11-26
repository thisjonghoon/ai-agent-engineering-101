def test(run,kit):
 import logic
 es=[{'kind':'join','data':{'role':'shop','name':'a','url':'https://old'}},{'kind':'settle','data':{'shop':'https://old','amount':7}},{'kind':'settle','data':{'shop':'https://new','amount':3}},{'kind':'supply','data':{'shop':'a','qty':2,'total':4}}]
 s,u,x=logic.aggregate(es,[{'name':'a','url':'https://new'}]); assert s['a']['settle']==2 and s['a']['sale_amount']==10 and s['a']['supply_qty']==2 and not x
