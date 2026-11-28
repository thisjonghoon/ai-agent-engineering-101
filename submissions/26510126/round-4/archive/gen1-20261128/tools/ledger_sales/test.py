def test(run,kit):
 o=run({'max':10,'sku':'G00c60e91'},kit); assert 'sales' in o and all(x['sku']=='G00c60e91' for x in o['sales'])