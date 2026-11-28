#!/opt/homebrew/bin/python3.15
"""11/28 00:31:45 KST 스냅샷으로 extract.py를 다시 돌려 원래 커밋(46c691e) 산출물과 비교한다.

    /opt/homebrew/bin/python3.15 failure-lab/snapshot_check.py <작업 디렉터리>

46c691e 산출물은 Python 3.15에서 만들어졌다. 3.15는 연도 없는 '%m/%d' 파싱을 거부하므로 넛지 시각이
로그 기록 시각으로 남는다. 다른 판 파이썬에서는 넛지 시각이 달라져 바이트 비교가 어긋날 수 있다.

살아 있는 로그는 읽기만 한다. 각 로그를 ts가 기준 시각 이하인 마지막 행까지 잘라(행 번호 보존)
작업 디렉터리에 복사하고, 46c691e 판 extract.py를 ROOT·OUT만 바꿔 실행한다. Git은 원래 저장소에서 읽는다.
지금 extract.py에 규칙을 보태도 474건 재현은 바뀌지 않는다.
failure-lab/의 기존 산출물은 건드리지 않는다.
"""
from datetime import datetime, timedelta, timezone
from pathlib import Path
import importlib.util
import json
import shutil
import subprocess
import sys

sys.dont_write_bytecode = True
if sys.version_info[:2] != (3, 15):
    print(f'주의: Python {sys.version_info.major}.{sys.version_info.minor}. 474건 재현 기준은 /opt/homebrew/bin/python3.15다.')
KST = timezone(timedelta(hours=9))
CUT = datetime(2026, 11, 28, 0, 31, 45, tzinfo=KST).timestamp()
BASE = '46c691e'
FILES = ['logs/react.jsonl', 'logs/talk.jsonl', 'logs/forge.jsonl', 'logs/ledger.jsonl',
         '.kit/chat.jsonl', 'logs/nudges.jsonl', 'checkout_withdrawals.jsonl', 'auto_checkout.jsonl']
OUTPUTS = ['incidents.jsonl', 'interventions.md', 'taxonomy.md', 'summary.json']

root = Path(__file__).resolve().parent.parent
work = Path(sys.argv[1]).resolve()
data, out = work / 'root', work / 'out'
out.mkdir(parents=True, exist_ok=True)


def git(*args):
    return subprocess.run(['git', *args], cwd=root, text=True, capture_output=True, check=False).stdout


for name in FILES:
    src = root / name
    if not src.exists():
        continue
    lines = src.read_bytes().splitlines(keepends=True)
    keep = 0
    for index, raw in enumerate(lines, 1):
        try:
            ts = json.loads(raw).get('ts')
        except ValueError:
            continue
        if ts is None or ts <= CUT:
            keep = index
    (data / name).parent.mkdir(parents=True, exist_ok=True)
    (data / name).write_bytes(b''.join(lines[:keep]))
    print(f'{name}: {keep}/{len(lines)}행 사용')
shutil.copy(root / 'logs/agent-kit.log', data / 'logs/agent-kit.log')

# 474건은 46c691e 시점 추출기의 결과다. 이후 extract.py에 규칙을 보태도 이 재현은 바뀌지 않도록
# 추출기도 같은 커밋 판을 쓴다.
pinned = work / 'extract_46c691e.py'
pinned.write_text(git('show', f'{BASE}:./failure-lab/extract.py'))
spec = importlib.util.spec_from_file_location('extract', pinned)
extract = importlib.util.module_from_spec(spec)
spec.loader.exec_module(extract)
extract.ROOT, extract.OUT, extract.git = data, out, git
original_goals = extract.goals
extract.goals = lambda: [g for g in original_goals() if g['ts'] <= CUT]
extract.main()

summary = json.loads((out / 'summary.json').read_text())
print('through', summary['through'], '사건', sum(1 for _ in open(out / 'incidents.jsonl')),
      '개입', len(summary['interventions']))
for name in OUTPUTS:
    same = git('show', f'{BASE}:./failure-lab/{name}') == (out / name).read_text()
    print(f'{name}: {BASE}와 ' + ('동일' if same else '다름'))
