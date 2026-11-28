from pathlib import Path

def test(run, kit):
    Path('owner_rules.md').write_text('지속 규칙\n요거트는 01:03 이후 철회\n01:40 우유·사과 마감 할인 검토\n', encoding='utf-8')
    r = run({'remove_today': True, 'append': '새 교훈: 재고는 소량 시험 매입'}, kit)
    s = Path('owner_rules.md').read_text(encoding='utf-8')
    assert r['ok']
    assert '지속 규칙' in s
    assert '요거트는 01:03' not in s
    assert '01:40 우유·사과' not in s
    assert '새 교훈' in s
