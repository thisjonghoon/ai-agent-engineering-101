def test(run,kit):
 r=run({},kit)
 assert 'roles' in r and 'recent_replies' in r
