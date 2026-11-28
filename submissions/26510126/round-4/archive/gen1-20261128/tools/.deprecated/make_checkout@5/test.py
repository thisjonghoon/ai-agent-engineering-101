def test(run,kit):
 assert 'error' in run({'sku':'s','unit':'u','price':100,'cost':100},kit)
 r=run({'sku':'s','unit':'u-test-checkout','price':1000,'cost':100},kit)
 assert r.get('checkout_jwt') and r['payload']['unit']=='u-test-checkout'
 r=run({'sku':'s','unit':'u-test-checkout','price':1000,'cost':100},kit)
 assert 'error' in r
