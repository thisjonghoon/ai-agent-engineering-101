def test(run,kit):
 if kit.testing: return
 assert 'status' in run({},kit)
