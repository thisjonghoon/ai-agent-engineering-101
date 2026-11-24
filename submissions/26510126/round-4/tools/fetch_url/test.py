def test(run, kit):
    assert 'error' in run({'url': 'https://elsewhere.invalid/x'}, kit)
    assert 'error' in run({'url': kit.market + '.evil.invalid/x'}, kit)
    for path, words in [('/api/catalog', ['사과']), ('/api/agents', ['곽재천'])]:
        out = run({'url': kit.market + path, 'keywords': words, 'limit': 10}, kit)
        assert out['status'] == 200
        assert isinstance(out['items'], list)
        assert all(any(k in str(x.get('name', '')) or k in str(x.get('sku', '')) for k in words) for x in out['items'])
