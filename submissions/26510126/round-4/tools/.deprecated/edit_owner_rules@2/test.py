def test(run, kit):
    r = run({'remove_today': True, 'append': '새 교훈: 테스트는 실제 파일을 건드리지 않는다'}, kit)
    assert r['ok']
    assert '요거트는 01:03' not in r['text']
    assert '01:40 우유·사과' not in r['text']
    assert '새 교훈' in r['text']
