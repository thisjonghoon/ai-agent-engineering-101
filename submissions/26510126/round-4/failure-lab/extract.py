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
    'unknown': '원인 미확인',
}
MISSING = Counter()


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
    return bool(re.search(r'결제서를 (?:함께 |바로 )?(?:보냅니다|보내요|보내드려요|드립니다|첨부했습니다)|서명된 결제서입니다', reply))


def main():
    react = sorted(load('logs/react.jsonl'), key=lambda r: r['ts'])
    talk = sorted(load('logs/talk.jsonl'), key=lambda r: r['ts'])
    forge = sorted(load('logs/forge.jsonl'), key=lambda r: r['ts'])
    ledger = sorted(load('logs/ledger.jsonl'), key=lambda r: r['ts'])
    chat = sorted(load('.kit/chat.jsonl'), key=lambda r: r['ts'])
    nudges = load('logs/nudges.jsonl')
    for row in nudges:
        try:
            sent = datetime.strptime(row['time'], '%m/%d %H:%M:%S')
        except (KeyError, ValueError):
            continue
        year = datetime.fromtimestamp(row['ts'], KST).year
        row['ts'] = sent.replace(year=year, tzinfo=KST).timestamp()
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

    def emit(row, kind, category, description, *, extra=(), cost=None, low=False,
             customer=None, item=None, tool=None, state=None, repeat_key=None):
        ref = row['ref']
        ts = row['ts']
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
        elif purchase_intent(row) and not checkout_text(row) and not re.search(
            r'재고가 없|재고는 없|재고가 지금 없|재고가 모두 없|않습니다|않겠|구매하지|취급', reply
        ):
            emit(row, 'no_checkout_in_text', 'unknown', '구매 관련 답변에서 결제서 전달 문구가 확인되지 않았다.',
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

    interventions = compare(incidents, react, talk, settles, forge, nudges, owner, goal, restart, cutoff)
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
    emit(at(talk, 119), 'buyer_condition_ignored', 'policy',
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


def compare(incidents, react, talk, settles, forge, nudges, owner, goal, restart, cutoff):
    result = []
    labels = [('넛지', nudges), ('주인 채팅', owner), ('goal 변경', goal), ('키트 시작 시도', restart)]
    for label, rows in labels:
        for row in rows:
            ts = row['ts']
            ref = row['ref']
            category = topic(row.get('text', ''))
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
            result.append({'kind': label, 'ts': iso(ts), 'evidence': ref, 'target': category,
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
    'tests': '코드 변경으로 기존 경로가 좁아졌거나 체크아웃 호출에서 처리 오류가 난 사례. 매입의 비시간창 오류도 포함한다.',
    'memory': '주인 지시 뒤 같은 규칙과 어긋나는 코드 변경 또는 외부 행동을 확인한 사례.',
    'policy': '대기 손님 없는 발급, 손님 조건 배제 누락, 기존 결제서 관련 잠금·중복 방어가 관찰된 사례.',
    'meaning': '단위, 등급·인증서, 원장 집계 또는 견적의 의미 혼선. 등급 불일치 보호 동작도 포함한다.',
    'market': '원장 만료, 매입 HTTP 실패, 열리기 직전 확인했으나 놓친 재입고 창.',
    'unknown': '답변 텍스트는 있으나 실패 또는 원인을 판정하기에 데이터가 부족한 구매 관련 대화.',
}


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
                '- **서명 경로 복구.** v19는 부모 도구에 필요한 권한을 추가했다. 13:05 정산은 가격 9,673크레딧과 가게 URL까지 로컬 원장에 남았다. v22에서는 권한이 다시 빠졌고, v23에서 복원했다. [v19 forge](../logs/react.jsonl#L7182) · [정산 seq 19145](../logs/ledger.jsonl#L156) · [v23 forge](../logs/react.jsonl#L7523)',
                '- **지시 반영 뒤 되돌림.** 22:10 주인 지시 뒤 v25가 인증서 공란 차단을 제거했다. 22:25 판매 불가 공지가 실제 게시됐다. 이 사례에서는 답변뿐 아니라 코드도 바뀌었으나 운영 행동은 되돌아갔다. [주인 지시](../.kit/chat.jsonl#L239) · [v25 forge](../logs/react.jsonl#L7767) · [공지](../logs/react.jsonl#L7785)',
                '- **goal 전면 교체.** 19:33 시작 시도 뒤 결제서를 안내한 손님 답변과 busy 답변이 모두 남았다. 자정까지 추가 정산은 로컬 원장에서 확인되지 않는다. [키트 시작](../logs/agent-kit.log#L7944) · [결제서 안내](../logs/talk.jsonl#L107) · [busy](../logs/talk.jsonl#L121)',
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
                    'restock_window_missed', 'buyer_condition_ignored'}, len(e['evidence'])), reverse=True)
    dump('summary.json', {'schema_version': 1, 'timezone': 'Asia/Seoul', 'through': iso(cutoff),
                          'coverage': {'react_from': iso(react[0]['ts']), 'react_through': iso(react[-1]['ts']),
                                       'talk_from': iso(talk[0]['ts']), 'talk_through': iso(talk[-1]['ts']),
                                       'settlements': len(settles), 'auto_checkout_without_receipt': sum(r.get('delivery_status') == 'unknown_no_delivery_receipt' for r in auto), 'missing_or_malformed': dict(MISSING)},
                          'types': data, 'handler_versions': version_windows, 'hourly': dict(sorted(hourly.items())),
                          'top_incidents': [{k: e[k] for k in ('id', 'ts', 'description', 'type')} for e in ranked[:12]],
                          'intervention_counts': Counter(i['verdict'] for i in interventions),
                          'interventions': interventions})


if __name__ == '__main__':
    main()
