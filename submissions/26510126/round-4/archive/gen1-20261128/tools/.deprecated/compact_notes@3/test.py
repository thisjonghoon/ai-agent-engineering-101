def test(run, kit):
    r=run({},kit)
    assert r['ok'] is True
    assert r['chars'] <= 3000
    assert r['rules_chars'] > 0
    return r
