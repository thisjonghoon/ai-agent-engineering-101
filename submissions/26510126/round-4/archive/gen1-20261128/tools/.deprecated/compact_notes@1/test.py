from pathlib import Path

def test(run, kit):
    Path('notes.md').write_text('old\n'+'x'*3100)
    r=run({'limit':3000},kit)
    saved=Path('notes.md').read_text()
    assert r['written'] is True
    assert len(saved)<=3000
    assert 'x' in saved
