def test(run,kit):
 assert kit.testing
 o=run({'max':10},kit); assert 'by_sku' in o and 'sales' in o and 'last_seq' in o