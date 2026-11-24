def test(run, kit):
    import os, json
    out = run({'description': '테스트 가게', 'skills': [{'id': 'ask', 'name': '문의', 'description': '재고 문의'}]}, kit)
    assert out['ok'] is True
    assert out['bytes'] > 0
