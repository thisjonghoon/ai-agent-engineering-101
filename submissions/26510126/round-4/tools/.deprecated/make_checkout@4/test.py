def test(run,kit):
 import uuid
 u='test-'+uuid.uuid4().hex; a={'sku':'s','unit':u,'price':10000,'cost':5000,'cert':{'signature':'abc'},'claim':'B'}
 assert 'error' in run(dict(a,price=100),kit)
 x=run(a,kit); assert x['payload']['claim']=='B' and 'checkout_jwt' in x
 assert 'error' in run(a,kit)
 assert 'error' in run(dict(a,withdrawal_post=1),kit)
