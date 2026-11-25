def test(run,kit):
 assert kit.testing
 o=run({'n':3},kit); assert 'tail' in o and isinstance(o['tail'],list)