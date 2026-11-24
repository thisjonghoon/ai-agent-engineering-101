from pathlib import Path

def test(run, kit):
    r = run({}, kit)
    s = Path('notes.md').read_text()
    assert r['written']
    assert '주인 jonghoon' in s
    assert '사과' in s
    assert len(s) <= 3000
