def test(run, kit):
    assert 'error' in run({'url': 'https://elsewhere.invalid/x'}, kit)
    assert 'error' in run({'url': kit.market + '.evil.invalid/x'}, kit)
    if kit.testing:
        out = run({'url': kit.market + '/api/catalog', 'keywords': ['사과', 'G0a213975', '계란', '앞다리'], 'limit': 10}, kit)
        assert out['status'] == 200
        assert isinstance(out['items'], list)
        assert all(any(k in str(x.get('name', '')) or k in str(x.get('sku', '')) for k in ['사과', 'G0a213975', '계란', '앞다리']) for x in out['items'])
