def test(run, kit):
    r=run({},kit)
    assert 'windows' in r and '3h' in r['windows'] and '24h' in r['windows']
    assert 'sales_count' in r['windows']['3h']
