def test(run, kit):
    r = run({'remove_test_line': True}, kit)
    assert r['ok']
    assert '새 교훈: 재고는 소량 시험 매입' not in r['text']
