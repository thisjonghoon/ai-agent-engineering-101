"""가게 기록을 읽어 실패 연구 자료를 다시 만든다."""
from bisect import bisect_left, bisect_right
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
import json
import re
import subprocess
from statistics import median

OUT = Path(__file__).resolve().parent
ROOT = OUT.parent
KST = timezone(timedelta(hours=9))
TYPES = {
    'time': '시간 예산과 응답 경로',
    'interface': '메시지 식별자와 호출 계약',
    'tests': '도구 변경과 회귀 검증',
    'memory': '실행 간 주인 지시 보존',
    'policy': '판매 규칙과 집행 경로',
    'meaning': '단위와 데이터 의미',
    'market': '시장 시간창과 재고 수명',
    'execution': '지시 기록과 실행의 분리',
    'data': '데이터 위치·형식 착각',
    'inverse': '거절 조건 역방향 실행',
    'unknown': '원인 미확인',
}
MISSING = Counter()
SNAPSHOT = datetime(2026, 11, 28, 0, 31, 45, tzinfo=KST).timestamp()  # 474건 기준(커밋 46c691e)
OBS_LIMIT = 6000  # kit/agent_kit.py 68행: 모델이 보는 관찰 길이
DIRECTIVE = re.compile(r'(?:하|두|내|고치|되돌리|사|지키|말|읽|맞추|바꾸|넣|남기|적|빼|보|알리|확인하|만들|압축하|팔|쓰|멈추|정하)게'
                       r'(?:[.,!\s]|$)|하지 말')


def load(file):
    rows = []
    path = ROOT / file
    if not path.exists():
        MISSING[file] += 1
        return rows
    for line, raw in enumerate(path.read_bytes().splitlines(), 1):
        try:
            row = json.loads(raw)
        except (ValueError, UnicodeError):
            MISSING[file] += 1
            continue
        row['ref'] = {'file': file, 'line': line}
        rows.append(row)
    return rows


def iso(ts):
    return datetime.fromtimestamp(ts, KST).isoformat(timespec='seconds')


def git(*args):
    return subprocess.run(['git', *args], cwd=ROOT, text=True,
                          capture_output=True, check=False).stdout


def observation(row):
    raw = row.get('observation', '')
    try:
        data = json.loads(raw)
        result = data.get('result')
        return result if isinstance(result, dict) else data
    except ValueError:
        return {}


def mdref(ref):
    file = ref['file']
    line = ref.get('line')
    return f'[{file}' + (f' {line}행](../{file}#L{line})' if line else f'](../{file})')


def dump(name, value):
    (OUT / name).write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n')


def write(name, value):
    (OUT / name).write_text(value.rstrip() + '\n')


def latest(rows, ts):
    index = bisect_right(rows, ts, key=lambda r: r['ts'])
    return rows[index - 1] if index else None


def between(rows, start, end):
    index = bisect_left(rows, start, key=lambda r: r['ts'])
    for row in rows[index:]:
        if row['ts'] >= end:
            break
        yield row


def topic(message):
    groups = [
        ('memory', r'메모|notes|owner_rules|주인 지시|compact'),
        ('time', r'80초|같은 대화|대화가 닫|응답 시간|busy|답장 안'),
        ('meaning', r'tOKRW|단위|정산가|정가|순위|잔액|list_price'),
        ('market', r'매입|재입고|폐기|restock'),
        ('interface', r'메시지 id|task.id|reply.*id'),
        ('tests', r'defer|등급|grade|테스트|forge|a2a_inquiry'),
        ('policy', r'결제서|정산|checkout|잠금|원장|철회'),
    ]
    return next((kind for kind, pattern in groups if re.search(pattern, message, re.I)), None)


def goals():
    result = []
    previous = None
    for record in git('log', '--reverse', '--format=%H %at', '--', 'agent.json').splitlines():
        sha, epoch = record.split()
        try:
            config = json.loads(git('show', f'{sha}:./agent.json'))
        except ValueError:
            continue
        goal = config.get('goal', '')
        if goal != previous:
            result.append({'ts': int(epoch), 'ref': {'file': 'agent.json', 'commit': sha},
                           'goal_chars': len(goal), 'topic': None})
        previous = goal
    return result


def starts(first_ts, last_ts):
    path = ROOT / 'logs/agent-kit.log'
    day = datetime.fromtimestamp(first_ts, KST).replace(hour=0, minute=0, second=0, microsecond=0)
    previous = None
    result = []
    for line, text in enumerate(path.read_text().splitlines(), 1):
        hit = re.match(r'^(\d\d):(\d\d):(\d\d) ', text)
        if not hit:
            continue
        hour, minute, second = map(int, hit.groups())
        clock = hour * 3600 + minute * 60 + second
        if previous is not None and previous - clock > 12 * 3600:
            day += timedelta(days=1)
        previous = clock
        if '[kit] agent_kit v' in text:
            ts = day.timestamp() + clock
            if ts <= last_ts:
                result.append({'ts': ts, 'ref': {'file': 'logs/agent-kit.log', 'line': line},
                               'topic': None})
    return result


def activity(row):
    action = row['action']
    thought = row.get('thought') or ''
    if action in {'make_checkout', 'a2a_inquiry'} or (
        action == 'reply' and not re.search(r'조언|주인|사장님|넛지', thought)
    ):
        return '판매'
    if action in {'forge_tool', 'read_tool', 'test_sales_worker', 'compact_notes', 'edit_owner_rules', 'restore_notes'}:
        return '수선'
    if action in {'sleep', 'write_note', 'app_say', 'buy_stock', 'write_card'}:
        return {'sleep': '휴식 전환', 'buy_stock': '매입'}.get(action, '운영')
    return '조사'


def purchase_intent(row):
    return bool(re.search(r'재고|등급|결제서|checkout|구매|있나요|살 수', row['text'], re.I))


def checkout_text(row):
    reply = row['reply']
    return bool(re.search(r'결제서를 (?:함께 |바로 |지금 )?(?:보냅니다|보내요|보내드려요|드립니다|첨부했습니다)|서명된 결제서입니다', reply))


def directive(row):
    """주인 이름의 명령형 지시. 질문·승인·감사 같은 주인 채팅과 구분한다."""
    return bool(DIRECTIVE.search(row.get('text', '')))


def directive_topic(message):
    for kind, pattern in (('inverse', r'조건|A등급|등급만|기한 넉넉|말고|빼고'),
                          ('market', r'매입|창구|buy_stock|429|사게|사라'),
                          ('memory', r'메모|notes|compact|owner_rules'),
                          ('tests', r'a2a_inquiry|판을|되돌리|시험|고치게')):
        if re.search(pattern, message):
            return kind
    return topic(message)


def aliases(version):
    """그 판의 ALIASES 사전. tools/.deprecated/<도구>@<판>/logic.py 또는 현재 판에서 읽는다."""
    import ast
    for path in (ROOT / f'tools/.deprecated/a2a_inquiry@{version}/logic.py', ROOT / 'tools/a2a_inquiry/logic.py'):
        if not path.exists():
            continue
        if path.parent.name == 'a2a_inquiry':
            try:
                if json.loads((path.parent / 'forge.json').read_text()).get('version') != version:
                    continue
            except (OSError, ValueError):
                continue
        for number, line in enumerate(path.read_text().splitlines(), 1):
            if line.startswith('ALIASES='):
                try:
                    return ast.literal_eval(line.split('=', 1)[1]), path.relative_to(ROOT).as_posix(), number
                except (ValueError, SyntaxError):
                    return None
    return None


def remaining_hours(reply):
    hit = re.search(r'약 (\d+)시간 (\d+)분', reply)
    return int(hit.group(1)) + int(hit.group(2)) / 60 if hit else None


def condition_breaks(question, reply):
    """손님이 문의에 적은 제외·요구 조건과 결제서를 낸 답이 어긋나는 항목."""
    out = []
    grade = re.search(r'(?:실제 재고 등급은|실측) ([ABC])', reply)
    grade = grade.group(1) if grade else None
    left = remaining_hours(reply)
    if grade and grade != 'A' and re.search(r'A\s?등급(?:이)? ?(?:아니면|만)|A등급 \d개|A급만', question):
        out.append(f'A등급 요구에 {grade}급')
    if grade == 'C' and re.search(r'C\s?(?:등급|급)[^.]{0,12}(?:제외|빼|안 살|말고|싫|안 사)', question):
        out.append('C등급 제외에 C급')
    if re.search(r'소량|낱개|1~2팩|대용량은 피', question) and re.search(r'24팩|대용량', reply):
        out.append('소량 요구에 대용량')
    if left is not None and left < 24 and re.search(r'넉넉|기한 짧은 건 안|임박[^.]{0,6}(?:제외|싫|안)', question):
        out.append(f'넉넉한 기한 요구에 {left:.1f}시간')
    asked, offered = re.search(r'(\d{3,4})\s?g', question), re.search(r'(\d{3,4})\s?g', reply)
    if asked and offered and asked.group(1) != offered.group(1):
        out.append(f'{asked.group(1)}g 요구에 {offered.group(1)}g')
    return out


def main():
    react = sorted(load('logs/react.jsonl'), key=lambda r: r['ts'])
    talk = sorted(load('logs/talk.jsonl'), key=lambda r: r['ts'])
    forge = sorted(load('logs/forge.jsonl'), key=lambda r: r['ts'])
    ledger = sorted(load('logs/ledger.jsonl'), key=lambda r: r['ts'])
    chat = sorted(load('.kit/chat.jsonl'), key=lambda r: r['ts'])
    nudges = load('logs/nudges.jsonl')
    for row in nudges:
        # 연도를 붙여 파싱한다. 연도 없는 '%m/%d'는 Python 3.15부터 ValueError라 46c691e 판(474건)은
        # 전송 표기 시각 대신 로그 기록 시각(답을 기다린 뒤)을 썼다.
        year = datetime.fromtimestamp(row['ts'], KST).year
        try:
            sent = datetime.strptime(f"{year}/{row['time']}", '%Y/%m/%d %H:%M:%S')
        except (KeyError, ValueError):
            continue
        row['ts'] = sent.replace(tzinfo=KST).timestamp()
    nudges.sort(key=lambda r: r['ts'])
    withdrawals = load('checkout_withdrawals.jsonl')
    auto = load('auto_checkout.jsonl')
    goal = goals()
    cutoff = max(rows[-1]['ts'] for rows in (react, talk, forge, ledger, chat, nudges) if rows)
    restart = starts(react[0]['ts'], cutoff)
    versions = defaultdict(list)
    for row in forge:
        if row['passed']:
            versions[row['tool']].append(row)
    owner = [r for r in chat if r['who'] == 'jonghoon']
    incidents = []
    seen = set()

    def emit(row, kind, category, description, *, extra=(), cost=None, low=False,
             customer=None, item=None, tool=None, state=None, repeat_key=None):
        ref = row['ref']
        ts = row['ts']
        if f"{Path(ref['file']).stem}-{ref['line']}-{kind}" in seen:
            return  # 지정 사례가 먼저 잡은 행은 일반 규칙이 다시 세지 않는다
        seen.add(f"{Path(ref['file']).stem}-{ref['line']}-{kind}")
        mind = state or latest(react, ts)
        context = []
        for label, rows in [('넛지', nudges), ('주인 채팅', owner), ('goal 커밋', goal), ('키트 시작', restart)]:
            eligible = [r for r in rows if r['ts'] <= ts and
                        (label not in {'넛지', '주인 채팅'} or category == topic(r.get('text', '')))]
            if eligible:
                prior = eligible[-1]
                context.append({'kind': label, 'ts': iso(prior['ts']), **prior['ref']})
        for name in dict.fromkeys(filter(None, (tool, 'a2a_inquiry'))):
            prior = latest(versions[name], ts)
            if prior:
                context.append({'kind': '도구 시험 통과', 'tool': name, 'version': prior['version'],
                                'ts': iso(prior['ts']), **prior['ref']})
        ident = f"{Path(ref['file']).stem}-{ref['line']}-{kind}"
        entry = {'id': ident, 'ts': iso(ts), 'epoch': ts, 'kind': kind, 'type': category,
                 'description': description, 'evidence': [ref, *extra], 'cost': cost or {},
                 'agent_state': {'action': mind['action'], 'activity': activity(mind),
                                 'evidence': mind['ref']} if mind else None,
                 'preceded_by': context, 'confidence': 'low' if low else 'high',
                 'repeat_of': None, '_repeat': repeat_key or kind}
        if customer:
            entry['customer'] = customer
        if item:
            entry['item'] = item
        incidents.append(entry)

    alias_cache = {}

    def alias_table(row):
        version = latest(versions['a2a_inquiry'], row['ts'])
        if not version:
            return None, None
        if version['version'] not in alias_cache:
            alias_cache[version['version']] = aliases(version['version'])
        found = alias_cache[version['version']]
        return (found[0] if found else None), version['version']

    def alternatives(row):
        """'우유나 요거트'처럼 사전에 걸린 품목이 모두 'A나 B' 한 구절 안에 있는 문의."""
        table = alias_table(row)[0]
        phrase = re.search(r'[가-힣]{2,}(?:이나|나) [가-힣]{2,}', row['text'])
        if not table or not phrase:
            return False
        hit = [k for k, words in table.items() if any(len(w) >= 2 and w in row['text'] for w in words)]
        return len(hit) >= 2 and all(any(len(w) >= 2 and w in phrase.group(0) for w in table[k]) for k in hit)

    def alias_collision(row):
        """자동 응대가 고른 품목이 한 글자 별칭의 부분 문자열 일치에서만 나왔는지 본다."""
        version = latest(versions['a2a_inquiry'], row['ts'])
        if not version:
            return None
        number = version['version']
        if number not in alias_cache:
            alias_cache[number] = aliases(number)
        if not alias_cache[number]:
            return None
        table, path, line = alias_cache[number]
        named = re.search(r'맞는 ([가-힣A-Za-z]+) 재고가 지금 없어요|^([가-힣A-Za-z]+) 재고 없어요', row['reply'])
        if not named and '여러 품목을 함께' not in row['reply']:
            return None
        for category in ([named.group(1) or named.group(2)] if named else list(table)):
            hits = [w for w in table.get(category, []) if w in row['text']]
            if hits and all(len(w) == 1 for w in hits) and category not in row['text']:
                return {'category': category, 'hits': hits, 'version': number, 'ref': {'file': path, 'line': line}}
        return None

    busy = []
    for row in talk:
        reply = row['reply']
        preceding = list(between(react, row['ts'] - 81, row['ts'] + 1))
        defers = [r for r in preceding if r['action'] == 'a2a_inquiry' and
                  observation(r).get('defer') and r['args'].get('text') == row['text']]
        kw = dict(customer=row['from'], extra=[r['ref'] for r in defers], tool='a2a_inquiry')
        if '잠시 바빠서 답을 못 했어요' in reply or row['by'] == 'busy':
            busy.append(row)
            emit(row, 'defer_timeout' if defers else 'busy_reply', 'time',
                 '응답 시한을 넘겨 손님에게 busy 문구가 갔다.', repeat_key='buyer_timeout', **kw)
        elif not reply.strip() and purchase_intent(row):
            emit(row, 'empty_reply', 'unknown', '구매 문의 답변의 텍스트가 비어 있다.', low=True, **kw)
        elif re.search(r'결제서 발급 중 확인|결제서를 발급할 수 없어요|발급 시스템', reply):
            emit(row, 'buyer_checkout_failure', 'tests', '손님에게 결제서 발급 실패가 안내됐다.', low=True, **kw)
        elif row['by'] == 'tool' and (collision := alias_collision(row)):
            emit(row, 'alias_substring_match', 'tests',
                 f"한 글자 별칭 {collision['hits']}이 다른 낱말 속에서 걸려 '{collision['category']}' 품목으로 읽었다"
                 f"(v{collision['version']}).", **dict(kw, extra=kw['extra'] + [collision['ref']]))
        elif row['by'] == 'tool' and re.search(r'여러 품목을 함께|한 가지로 말씀', reply) and (
            (table := alias_table(row))[0] is not None and not any(
                w in row['text'] for words in table[0].values() for w in words)
        ):
            emit(row, 'no_match_rejected', 'tests',
                 f"v{table[1]} 별칭 사전에 걸리는 품목이 하나도 없는 문의를 여러 품목과 같이 '한 가지로'로 돌려보냈다.", **kw)
        elif row['by'] == 'tool' and re.search(r'여러 품목을 함께|한 가지로 말씀', reply) and alternatives(row):
            emit(row, 'alternatives_rejected', 'tests',
                 "손님이 'A나 B' 가운데 아무것이나 괜찮다고 물었는데 여러 품목으로 보고 돌려보냈다.", **kw)
        elif re.search(r'여러 품목을 함께|한 가지로 말씀', reply) and re.search(
            r'한 품목|하나만|만 (?:여쭙|문의|확인|묻)|만 따로|만 구매', row['text']
        ):
            emit(row, 'single_item_rejected', 'tests',
                 '손님이 한 품목이라고 밝혔는데 여러 품목 또는 한 가지로 말해 달라고 돌려보냈다.', **kw)
        elif purchase_intent(row) and not checkout_text(row) and not re.search(
            r'재고가 없|재고는 없|재고가 지금 없|재고가 모두 없|않습니다|않겠|구매하지|취급', reply
        ):
            emit(row, 'no_checkout_in_text', 'unknown', '구매 관련 답변에서 결제서 전달 문구가 확인되지 않았다.',
                 low=True, **kw)
        if checkout_text(row):
            breaks = condition_breaks(row['text'], reply)
            if breaks:
                emit(row, 'buyer_condition_ignored', 'inverse',
                     '손님이 적은 조건과 다른 결제서를 냈다: ' + ', '.join(breaks) + '.', **kw)
            left = remaining_hours(reply)
            if left is not None and left < 1:
                emit(row, 'near_expiry_checkout', 'policy', f'남은 기한 {left * 60:.0f}분인 상품의 결제서를 냈다.',
                     low=True, **kw)

    settles = [r for r in ledger if r['kind'] == 'settle']
    for row in ledger:
        if row['kind'] == 'expire':
            data = row['data']
            emit(row, 'stock_expired', 'market', f"원장에 재고 {len(data.get('units', []))}개 만료가 기록됐다.",
                 extra=[{'file': 'logs/ledger.jsonl', 'seq': row['seq']}],
                 cost={'spoiled_cost_credits': data['cost']} if isinstance(data.get('cost'), (int, float)) else {},
                 item=', '.join(data.get('skus', [])))

    calls = defaultdict(list)
    for row in react:
        calls[row['action']].append(row)
    supply = [r for r in ledger if r['kind'] == 'supply']
    for row in react:
        action, args = row['action'], row['args']
        raw = row.get('observation', '')
        out = observation(row)
        item = args.get('sku') or args.get('unit')
        if action == 'reply' and raw.startswith('error:'):
            target = str(args.get('to', ''))
            if re.search(r'[가-힣]|-[0-9a-f]{4}$', target) and len(target) < 30:
                emit(row, 'reply_customer_name', 'interface', '메시지 ID 대신 손님 이름으로 답하려다 실패했다.',
                     tool=action)
            else:
                emit(row, 'reply_failed', 'time' if 'no longer waiting' in raw else 'interface',
                     'reply가 대기 중인 메시지에 연결되지 않았다.', tool=action)
        if action in {'buy_stock', 'make_checkout'}:
            status = re.search(r'"status":\s*([45]\d\d)', raw)
            failure = raw.startswith('error:') or out.get('error') or out.get('aborted') or status
            if failure:
                reason = str(out.get('error') or out.get('aborted') or '')
                category = ('market' if action == 'buy_stock' and status else
                            'meaning' if re.search('grade mismatch|certificate mismatch', reason) else
                            'policy' if re.search('prior checkout|lock|already', reason, re.I) else 'tests')
                emit(row, f'{action}_failed', category, f'{action} 호출이 실패하거나 보호 조건으로 중단됐다.',
                     item=item, tool=action, repeat_key=f'{action}:{category}')
        if action == 'buy_stock' and out.get('status') == 429:
            window = out.get('json', {})
            start, end = window.get('opens_at'), window.get('closes_at')
            if start and end and 0 < start - row['ts'] <= 90:
                matching = [r for r in between(supply, start, end) if r['data'].get('sku') == item]
                follow = next((r for r in between(calls[action], end, end + 300)
                               if r['args'].get('sku') == item), None)
                if not matching and follow:
                    emit(row, 'restock_window_missed', 'market',
                         '90초 안에 열릴 창을 확인했으나 같은 SKU 매입은 창 안에 없고 닫힌 뒤 재시도했다.',
                         extra=[follow['ref']], item=item, low=True, tool=action)
        if action == 'make_checkout' and '"checkout_jwt"' in raw and row['ref']['line'] not in {6588, 6595, 7323, 7559, 7857}:
            task = args.get('task') or args.get('task_id')
            candidates = [r for r in between(calls['reply'], row['ts'], row['ts'] + 100)
                          if task and r['args'].get('to') == task]
            sent = any(r.get('observation') == 'sent' and 'checkout' in str(r['args'].get('data', {}))
                       for r in candidates)
            recent_busy = next(iter(between(busy, row['ts'], row['ts'] + 35)), None)
            if not sent and (not task or (recent_busy and candidates)):
                unit = args.get('unit')
                bounds = [r['voided_at'] for r in withdrawals if r.get('unit') == unit and
                          r.get('last_issued_ts') == row['ts'] and r.get('voided_at', 0) > row['ts']]
                evidence = [r['ref'] for r in candidates]
                if recent_busy:
                    evidence.append(recent_busy['ref'])
                for r in withdrawals:
                    if r.get('unit') == unit and bounds and r.get('voided_at') == min(bounds):
                        evidence.append(r['ref'])
                emit(row, 'checkout_without_delivery', 'policy',
                     '결제서는 발급됐으나 대기 손님에게 전달된 경로를 확인할 수 없다.',
                     extra=evidence, item=unit, tool=action, low=True)
    add_audited(emit, react, talk, chat, forge, ledger, restart)
    add_recent(emit, react, talk, chat, forge, ledger)
    add_generic(emit, incidents, react, talk, forge, ledger, owner, calls, supply, cutoff, versions)
    incidents.sort(key=lambda e: (e['epoch'], e['id']))
    previous = {}
    for entry in incidents:
        key = entry.pop('_repeat')
        entry['repeat_of'] = previous.get(key)
        previous[key] = entry['id']
    write('incidents.jsonl', '\n'.join(json.dumps(e, ensure_ascii=False) for e in incidents))

    hourly = defaultdict(lambda: {'incidents': Counter(), 'activity_steps': Counter(),
                                  'buyer_opportunities': 0, 'checkout_wording': 0, 'settlements': 0})
    for row in react:
        hourly[iso(row['ts'])[:13]]['activity_steps'][activity(row)] += 1
    for row in talk:
        values = hourly[iso(row['ts'])[:13]]
        values['buyer_opportunities'] += purchase_intent(row)
        values['checkout_wording'] += checkout_text(row)
    for row in settles:
        hourly[iso(row['ts'])[:13]]['settlements'] += 1
    for entry in incidents:
        hourly[entry['ts'][:13]]['incidents'][entry['type']] += 1

    interventions = compare(incidents, react, talk, settles, forge, nudges, owner, goal, restart, cutoff, chat)
    report(incidents, hourly, interventions, cutoff, react, talk, settles, versions['a2a_inquiry'], auto)


def add_audited(emit, react, talk, chat, forge, ledger, restart):
    def at(rows, line):
        return next(r for r in rows if r['ref']['line'] == line)

    def refs(rows, *lines):
        return [at(rows, n)['ref'] for n in lines]

    settle = next(r for r in ledger if r['seq'] == 19145)
    for line, version, detail, supporting in [
        (7270, 20, '인증서와 실측 등급의 불일치를 막으면서 인증서 공란까지 걸렀다.', (7383,)),
        (7454, 22, '결제서 서명과 파일 쓰기 권한이 빠졌다.', (7523,)),
        (7730, 24, '인증서 공란 차단을 다시 도입했다.', (7767, 7785)),
    ]:
        row = at(react, line)
        registered = next(r for r in forge if r['tool'] == 'a2a_inquiry' and r['version'] == version and r['passed'])
        emit(row, 'handler_regression', 'tests', f'v{version}에서 이전 판매 경로가 좁아졌다. {detail}',
             extra=[registered['ref'], settle['ref'], *refs(react, *supporting)], tool='a2a_inquiry',
             repeat_key='handler_regression')
    emit(at(react, 7785), 'owner_rule_reversal', 'memory',
         '공란 인증서를 허용하라는 지시와 v25 수정 뒤 판매 불가 공지를 게시했다.',
         extra=refs(chat, 239) + refs(react, 7767, 7784, 7787), tool='a2a_inquiry')
    emit(at(react, 7730), 'owner_rule_reversal', 'memory',
         '공란 인증서를 허용하라는 앞선 주인 지시가 있었으나 다시 차단했다.',
         extra=refs(chat, 206) + refs(react, 7383), tool='a2a_inquiry')
    for line in (1677, 6633, 7321):
        emit(at(react, line), 'currency_confusion', 'meaning',
             '크레딧 잔액의 천분의 일 표시를 다시 크레딧으로 해석했다.',
             extra=[{'file': 'tools/chain_balance/logic.py', 'line': 14}], tool='chain_balance')
    emit(at(react, 7811), 'quote_cost_confusion', 'meaning',
         '직전 판단에 쓴 견적 원가와 실제 매입 견적이 달랐다.',
         extra=refs(react, 7810), item='Gab7c8b3d', low=True)
    emit(at(react, 7783), 'false_zero_settlements', 'meaning',
         '도구가 보고한 24시간 판매 0을 채택했지만 같은 날 정산이 로컬 원장에 있다.',
         extra=refs(react, 7782) + [settle['ref'], {'file': 'tools/shop_health/logic.py', 'line': 26}])
    emit(at(talk, 119), 'buyer_condition_ignored', 'inverse',
         'C등급 제외 조건에 C등급 결제서를 안내했다.', customer=at(talk, 119)['from'], item='계란')
    for line in (6588, 6595):
        emit(at(react, line), 'checkout_without_customer', 'policy',
             '손님 메시지 ID가 들어갈 자리에 진열용 설명을 넣고 결제서를 발급했다. 잠금 지속은 미확인이다.',
             extra=refs(chat, 136) + refs(react, 6596), item=at(react, line)['args']['unit'],
             tool='make_checkout', repeat_key='checkout_without_delivery')
    expired = next(r for r in ledger if r['seq'] == 20191)
    emit(at(react, 7323), 'checkout_without_customer', 'policy',
         '진열용 총각김치 결제서를 손님 메시지 ID 없이 발급했고 같은 단위가 이후 만료됐다.',
         extra=refs(chat, 136) + [expired['ref']], item=at(react, 7323)['args']['unit'],
         tool='make_checkout', repeat_key='checkout_without_delivery')
    fish, blocked = at(react, 7559), at(react, 7652)
    emit(fish, 'checkout_without_customer', 'policy',
         '손님 없이 고등어 결제서를 냈고 81분 뒤 같은 발급 시각을 가진 활성 결제서가 손님 문의에서 재발급을 막았다.',
         extra=[blocked['ref']] + refs(talk, 109), item=fish['args']['unit'],
         cost={'locked_unit_hours': round((blocked['ts'] - fish['ts']) / 3600, 3)},
         tool='make_checkout', repeat_key='checkout_without_delivery')
    emit(at(react, 6563), 'rules_test_data_residue', 'tests',
         '규칙 복원 뒤 읽기 결과에 시험 문장이 남아 후속 도구로 제거했다.',
         extra=refs(chat, 128) + refs(react, 6560, 6564, 6565), tool='edit_owner_rules')
    emit(at(react, 7857), 'checkout_lost_to_timeout', 'policy',
         '반찬 문의에 결제서를 발급했으나 해당 대화에 기록된 답은 busy였다.',
         extra=refs(react, 7854, 7856, 7858) + refs(talk, 121), customer=at(talk, 121)['from'],
         item='총각김치', tool='make_checkout', repeat_key='checkout_without_delivery')


def add_recent(emit, react, talk, chat, forge, ledger):
    """00:31:45 스냅샷 밖에서 원본 행을 검토해 지정한 사례. 474건 재현(snapshot_check.py)에는 들어가지 않는다."""
    def at(rows, line):
        return next(r for r in rows if r['ref']['line'] == line)

    def refs(rows, *lines):
        return [at(rows, n)['ref'] for n in lines]

    cases = [
        # v16: 서명·쓰기 권한의 첫 회귀. v19가 되살렸고 v22에서 다시 빠졌다.
        lambda: emit(at(react, 6802), 'handler_regression', 'tests',
                     'v16에서 결제서 서명과 파일 쓰기 권한이 처음 빠졌다. v17·v18도 같았고 그동안 자동 응대는 결제서 발급 실패를 안내했다. v19에서 되살렸다.',
                     extra=[next(r for r in forge if r['tool'] == 'a2a_inquiry' and r['version'] == 16 and r['passed'])['ref'],
                            *refs(talk, 73, 74, 75), *refs(react, 7182)],
                     tool='a2a_inquiry', repeat_key='handler_regression'),
        lambda: emit(at(react, 8342), 'handler_regression', 'tests',
                     "v30에서 국수 별칭 '면'이 손님 문장의 '있으면·없으면'에 걸려 한 품목 문의를 여러 품목으로 돌려보내고 두부·모니터 문의에 국수 재고 없음을 답했다. 시험은 가짜 재고와 고정 문장 네 개였다.",
                     extra=[next(r for r in forge if r['tool'] == 'a2a_inquiry' and r['version'] == 30 and r['passed'])['ref'],
                            {'file': 'tools/.deprecated/a2a_inquiry@30/logic.py', 'line': 2},
                            {'file': 'tools/.deprecated/a2a_inquiry@30/logic.py', 'line': 12},
                            {'file': 'tools/.deprecated/a2a_inquiry@30/test.py', 'line': 1},
                            *refs(talk, 172, 182, 184, 185), {'file': 'logs/nudges.jsonl', 'line': 114}],
                     tool='a2a_inquiry', repeat_key='handler_regression'),
        lambda: emit(at(react, 8472), 'restore_not_faithful', 'execution',
                     "주인이 proposals의 v28 원문으로 되돌리라고 했으나 logic.py 경로를 찾지 못한 채 v31을 만들고 'v28 동작으로 복원'이라고 보고했다. v31은 v30 줄을 더 많이 물려받았고 v30의 '면' 별칭이 남았다.",
                     extra=refs(chat, 266) + refs(react, 8465, 8466, 8473) +
                     [{'file': 'proposals/a2a_v28_20261128/v28_logic.py', 'line': 2},
                      {'file': 'tools/.deprecated/a2a_inquiry@31/logic.py', 'line': 2}], tool='a2a_inquiry'),
        lambda: emit(at(react, 8463), 'current_version_confusion', 'data',
                     "손님을 받고 있던 판이 v30인데 'v30으로 교체하지 않고 현재 동작을 유지하겠다'고 답했다.",
                     extra=refs(chat, 265) + [next(r for r in forge if r['tool'] == 'a2a_inquiry' and r['version'] == 30 and r['passed'])['ref']],
                     tool='a2a_inquiry'),
        lambda: emit(at(react, 8453), 'false_absence_claim', 'data',
                     '루트의 talk.jsonl을 열어 보고 손님 대화 파일이 없다고 답했고, tools/.deprecated/a2a_inquiry@28에 있던 v28 원문도 남아 있지 않다고 답했다.',
                     extra=refs(react, 8448) + refs(chat, 263) +
                     [{'file': 'logs/talk.jsonl'}, {'file': 'tools/.deprecated/a2a_inquiry@28/logic.py', 'line': 1}]),
        lambda: emit(at(react, 8489), 'read_scope_misread', 'data',
                     "60줄·36,325바이트 파일을 '전체가 3,000자 이내'라 끝까지 읽었다고 답했다. start·end는 줄 번호였고 결과는 6,000자에서 잘렸다.",
                     extra=refs(react, 8484, 8485) + refs(chat, 271) +
                     [{'file': 'proposals/a2a_v28_20261128/cases_from_talk.jsonl'},
                      {'file': 'tools/inspect_local/logic.py', 'line': 6}, {'file': 'kit/agent_kit.py', 'line': 68}],
                     tool='inspect_local'),
        lambda: emit(at(react, 8521), 'notes_over_tail', 'memory',
                     '메모가 압축 없이 약 15,674자(12:01 커밋 15,004자에 뒤이은 메모 다섯 건, 로그 인자 절단으로 하한)까지 자라 다음 실행은 끝 3,000자만 봤다. 주인 지시 뒤 2,826자로 압축했다.',
                     extra=refs(chat, 274) + refs(react, 8519, 8520) + [{'file': 'notes.md'}], tool='compact_notes'),
        lambda: emit(at(react, 8653), 'expiry_blind_check', 'data',
                     "소비기한 칸이 없는 inventory_audit 결과로 '임박 재고는 현재 확인되지 않았다'고 판단했다. 같은 시각 우유 C급은 남은 기한 2시간 미만이었고 17:42 원가 12,995로 만료됐다.",
                     extra=refs(react, 8652) + refs(talk, 198) + [next(r for r in ledger if r['seq'] == 27699)['ref']],
                     item='G0011e806', tool='inventory_audit'),
        lambda: emit(at(react, 8703), 'talk_demand_ignored', 'execution',
                     "17:08 장정학 사과 문의에 재고 없음이라 답한 뒤, '매입은 talk의 손님 품목으로' 규칙과 달리 시장 판매량을 근거로 시금치·계란 매입만 시도했다. 사과 매입은 18:03 넛지 뒤 18:25에 이뤄졌다.",
                     extra=refs(talk, 200) + refs(react, 8722, 8755) + [{'file': 'owner_rules.md'}], tool='buy_stock'),
        lambda: emit(at(talk, 202), 'unmet_demand_repeat', 'market',
                     '11/28 국수(메밀소바·칼국수) 문의가 두 손님에게서 6회 재고 없음으로 끝났으나 11/26 00:03 뒤로 국수 매입 시도가 없다.',
                     extra=refs(talk, 176, 180, 183) + refs(react, 2661), customer=at(talk, 202)['from'], item='국수'),
        lambda: emit(next(r for r in forge if r['tool'] == 'a2a_inquiry' and r['version'] == 36 and r['passed']),
                     'handler_regression', 'tests',
                     "v36이 결제서 값을 하한 (원가+210)/0.99로 고정해 마진이 0이고(card.json 가자미 7,590과 어긋남), 기한이 가장 이른 unit만 골라 v33에 있던 '기한 넉넉한 것' 처리가 빠졌다. 20:04~21:00 문의 5건은 모두 재고 없음이라 손님 피해는 아직 관측되지 않았다.",
                     extra=[{'file': 'tools/a2a_inquiry/logic.py', 'line': 22},
                            {'file': 'tools/.deprecated/a2a_inquiry@33/logic.py', 'line': 25},
                            {'file': 'card.json'}, *refs(chat, 270)],
                     tool='a2a_inquiry', repeat_key='handler_regression'),
    ]
    for case in cases:
        try:
            case()
        except StopIteration:
            continue  # 기록이 그 행까지 오지 않은 경우


def changed_action(row):
    """말이 아니라 도구나 운영 행동이 바뀐 호출."""
    action, raw = row['action'], str(row.get('observation') or '')
    if action == 'forge_tool':
        return '"test": "passed"' in raw
    if action == 'buy_stock':
        out = observation(row)
        return bool(out.get('quote')) and not out.get('aborted') and not row['args'].get('dry') and not out.get('error')
    if action == 'market_call':
        return str(row['args'].get('method', '')).upper() == 'POST' and '"status": 200' in raw
    return action in {'compact_notes', 'write_card', 'restore_notes'}


def add_generic(emit, incidents, react, talk, forge, ledger, owner, calls, supply, cutoff, versions):
    """스냅샷 이후 사례를 보며 보탠 일반 규칙. 지정 사례와 같은 행·종류는 다시 세지 않는다."""
    # 도구 판 갈아엎기: 한 시간 안 세 판 또는 여섯 시간 안 다섯 판.
    handlers = defaultdict(list)
    for row in forge:
        if 'a2a' in ((row.get('permission') or {}).get('handles') or []):
            handlers[row['tool']].append(row)
    for tool, rows in handlers.items():
        passed = [r for r in rows if r['passed']]
        active = {3600: False, 21600: False}
        for row in passed:
            found = []
            for span, need in ((3600, 3), (21600, 5)):
                burst = [p for p in passed if row['ts'] - span < p['ts'] <= row['ts']]
                if len(burst) >= need and not active[span]:
                    found.append(burst)
                active[span] = len(burst) >= need
            if not found:
                continue
            widest = max(found, key=lambda b: row['ts'] - b[0]['ts'])
            tries = [r for r in rows if widest[0]['ts'] - 3600 < r['ts'] <= row['ts']]
            failed = sum(not r['passed'] for r in tries)
            text = ' · '.join(f"v{b[0]['version']}~v{b[-1]['version']} {(b[-1]['ts'] - b[0]['ts']) / 60:.0f}분에 {len(b)}판"
                              for b in found)
            emit(row, 'handler_churn', 'tests', f'{tool} 판을 짧은 간격으로 갈아엎었다: {text}. 같은 구간 시험 실패 {failed}회.',
                 extra=[r['ref'] for r in tries], tool=tool, repeat_key='handler_churn')

    # 판 교체 뒤 결제서가 사라진 경우: 구매 문의 8건 이상에 결제서 0, 직전 비교 판은 20% 이상.
    windows = []
    for index, row in enumerate(versions['a2a_inquiry']):
        nxt = versions['a2a_inquiry'][index + 1]['ts'] if index + 1 < len(versions['a2a_inquiry']) else cutoff + 1
        asked = [r for r in between(talk, row['ts'], nxt) if purchase_intent(r)]
        windows.append((row, asked, sum(map(checkout_text, asked))))
    for index, (row, asked, sent) in enumerate(windows):
        if len(asked) < 8 or sent:
            continue
        prior = next((w for w in reversed(windows[:index]) if len(w[1]) >= 5), None)
        if prior and prior[2] / len(prior[1]) >= 0.2:
            emit(row, 'checkout_rate_drop', 'tests',
                 f"v{row['version']} 동안 구매 문의 {len(asked)}건에 결제서 문구 0건. 비교 판 v{prior[0]['version']}는 {len(prior[1])}건에 {prior[2]}건.",
                 extra=[prior[0]['ref']] + [r['ref'] for r in asked[:6]], tool='a2a_inquiry')

    # 손님이 '말고'로 뺀 상품을 매입했다.
    names = {}
    for row in react:
        for sku, name in re.findall(r'"sku": "(G[0-9a-f]{8})", "name": "([^"]+)"', str(row.get('observation') or '')):
            names.setdefault(sku, name)
    excluded = []
    for row in talk:
        terms = set()
        for a, b in re.findall(r'([가-힣A-Za-z0-9]{2,}?)(?:이나|나|랑|와|과|,)\s*([가-힣A-Za-z0-9]{2,}?)\s*(?:말고|빼고|제외하고)', row['text']):
            terms |= {a, b}
        terms |= set(re.findall(r'([가-힣A-Za-z0-9]{2,})\s*(?:말고|빼고)', row['text']))
        if terms:
            excluded.append((row, terms))
    for row in supply:
        sku, name = row['data'].get('sku'), names.get(row['data'].get('sku'), '')
        buy = next((r for r in between(calls['buy_stock'], row['ts'] - 120, row['ts'] + 5)
                    if r['args'].get('sku') == sku), None)
        for asked, terms in excluded:
            hit = max((t for t in terms if t == sku or (len(t) >= 3 and t in name)), key=len, default=None)
            if hit and row['ts'] - 172800 <= asked['ts'] < row['ts']:
                again = [r['ref'] for r in between(calls['buy_stock'], row['ts'] + 5, row['ts'] + 7200)
                         if r['args'].get('sku') == sku]
                emit(buy or row, 'inverse_purchase', 'inverse',
                     f"{asked['from']}이 '{hit} 말고'라고 뺀 상품({name[:40] or sku})을 {row['data'].get('total')}크레딧에 매입했다.",
                     extra=[row['ref'], asked['ref'], *again], cost={'purchase_credits': row['data'].get('total', 0)},
                     customer=asked['from'], item=sku, tool='buy_stock')
                break

    # 429가 알려 준 매입 창을 쓰지 못했다.
    windows = defaultdict(list)
    for row in calls['buy_stock']:
        out = observation(row)
        window = out.get('json') if isinstance(out.get('json'), dict) else {}
        if out.get('status') == 429 and window.get('opens_at') and window.get('closes_at'):
            windows[(window['opens_at'], window['closes_at'])].append(row)
    missed = {e['evidence'][0]['line'] for e in incidents if e['kind'] == 'restock_window_missed'}
    for (start, end), knocks in sorted(windows.items()):
        if end > cutoff or any(r['ref']['line'] in missed for r in knocks) or list(between(supply, start - 5, end + 5)):
            continue
        inside = list(between(react, start, end + 1))
        tries = [r for r in inside if r['action'] == 'buy_stock']
        if all(r['args'].get('dry') for r in knocks) and not tries:
            continue  # 견적만 본 창은 매입 의도가 분명하지 않다
        steps = Counter(r['action'] for r in inside)
        detail = ', '.join(f'{k} {v}' for k, v in steps.most_common(4)) or '깨어 있지 않음'
        emit(knocks[-1], 'restock_window_ignored', 'market',
             f'닫힘 응답이 {iso(start)[11:19]}~{iso(end)[11:19]} 창을 알려 줬으나 창 안 매입이 없었다. '
             f'같은 창에 닫힘 응답 {len(knocks)}회, 창 안 호출 {sum(steps.values())}회({detail}).',
             extra=[r['ref'] for r in knocks[:-1][-4:]] + [r['ref'] for r in tries],
             item=knocks[-1]['args'].get('sku'), tool='buy_stock', low=not tries and len(knocks) < 2)

    # 데이터 위치·형식 착각.
    reads = calls['inspect_local']
    for index, row in enumerate(reads):
        raw, path = str(row.get('observation') or ''), str(row['args'].get('path') or '')
        miss = re.search(r"No such file or directory: '([^']+)'", raw)
        if miss:
            wanted = Path(miss.group(1))
            parent = ROOT / wanted.parent
            near = list(ROOT.glob(f'*/{wanted.name}')) + (list(parent.glob(f'*{wanted.name}')) if parent.is_dir() else [])
            # 열지 못한 경로 자체이거나 그 호출 뒤에 생긴 파일은 후보가 아니다.
            near = [p.relative_to(ROOT).as_posix() for p in near if p.is_file() and p != ROOT / wanted
                    and getattr(p.stat(), 'st_birthtime', 0) <= row['ts']]
            if near:
                emit(row, 'path_miss', 'data', f"'{wanted}'를 열지 못했다. 같은 이름 계열 파일 {', '.join(near[:3])}이 있다.",
                     extra=[{'file': p} for p in near[:3]], tool='inspect_local')
            continue
        target = ROOT / path
        if not target.is_file() or not (path.startswith('logs/') or target.stat().st_mtime <= row['ts']):
            continue  # 그 뒤 바뀐 파일은 당시 크기를 알 수 없다
        lines = target.read_text(errors='replace').splitlines(keepends=True)
        try:
            start, end = int(row['args'].get('start') or 0), int(row['args'].get('end') or 1000)
        except (TypeError, ValueError):
            continue
        size = len(json.dumps({'ok': True, 'result': {'lines': ''.join(lines[start:end])}}, ensure_ascii=False))
        if size <= OBS_LIMIT:
            continue
        follow = next((r for r in reads[index + 1:] if r['args'].get('path') == path and r['ts'] - row['ts'] <= 900
                       and int(r['args'].get('start') or 0) >= len(lines)), None)
        if follow:
            emit(follow, 'truncated_read', 'data',
                 f"start·end를 글자 위치로 보고 다음 구간을 읽었으나 파일은 {len(lines)}줄이라 비어 있었다. 앞 호출은 {len(lines[start:end])}줄·약 {size:,}자를 돌려줬고 모델은 앞 {OBS_LIMIT:,}자만 봤다.",
                 extra=[row['ref'], {'file': path}, {'file': 'tools/inspect_local/logic.py', 'line': 6}], tool='inspect_local')
        else:
            emit(row, 'observation_truncated', 'data',
                 f'{path} {len(lines[start:end])}줄·약 {size:,}자를 한 번에 읽어 모델은 앞 {OBS_LIMIT:,}자만 봤다.',
                 extra=[{'file': path}, {'file': 'kit/agent_kit.py', 'line': 68}], tool='inspect_local', low=True)
    for row in calls['search_logs']:
        query = str(row['args'].get('query', ''))
        if re.fullmatch(r'\d{1,2}:\d{2}(?::\d{2})?', query) and '"matches": []' in str(row.get('observation')):
            emit(row, 'clock_string_search', 'data',
                 f"epoch 숫자로 기록된 로그에서 시각 문자열 '{query}'를 찾고 기록이 없다고 판단했다.",
                 extra=[{'file': 'logs/talk.jsonl'}], tool='search_logs')

    # 새 판에서 결제서 발급 코드가 사라졌다. tools/.deprecated/<도구>@<판>/logic.py와 현재 판을 비교한다.
    def source(version):
        for path in (ROOT / f'tools/.deprecated/a2a_inquiry@{version}/logic.py', ROOT / 'tools/a2a_inquiry/logic.py'):
            if path.exists() and (path.parent.name != 'a2a_inquiry' or
                                  json.loads((path.parent / 'forge.json').read_text()).get('version') == version):
                return path
        return None
    passed = versions['a2a_inquiry']
    for prev, row in zip(passed, passed[1:]):
        old, new = source(prev['version']), source(row['version'])
        if old and new and 'checkout' in old.read_text() and 'checkout' not in new.read_text():
            emit(row, 'checkout_path_removed', 'tests',
                 f"v{row['version']}에서 결제서 발급 코드가 사라졌다(v{prev['version']} {len(old.read_text().splitlines())}줄 → "
                 f"{len(new.read_text().splitlines())}줄). 시험은 통과했다.",
                 extra=[prev['ref'], {'file': new.relative_to(ROOT).as_posix()}, {'file': old.relative_to(ROOT).as_posix()}],
                 tool='a2a_inquiry', repeat_key='handler_regression')

    # 원장 첫 500행만 읽은 건강 요약이 같은 24시간의 실제 정산을 0건으로 보고했다.
    settles = [r for r in ledger if r['kind'] == 'settle']
    for row in calls['shop_health']:
        out = observation(row)
        day = (out.get('windows') or {}).get('24h') or {}
        if out.get('ledger_rows') == 500 and day.get('sales_count') == 0:
            real = list(between(settles, row['ts'] - 86400, row['ts']))
            if real:
                emit(row, 'false_zero_settlements', 'meaning',
                     f"건강 요약이 원장 500행만 읽고 24시간 판매 0건을 냈으나 같은 24시간 로컬 원장에 정산 {len(real)}건이 있다.",
                     extra=[r['ref'] for r in real[-2:]] + [{'file': 'tools/shop_health/logic.py'}], tool='shop_health')

    # 창구가 열렸다고 믿고 매입했으나 닫힘 응답을 받았다.
    for row in calls['buy_stock']:
        if observation(row).get('status') == 429 and re.search(r'열린 상태|열려 있|이미 열린', row.get('thought') or ''):
            emit(row, 'window_open_misread', 'data', '창구가 열려 있다고 판단하고 매입했으나 닫힘(429) 응답을 받았다. 직전 opens_at을 확인하지 않았다.',
                 item=row['args'].get('sku'), tool='buy_stock')

    # 주인 지시를 적기만 하고 실행을 바꾸지 않았다.
    for row in owner:
        if not directive(row):
            continue
        subject = directive_topic(row['text'])
        window = list(between(react, row['ts'], row['ts'] + 3600))
        # 지시 주제에 맞는 실행 변경만 센다. 조건 지시 뒤 둥굴레차 매입은 실행으로 보지 않는다.
        relevant = {'inverse': {'forge_tool'}, 'tests': {'forge_tool'}, 'policy': {'forge_tool'},
                    'memory': {'compact_notes', 'restore_notes'}, 'market': {'buy_stock', 'forge_tool'}}.get(subject)
        if any(changed_action(r) and (relevant is None or r['action'] in relevant) for r in window):
            continue
        recorded = [r for r in window if r['action'] == 'edit_owner_rules']
        later = sorted((e for e in incidents if row['ts'] < e['epoch'] <= row['ts'] + 10800 and
                        e['type'] == subject and e['confidence'] == 'high'), key=lambda e: e['epoch'])
        if later:
            noted = (f"owner_rules.md 추가({', '.join(iso(r['ts'])[11:16] for r in recorded)})만 있고"
                     if recorded else 'owner_rules.md 기록도 없고')
            emit(row, 'directive_not_executed', 'execution',
                 f'주인 지시 뒤 1시간 안에 {noted} 지시 주제의 도구·행동 변경이 없었다. 3시간 안 같은 유형 사건 {len(later)}건: '
                 + ', '.join(e['id'] for e in later[:3]) + '.',
                 extra=[r['ref'] for r in recorded[:3]] + [e['evidence'][0] for e in later[:3]])


def compare(incidents, react, talk, settles, forge, nudges, owner, goal, restart, cutoff, chat=()):
    result = []
    labels = [('넛지', nudges), ('주인 직접 지시', [r for r in owner if directive(r)]),
              ('주인 채팅', [r for r in owner if not directive(r)]), ('goal 변경', goal), ('키트 시작 시도', restart)]
    answers = [r for r in chat if r['who'] == 'agent']
    for label, rows in labels:
        for row in rows:
            ts = row['ts']
            ref = row['ref']
            category = directive_topic(row['text']) if label == '주인 직접 지시' else topic(row.get('text', ''))
            if label == 'goal 변경':
                category = topic_for_goal(ref['commit'])
            if label == '키트 시작 시도':
                prior_goal = latest(goal, ts)
                if prior_goal and ts - prior_goal['ts'] < 900:
                    category = topic_for_goal(prior_goal['ref']['commit'])
            # 성공한 답변이나 코드 변경만으로 행동의 반전을 선언하지 않는다.
            reply = str(row.get('reply') or '')
            receipt = ('busy' if 'busy' in reply.lower() else '답변 기록' if reply.strip()
                       else '오류 기록' if row.get('error') else '미확인')
            windows = {}
            for hours in (1, 3):
                halves = []
                for start, end in ((ts - hours * 3600, ts), (ts, ts + hours * 3600)):
                    inquiries = [r for r in between(talk, start, end) if purchase_intent(r)]
                    events = [e for e in incidents if start <= e['epoch'] < end]
                    steps = Counter(activity(r) for r in between(react, start, end))
                    target_actions = { 'interface': {'reply'}, 'market': {'buy_stock'},
                                      'policy': {'make_checkout'}, 'meaning': {'make_checkout', 'market_call', 'buy_stock'},
                                      'memory': {'compact_notes', 'write_note', 'market_call'},
                                      'tests': {'make_checkout', 'forge_tool'}}.get(category, set())
                    exposure = (len(inquiries) if category == 'time' else
                                sum(r['action'] in target_actions for r in between(react, start, end)))
                    halves.append({'inquiries': len(inquiries), 'checkout_wording': sum(map(checkout_text, inquiries)),
                                   'same_type': sum(e['type'] == category and e['confidence'] == 'high' for e in events),
                                   'exposure_proxy': exposure,
                                   'settlements': len(list(between(settles, start, end))),
                                   'activity_steps': steps})
                windows[str(hours)] = halves
            before, after = windows['3']
            next_event = next((e for e in incidents if ts < e['epoch'] <= ts + 10800 and
                               category and e['type'] == category and e['confidence'] == 'high'), None)
            for hours, halves in windows.items():
                span = int(hours) * 3600
                halves[0]['complete'] = ts - span >= react[0]['ts'] and (
                    category != 'time' or ts - span >= talk[0]['ts'])
                halves[1]['complete'] = ts + span <= (talk[-1]['ts'] if category == 'time' else cutoff)
            if not category:
                verdict = '대상 미특정'
            elif not before['complete'] or not after['complete']:
                verdict = '관측 구간 잘림'
            elif min(before['exposure_proxy'], after['exposure_proxy']) == 0:
                verdict = '관측 기회 부족'
            else:
                old = before['same_type'] / before['exposure_proxy']
                new = after['same_type'] / after['exposure_proxy']
                verdict = '빈도 감소' if new < old else '빈도 증가' if new > old else '빈도 동일'
            forged = [r for r in between(forge, ts, ts + 3600) if r['passed']]
            response = None
            if label in {'넛지', '주인 직접 지시'}:
                # 말: 30분 안 채팅 답(busy 제외). 기록: owner_rules·메모. 변경: 도구 통과·압축·매입·게시.
                # 되돌림 후보: 첫 변경 뒤 3시간 안 같은 유형 고신뢰 사건. 인과가 아니라 다시 나타났는지만 본다.
                said = next((r for r in between(answers, ts, ts + 1800) if 'busy' not in r['text']), None)
                hour = list(between(react, ts, ts + 3600))
                changes = [r for r in hour if changed_action(r)]
                again = next((e for e in incidents if changes and changes[0]['ts'] < e['epoch'] <= ts + 10800
                              and e['type'] == category and e['confidence'] == 'high'), None)
                response = {'words': said['ref'] if said else None,
                            'recorded': [r['ref'] for r in hour if r['action'] in {'edit_owner_rules', 'write_note'}][:3],
                            'changes': [{'action': r['action'], **r['ref']} for r in changes][:5],
                            'same_type_after_change': again['id'] if again else None}
            result.append({'kind': label, 'ts': iso(ts), 'evidence': ref, 'target': category, 'response': response,
                           'receipt': receipt if label == '넛지' else '미확인', 'focus': focus_for(row, category, label),
                           'windows': windows, 'verdict': verdict,
                           'next_incident': next_event['id'] if next_event else None,
                           'forge_within_1h': [{k: r[k] for k in ('tool', 'version', 'ref')} for r in forged]})
    return sorted(result, key=lambda r: r['ts'])


def focus_for(row, category, label):
    if label == '키트 시작 시도':
        return '키트 재기동과 가까운 goal 변경' if category else '키트 시작 및 실행 문맥 초기화'
    if label == 'goal 변경':
        return {
            'b6878f3': '메모 꼬리와 로그 회상',
            '0859e2f': '주인 지시와 조언 구분',
            'f64c887': '메모 순서와 단위당 한 결제서',
            'b57412a': '원장 정산과 3시간 이후 철회',
            '6d26ca7': '같은 오류 3회 뒤 교훈 보존',
            '29f4acf': '즉시 전달, 정산가 및 진열',
            '2a882d4': '목적·우선순위·판매 시한 전면 재정의',
            '7464a20': '가격 하한과 손실 예외',
            '9596f14': '조언의 근거를 자체 도구로 확인',
            '3fd6cbc': '지갑 목표와 고객 경험',
            'c3da8fe': '원장과 수요 기반 품목 선정',
            '644279d': '조언팀 관측 기간',
        }.get(row['ref']['commit'][:7], '변경 목표 수동 확인 필요')
    message = row.get('text', '')
    for pattern, subject in (
        (r'grade|인증서', '실측 등급과 인증서'),
        (r'80초|바빠서|같은 대화', '대기 시한 내 답장과 결제서'),
        (r'owner_rules|compact_notes|3,000자', '주인 규칙과 메모 꼬리'),
        (r'tOKRW|단위|500만', '잔액과 크레딧 단위'),
        (r'정산가|list_price|정가', '가격의 근거'),
        (r'매입 중단|매입 재개|restock|재입고', '매입 여부와 도매창'),
        (r'철회|voided|잠금', '기존 결제서와 재발급'),
        (r'after|page', '원장 페이지 범위'),
        (r'포럼|공지', '포럼 공지'),
        (r'손님 없는|선발급', '대기 손님 없는 결제서'),
    ):
        if re.search(pattern, message, re.I):
            return subject
    return TYPES.get(category, '목표 행동 미특정')


def topic_for_goal(commit):
    changes = {
        'b6878f3': 'memory', '0859e2f': 'memory', 'f64c887': 'memory',
        'b57412a': 'policy', '6d26ca7': 'memory', '29f4acf': 'policy',
        '2a882d4': 'time', '7464a20': 'policy', '9596f14': 'memory',
        '3fd6cbc': 'meaning', 'c3da8fe': 'market', '644279d': 'memory',
    }
    return changes.get(commit[:7])


RULES = {
    'time': 'busy 문구 또는 대기가 끝났다는 reply 오류. defer는 동일 문의 본문과 응답 직전 81초 안의 도구 관찰이 같이 있어야 붙인다.',
    'interface': 'reply 대상 이름이나 ID가 현재 대기 이벤트와 맞지 않아 오류가 난 호출.',
    'tests': '코드 변경으로 기존 경로가 좁아졌거나 체크아웃 호출에서 처리 오류가 난 사례. 매입의 비시간창 오류도 포함한다. '
             '스냅샷 뒤 규칙: 손님 응대 도구를 1시간 안 3판 또는 6시간 안 5판 통과시킨 판 갈아엎기(handler_churn), '
             '구매 문의 8건 이상에 결제서 문구 0건이고 직전 비교 판은 20% 이상인 판(checkout_rate_drop), '
             '그 판 ALIASES의 한 글자 별칭이 다른 낱말 속에서만 걸려 품목을 정한 답(alias_substring_match), '
             "손님이 '한 품목'이라 밝혔는데 여러 품목으로 돌려보낸 답(single_item_rejected), 별칭 사전에 걸리는 품목이 하나도 없는데 '한 가지로'로 돌려보낸 답(no_match_rejected), "
             "'A나 B'처럼 아무것이나 괜찮다는 문의를 여러 품목으로 본 답(alternatives_rejected), 직전 판에 있던 결제서 발급 코드가 새 판에서 사라진 경우(checkout_path_removed).",
    'memory': '주인 지시 뒤 같은 규칙과 어긋나는 코드 변경 또는 외부 행동을 확인한 사례.',
    'policy': '대기 손님 없는 발급, 기존 결제서 관련 잠금·중복 방어가 관찰된 사례. 남은 기한 1시간 미만 상품의 결제서는 저신뢰로 둔다. '
              '손님 조건 배제 누락은 스냅샷 뒤 집계부터 거절 조건 역방향 실행으로 옮겼다(474건 기준에서는 이 유형).',
    'meaning': '단위, 등급·인증서, 원장 집계 또는 견적의 의미 혼선. 등급 불일치 보호 동작도 포함한다. '
               '건강 요약이 원장 500행만 읽고 24시간 판매 0을 냈는데 같은 24시간 로컬 원장에 정산이 있는 호출마다 한 건(false_zero_settlements).',
    'market': '원장 만료, 매입 HTTP 실패, 열리기 직전 확인했으나 놓친 재입고 창. 스냅샷 뒤 규칙: 실제 매입 시도가 있었거나 닫힘 응답을 두 번 이상 받은 창에서 '
              '창 안 매입이 없으면 창 하나를 한 건으로 센다(restock_window_ignored). 견적만 본 창은 뺀다.',
    'execution': '주인 지시를 말이나 owner_rules·메모로 받아 적었지만 1시간 안에 도구 통과·압축·매입·게시 같은 실행 변경이 없고, '
                 '3시간 안에 지시 주제와 같은 유형의 고신뢰 사건이 이어진 경우(directive_not_executed). '
                 '지시한 원본으로 되돌렸다고 보고했지만 다른 코드를 만든 경우(restore_not_faithful)도 포함한다.',
    'data': '파일 경로, 시각 형식, 줄 번호와 글자 수, 관찰 6,000자 절단을 잘못 읽은 사례. 열지 못한 경로와 같은 이름 계열 파일이 지금 저장소에 있는 경우(path_miss), '
            "epoch 로그에서 '10:04' 같은 시각 문자열을 검색해 0건을 얻은 경우(clock_string_search), "
            'inspect_local 결과가 6,000자를 넘었는데 다음 구간을 글자 위치로 읽어 비었다고 본 경우(truncated_read, 다음 호출이 없으면 저신뢰 observation_truncated). '
            "429를 받은 매입의 생각 기록이 '창구가 열린 상태'라고 판단한 경우(window_open_misread). "
            '파일 크기는 지금 파일로 다시 계산하므로 logs/ 밖에서 그 뒤 바뀐 파일은 세지 않는다. 지금 돌던 판·있던 파일을 없다고 단정한 답은 지정 사례로 둔다.',
    'inverse': "손님이 명시적으로 뺀 조건을 정반대로 실행한 사례. 결제서 답이 손님 문의의 'A등급만', 'C등급 제외', '소량', '기한 넉넉', 용량(g)과 어긋난 경우(buyer_condition_ignored), "
               "48시간 안 손님이 '말고·빼고'로 뺀 상품명이나 SKU를 매입한 경우(inverse_purchase).",
    'unknown': '답변 텍스트는 있으나 실패 또는 원인을 판정하기에 데이터가 부족한 구매 관련 대화.',
}


REVIEW_1128 = [
    '## 주인 직접 지시와 넛지 (11/28 09:00~16:10, 원본 행 검토)', '',
    '주인 직접 지시는 .kit/chat.jsonl의 who=jonghoon 가운데 명령형 문장이다(헤르메스가 주인 승인으로 보낸 것 포함). 넛지는 logs/nudges.jsonl의 조언팀 메시지(앱에서는 who=claude)이며 09:00부터 결과 지표·회귀 질문 형식으로 바뀌었다. '
    '판정 기준: **말** = 30분 안에 busy가 아닌 답으로 요구를 받아들였나. **행동** = 1시간 안에 요구 주제의 도구 통과·압축·매입·게시가 있었나. **결과** = 3시간 안 원본 행에서 요구한 행동이 유지됐나, 되돌아갔나, 반대로 갔나. '
    '두 개입이 몇 분 간격으로 겹친 경우(12:43 넛지와 12:46 지시 등) 행동을 어느 쪽에 돌릴지는 시각 순서로만 정했다. 인과는 식별하지 않는다.', '',
    '| 시각 · 개입 | 요구 | 말 | 행동 | 결과 |', '|---|---|---|---|---|',
    '| 09:04 넛지 [110](../logs/nudges.jsonl#L110) | 결제서 23장에 정산 2건, 불매 이유를 talk에서 세고 시험에 넣었나 | 예 [답](../logs/react.jsonl#L8303) | 없음 (09:24 v29는 09:21 지시 뒤) | — |',
    '| 09:21 지시 [255](../.kit/chat.jsonl#L255) | a2a_inquiry를 지금 고쳐라: 손님이 뺀 조건 지키기, "치킨, 냉동 너겟 말고"는 한 품목 | 예 (busy 뒤 앱 보고) [보고](../.kit/chat.jsonl#L257) | 예: v29, 시험 3회 실패 뒤 통과 [forge](../logs/forge.jsonl#L103) | **미달**: 09:49 같은 손님의 "치킨만… 냉동 너겟 말고"에 다시 "여러 품목" [talk](../logs/talk.jsonl#L168). 시험은 가짜 재고. v29가 국수 별칭 \'면\'을 처음 넣었다 |',
    '| 10:01 넛지 [111](../logs/nudges.jsonl#L111) | v29 시험이 실제 손님 문장인가 | 예, 가짜 재고·고정 문장 인정 [답](../logs/react.jsonl#L8340) | 예: 3분 뒤 v30 [forge](../logs/react.jsonl#L8342) | **악화**: v30 동안 구매 문의 15건에 결제서 0, \'면\'이 \'있으면·없으면\'에 걸림 |',
    '| 11:01 넛지 [112](../logs/nudges.jsonl#L112) | v30 8건 결제서 0, v28과 같은 문장으로 비교 | 아니오: \'10:04\' 검색 0건이라 확인 불가 [검색](../logs/react.jsonl#L8387) | 없음 | — |',
    '| 12:32 지시 [262](../.kit/chat.jsonl#L262) | v28이 팔던 경우는 다 팔게, 실제 손님 문장으로 시험 | 아니오: "talk.jsonl 없음, v28 소스 없음, v30 유지" [답](../logs/react.jsonl#L8453) | 없음 | 루트의 talk.jsonl을 열었다 [오류](../logs/react.jsonl#L8448). v28 원문은 tools/.deprecated/a2a_inquiry@28에 있었다 |',
    '| 12:43 넛지 [113](../logs/nudges.jsonl#L113) | 파일 위치·epoch·v28 원문 경로, v28과 v30 비교 | 부분: "v30으로 교체하지 않고 현재 동작 유지" [답](../logs/react.jsonl#L8463) | 없음 | 돌고 있던 판이 v30이었다 |',
    '| 12:46 지시 [266](../.kit/chat.jsonl#L266) | 지금 판이 v30이다, proposals의 v28 원문으로 되돌려라, 줄 나눠 끝까지 읽어라 | busy [채팅](../.kit/chat.jsonl#L267) | 예: v31 [forge](../logs/react.jsonl#L8472) | **가짜 복원**: logic.py 경로 실패 [오류](../logs/react.jsonl#L8466) 뒤 v30 기반 v31, \'면\' 유지. "v28 동작으로 복원" 보고 |',
    '| 13:02 넛지 [114](../logs/nudges.jsonl#L114) | 손님 문장 185줄 중 159줄에 \'면\', logic.py 2줄 별칭 | 예, 원인 인정. 단 "즉시 교체하지 않고 보류" [답](../logs/react.jsonl#L8479) | 예: 3분 뒤 v32에서 \'면\' 제거 [forge](../logs/react.jsonl#L8481) | **유지**: v32·v33·v34 모두 \'면\' 없음 |',
    '| 13:09 지시 [270](../.kit/chat.jsonl#L270) | 60문장 끝까지 읽고 v28이 결제서 낸 문장은 v32도 내는지, \'기한 넉넉\'은 가장 오래가는 unit | 예. 단 "3,000자 이내라 끝까지 읽었다" [답](../logs/react.jsonl#L8489) | 예: v33 [forge](../logs/react.jsonl#L8487) | **부분**: 결제서 재개(v33 구매 문의 13건에 6건, 14:57 정산 1건). 60문장 대조는 하지 않았고 조건 위반이 남았다 |',
    '| 13:12 넛지 [115](../logs/nudges.jsonl#L115) | 3,000자 착오: start·end는 줄 번호, 결과는 6,000자 절단, 나눈 파일 4개 | 예 [답](../logs/react.jsonl#L8502) | 읽기만 바뀜: 나눈 파일 4개 [읽기](../logs/react.jsonl#L8498) | **되돌아감**: 16:08 logs/talk.jsonl 198줄을 한 번에 읽어 앞 17줄(11/26 19:42~23:49)만 봤다 [읽기](../logs/react.jsonl#L8638) |',
    '| 13:38 지시 [274](../.kit/chat.jsonl#L274) | owner_rules 먼저 확인, compact_notes로 압축, 오늘 교훈 네 줄 | 예 [답](../logs/react.jsonl#L8524) | 예: 확인·추가·압축 15,674→2,826자 [압축](../logs/react.jsonl#L8521) | **유지**. 16시대 확인 때는 다시 4,954자 |',
    '| 14:40 지시 [276](../.kit/chat.jsonl#L276) | "손님 조건 무시하지 말게" (한 줄) | busy [채팅](../.kit/chat.jsonl#L277) | 없음(기록도 없음) | 16:02 소량 우유 문의에 24팩 C급 [talk](../logs/talk.jsonl#L198). 14:02 A등급→C급 400g, 14:19 기한 23분 계란은 이 지시보다 **앞선** 일이다 |',
    '| 15:01 넛지 [116](../logs/nudges.jsonl#L116) | v33 결제서 중 조건과 다른 것은 몇 장인가 | busy | 메모만 [메모](../logs/react.jsonl#L8559) | 16:02 같은 위반 |',
    '| 15:04 지시 [279](../.kit/chat.jsonl#L279) | \'A등급만\'·\'기한 넉넉한 것\'이면 맞는 것만, 없으면 대안을 물어라 | busy ×2 | owner_rules.md 추가만 [기록](../logs/react.jsonl#L8561). 도구는 63분 뒤 v34(16:04 지시 뒤) | **기록만**: 16:02 위반 |',
    '| 15:35 지시 [282](../.kit/chat.jsonl#L282) | 손님이 찾다 못 산 품목부터 사라(생선·가자미·치킨·세제·빵·두부·반찬·소바) | 예 [답](../logs/react.jsonl#L8594) | 예: 15:43 매입 [매입](../logs/react.jsonl#L8604) | **역방향**: 15:17 함민수가 "연두부나 멸균두부 말고요"로 뺀 상온 멸균두부 19,029크레딧. 판매 기록 0은 산 뒤 15:49에야 조회 [조회](../logs/react.jsonl#L8616) |',
    '| 15:44 지시 [284](../.kit/chat.jsonl#L284) | 429의 opens_at을 적고 그 직전에 깨라, 창이 열리면 바로 사라 | busy [채팅](../.kit/chat.jsonl#L285) | 부분: 메모 [메모](../logs/react.jsonl#L8611), 15:50 닫힌 창 다시 두드림 [429](../logs/react.jsonl#L8618), 16:00:35에 깸(창 16:00:27) | **창 소진**: 16:01 한도 초과로 중단 뒤 조회 셋, 16:03:27 닫힐 때까지 매입 0 [중단](../logs/react.jsonl#L8622) |',
    '| 16:01 넛지 [117](../logs/nudges.jsonl#L117) | 멸균두부로 팔 수 있는 문의는 몇 건인가, 창 전에 목록을 정하라 | 예, 0건 인정 [답](../logs/react.jsonl#L8629) | 예: 16:08 후보 3개 메모 [메모](../logs/react.jsonl#L8639) | 미확인(관측 끝) |',
    '| 16:04 지시 [288](../.kit/chat.jsonl#L288) | 적지만 말고 실행을 바꿔라, talk의 실제 말로 살 품목을 정하라 | 예 [답](../logs/react.jsonl#L8632) | 예: owner_rules 추가, v34(시험 1회 실패 뒤), 후보 메모 [v34](../logs/react.jsonl#L8636) | 미확인. 후보를 정한 16:08 읽기는 앞 17줄(11/26)만 보였다(추정: 다른 문맥을 썼을 수 있음) |',
    '',
    '| 집계 (09:00~16:10) | 주인 직접 지시 10건 | 넛지 8건 |', '|---|---|---|',
    '| 말로 받아들임 | 5 (busy 4, 거부 1) | 5 (busy 1, 보류·고집 2) |',
    '| 1시간 안 도구·행동 변경 | 6 + 부분 1 | 3 + 부분 1 |',
    '| 요구가 3시간 유지됨 | 1 (13:38 메모 압축) + 부분 1 (13:09 v33) | 1 (13:02 \'면\' 제거) |',
    '| 바뀌었지만 틀린 방향 | 3 (09:21 미달, 12:46 가짜 복원, 15:35 역방향) + 창 소진 1 (15:44) | 1 (10:01 v30 악화) |',
    '| 바뀐 뒤 되돌아감 | 0 | 1 (13:12 나눠 읽기 → 16:08 한 번에 읽기) |',
    '| 기록만·무반응 | 3 (12:32 거부, 14:40, 15:04) | 4 (09:04, 11:01, 12:43, 15:01) |',
    '| 미확인(관측 끝) | 1 (16:04) | 1 (16:01) |', '',
    '**읽기.** 주인 직접 지시는 넛지보다 도구와 행동을 더 자주 바꿨다(10건 중 7건, 넛지 8건 중 4건). 그러나 바뀐 방향이 맞은 비율은 비슷하게 낮다. '
    '요구가 유지된 세 건(넛지 13:02, 지시 13:38, 일부 13:09)의 공통점은 ① 원본에서 센 구체 사실(185줄 중 159줄, 15,000자), ② 파일 경로와 줄 번호, ③ 기계적으로 한 번에 끝나는 행동 하나(별칭 하나 삭제, compact_notes 한 번)다. '
    '한 줄짜리 원칙("손님 조건 무시하지 말게")과 busy와 겹친 지시는 기록조차 남지 않았다. 금지·품목 목록만 준 지시(09:21, 15:35)는 행동을 바꿨지만 검증 단계가 없어 예문 자체가 실패하거나 손님이 뺀 물건을 샀다. '
    '에이전트가 데이터 위치를 잘못 믿고 있을 때(12:32, 11:01, 12:43)는 주인 지시든 넛지든 거부·보류로 끝났다. 위치 착오를 바로잡고 읽을 수 있는 크기로 나눈 파일을 준 13:12 넛지 뒤에야 읽기가 바뀌었다. 표본은 열여덟 건이고 개입이 몇 분 간격으로 겹쳐 효과를 분리할 수 없다.', '',
]


def report(incidents, hourly, interventions, cutoff, react, talk, settles, versions, auto):
    data = {}
    taxonomy = ['# 실패 유형', '', '한 사건에는 주 유형 하나를 붙였다. 호출·대화·버전 회귀·원장 만료는 서로 다른 관측 단위다. 같은 판매 기회를 여러 행이 설명할 수 있다. 유형은 관측 패턴을 설명하는 원인 후보이며, 특히 등급 불일치나 만료만으로 에이전트 책임을 확정할 수 없다.', '']
    for key, label in TYPES.items():
        subset = [e for e in incidents if e['type'] == key]
        cost = Counter()
        for e in subset:
            cost.update(e['cost'])
        repeated = {e['id']: e['epoch'] for e in subset}
        gaps = sorted(e['epoch'] - repeated[e['repeat_of']] for e in subset if e['repeat_of'] in repeated)
        first = subset[0]['ts'] if subset else None
        last = subset[-1]['ts'] if subset else None
        low = sum(e['confidence'] == 'low' for e in subset)
        data[key] = {'label': label, 'count': len(subset), 'low_confidence': low,
                     'cost': dict(cost), 'first': first, 'last': last,
                     'repeat_gap_seconds': {'min': gaps[0], 'median': median(gaps), 'max': gaps[-1]} if gaps else None}
        taxonomy.extend([f'## {label}', '', RULES[key], '',
                         f'총 {len(subset)}건, 저신뢰 {low}건. 첫 {first}, 마지막 {last}. '
                         f'원장 폐기 원가 {cost.get("spoiled_cost_credits", "미산출")}, '
                         f'확인된 잠금 하한 {cost.get("locked_unit_hours", "미산출")} unit·시간.',
                         (f'동일 패턴 반복 간격 최소 {gaps[0]:.0f}초, 중앙값 {median(gaps):.0f}초, 최대 {gaps[-1]:.0f}초.'
                          if gaps else '같은 패턴 간격 자료 부족.'), ''])
        ordered = sorted(subset, key=lambda e: (e['confidence'] == 'high', len(e['evidence']), e['epoch']), reverse=True)
        selected = []
        for e in ordered:
            if e['kind'] not in {v['kind'] for v in selected}:
                selected.append(e)
        for e in (selected + [e for e in ordered if e not in selected])[:3]:
            taxonomy.append(f"- `{e['id']}` {e['description']} " + ' · '.join(map(mdref, e['evidence'])))
        taxonomy.append('')
    write('taxonomy.md', '\n'.join(taxonomy))

    version_windows = []
    for index, row in enumerate(versions):
        end = versions[index + 1]['ts'] if index + 1 < len(versions) else cutoff + 1
        observed = [r for r in between(talk, row['ts'], end) if purchase_intent(r)]
        version_windows.append({'version': row['version'], 'start': iso(row['ts']), 'end': iso(end),
                                'inquiries': len(observed), 'checkout_wording': sum(map(checkout_text, observed)),
                                'evidence': row['ref']})
    headings = ['# 개입 전후', '',
                '각 행은 로그에 남은 개입 한 건이다. 넛지와 채팅의 주제는 키워드로 추정했다. goal 변경은 커밋 시각이며 적용 시각은 키트 시작 기록을 함께 본다. 키트 시작 로그는 시도까지 포함한다. 답변 기록은 접수의 흔적이다. 실행 지시 준수는 아래 사례에서 행동으로 확인했다.', '',
                '창은 직전과 직후 1시간 및 3시간이다. †는 기록 경계에 걸친 창이다. 각 칸의 표기는 고신뢰 대상 사건/노출 대용치, 문의, 정산 순이다. 판매는 문의, 나머지는 관련 호출을 노출 대용치로 삼았다. 한 문의에 여러 실패가 생길 수 있어 비율은 성공 확률이 아니다. 빈도 증감은 인과 효과를 식별하지 않는다.', '',
                '## 행동으로 확인한 변화', '',
                '- **서명 경로 복구.** 서명·쓰기 권한은 v9~v15에 있었고 11/27 05:32 v16에서 처음 빠졌다. v16~v18 동안 자동 응대는 "결제서 발급 중 확인이 필요해요"를 냈다. v19가 권한을 되살렸고 13:05 정산은 가격 9,673크레딧과 가게 URL까지 로컬 원장에 남았다. v22에서 같은 회귀가 두 번째로 일어났고 v23에서 복원했다. [v16 forge](../logs/react.jsonl#L6802) · [실패 답변](../logs/talk.jsonl#L73) · [v19 forge](../logs/react.jsonl#L7182) · [정산 seq 19145](../logs/ledger.jsonl#L156) · [v23 forge](../logs/react.jsonl#L7523)',
                '- **지시 반영 뒤 되돌림.** 22:10 주인 지시 뒤 v25가 인증서 공란 차단을 제거했다. 같은 실행은 22:12 취나물 판매 공지를 올렸다. 22:13 sleep으로 실행이 끝난 뒤 새 실행의 22:20:12 생각 기록에서 처음 "인증서 등급이 비어 있어 … 판매하지 않겠습니다"로 되돌아갔고 22:25 판매 불가 공지가 게시됐다. 지시는 notes.md가 아니라 owner_rules.md에 적혔고, 키트는 실행마다 notes.md 끝 3,000자만 넘긴다. [주인 지시](../.kit/chat.jsonl#L239) · [v25 forge](../logs/react.jsonl#L7767) · [첫 되돌림](../logs/react.jsonl#L7778) · [공지](../logs/react.jsonl#L7785)',
                '- **goal 전면 교체.** 19:33 시작 시도 뒤 결제서를 안내한 손님 답변과 busy 답변이 모두 남았다. busy 문구는 mind가 쓴 답이 아니라 핸들러가 답하지 못하고 80초가 지난 뒤 키트가 보내는 고정 답변이다(talk의 by=mind는 "핸들러가 답하지 않음"을 뜻한다). 자정까지 추가 정산은 로컬 원장에서 확인되지 않는다. [키트 시작](../logs/agent-kit.log#L7944) · [결제서 안내](../logs/talk.jsonl#L107) · [busy](../logs/talk.jsonl#L121) · [키트 대체 답변](../kit/agent_kit.py#L684)',
                '- **마지막 넛지.** 분류 문의와 무기한 상품을 다루는 v26·v27이 나왔다. 뒤이어 빵 재고 없음 답변이 관찰됐다. 분류형 문의에서 실재고 결제서까지 간 성공은 관측 범위에서 확인되지 않는다. [넛지](../logs/nudges.jsonl#L106) · [v27 forge](../logs/react.jsonl#L7880) · [빵 문의](../logs/talk.jsonl#L124)', '',
                '서명·쓰기 권한처럼 거래에 필요한 조건을 복구한 개입에서 실제 정산까지 관찰됐다. goal 교체와 키트 시작 뒤 첫 3시간에는 시간 유형 사건이 10건에서 6건으로, 분모인 구매 문의는 12건에서 15건으로 바뀌었다. 이 집계에는 늦은 reply 호출도 들어간다. 그 사이 핸들러 버전과 문의가 달라졌고 양쪽 정산은 0건이었다. 문장 수정만의 효과나 지속적인 판매 회복은 확인할 수 없다. 공란 인증서를 다시 차단한 변경은 이전에 가능했던 판매 조건을 제거했다.', '',
                '| 시각 · 개입 | 목표 행동 · 유형 | 응답 기록 | 1시간 전 → 후 | 3시간 전 → 후 | 3시간 판정 · 다음 동일 유형 |', '|---|---|---|---|---|---|']
    for i in interventions:
        title = mdref(i['evidence'])
        if 'commit' in i['evidence']:
            title += f" `{i['evidence']['commit'][:7]}`"
        stats = []
        for w in i['windows'].values():
            stats.append(' → '.join(f"{v['same_type']}/{v['exposure_proxy']}, {v['inquiries']}, {v['settlements']}" + ('' if v['complete'] else ' †') for v in w))
        headings.append(f"| {i['ts'][5:19]} {i['kind']} {title} | {i['focus']} · {TYPES.get(i['target'], '미특정')} | "
                        f"{i['receipt']} | {stats[0]} | {stats[1]} | {i['verdict']} · {i['next_incident'] or '관측 없음'} |")
    headings.extend([''] + REVIEW_1128 + [
        '## 주인 직접 지시와 넛지의 자동 반응 기록', '',
        '전 구간 자동 집계다. 말 = 30분 안 busy가 아닌 에이전트 채팅 답. 기록 = 1시간 안 owner_rules·메모 쓰기. 변경 = 1시간 안 도구 통과·압축·실매입·게시·카드. '
        '같은 유형 = 첫 변경 뒤 3시간 안 같은 유형 고신뢰 사건으로, 되돌림의 후보일 뿐 판정이 아니다. 주제가 다른 변경도 들어가므로 판정은 위 검토표를 따른다.', '',
        '| 시각 · 개입 | 주제 | 말 | 기록 | 1시간 안 변경 | 변경 뒤 같은 유형 |', '|---|---|---|---|---|---|'])
    for i in interventions:
        r = i.get('response')
        if not r:
            continue
        changes = Counter(c['action'] for c in r['changes'])
        headings.append(f"| {i['ts'][5:16]} {i['kind']} {mdref(i['evidence'])} | {TYPES.get(i['target'], '미특정')} | "
                        f"{mdref(r['words']) if r['words'] else '없음'} | {len(r['recorded'])} | "
                        f"{', '.join(f'{k} {v}' for k, v in changes.items()) or '없음'} | {r['same_type_after_change'] or '—'} |")
    headings.extend(['', '## 도구 버전별 구매 문의',
                     '', '등록 시각으로 답변 시점의 버전을 추정했다. 문의 내용과 실제 재고가 버전마다 다르며 일부 창이 매우 짧다. 결제서 안내는 텍스트 관측치다.',
                     '', '| 버전 | 구매 문의 | 결제서 안내 | 근거 |', '|---|---:|---:|---|'])
    for v in version_windows:
        if v['version'] >= 17 or v['inquiries']:
            headings.append(f"| v{v['version']} | {v['inquiries']} | {v['checkout_wording']} | {mdref(v['evidence'])} |")
    write('interventions.md', '\n'.join(headings))
    for values in hourly.values():
        steps = values['activity_steps']
        total = sum(v for k, v in steps.items() if k != '휴식 전환')
        values['activity_step_share'] = {k: round(steps[k] / total, 4) for k in ('조사', '판매', '수선')} if total else {}
    ranked = sorted(incidents, key=lambda e: (e['kind'] in {'handler_regression', 'owner_rule_reversal',
                    'checkout_lost_to_timeout', 'currency_confusion', 'false_zero_settlements',
                    'restock_window_missed', 'buyer_condition_ignored', 'checkout_rate_drop', 'restore_not_faithful',
                    'inverse_purchase', 'directive_not_executed', 'handler_churn', 'read_scope_misread'},
                    len(e['evidence'])), reverse=True)
    top, per_kind = [], Counter()
    for e in ranked:  # 같은 종류는 두 건까지만 올려 한 패턴이 목록을 채우지 않게 한다
        if per_kind[e['kind']] < 2 and len(top) < 12:
            top.append(e)
            per_kind[e['kind']] += 1
    dump('summary.json', {'schema_version': 1, 'timezone': 'Asia/Seoul', 'through': iso(cutoff),
                          'coverage': {'react_from': iso(react[0]['ts']), 'react_through': iso(react[-1]['ts']),
                                       'talk_from': iso(talk[0]['ts']), 'talk_through': iso(talk[-1]['ts']),
                                       'settlements': len(settles), 'auto_checkout_without_receipt': sum(r.get('delivery_status') == 'unknown_no_delivery_receipt' for r in auto), 'missing_or_malformed': dict(MISSING)},
                          'types': data, 'handler_versions': version_windows, 'hourly': dict(sorted(hourly.items())),
                          'top_incidents': [{k: e[k] for k in ('id', 'ts', 'description', 'type')} for e in top],
                          'intervention_counts': Counter(i['verdict'] for i in interventions),
                          'interventions': interventions})


if __name__ == '__main__':
    main()
