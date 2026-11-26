def test(run,kit):
 import uuid
 unit='test-'+uuid.uuid4().hex
 a={'sku':'s','unit':unit,'price':10000,'cost':5000,'cert':{'signature':'abc'},'claim':'B'}
 assert 'error' in run(dict(a,price=100),kit)
 first=run(a,kit); assert 'checkout_jwt' in first
 assert first['payload']['cert']==a['cert'] and first['payload']['claim']=='B'
 assert 'error' in run(a,kit)
