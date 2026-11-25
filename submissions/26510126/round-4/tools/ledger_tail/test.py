def test(run,kit):
 assert run({'n':0},kit)['tail']==[]
 assert 'error' in run({'n':-1},kit)
 o=run({'n':3},kit); assert isinstance(o['tail'],list) and len(o['tail'])<=3
