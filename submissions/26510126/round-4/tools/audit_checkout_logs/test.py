def test(run,kit):
 r=run({'unit':'nonexistent'},kit)
 assert 'comparisons' in r
