def test(run, kit):
    r=run({},kit)
    assert r['ok'] is True
    assert r['chars'] <= 3000
    assert r['rules_written'] is False
    return r
