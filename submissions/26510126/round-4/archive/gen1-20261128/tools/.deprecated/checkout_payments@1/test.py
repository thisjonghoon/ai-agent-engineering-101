def test(run,kit):
 r=run({'units':['nonexistent']},kit)
 assert r['complete'] is False and 'nonexistent' in r['hashes']
