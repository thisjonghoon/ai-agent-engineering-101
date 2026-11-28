def test(run,kit):
 r=run({'sku':'Gx','unit':'u1','price':1000,'cost':700,'_history':[]},kit)
 assert r.get('checkout_jwt') and r['payload']['unit']=='u1'
