import datetime
import importlib.util
import json
import os
import re
import statistics
import time

import httpx

ALIASES = {'계란':['계란','달걀'],'요거트':['요거트','요구르트'],'시금치':['시금치'],'사과':['사과'],'취나물':['취나물'],'둥굴레차':['둥굴레차','둥굴레 차','둥굴레'],'티슈':['티슈','휴지','화장지','크리넥스'],'김치':['김치'],'두부':['두부'],'콩나물':['콩나물'],'쌀':['쌀','백미'],'생수':['생수','물'],'우유':['우유'],'빵':['빵'],'세제':['세제']}
GRADE = re.compile(r'(?<![A-Za-z0-9])([ABC])\s*(?:등급|급)(?:\s*(이상|이하|초과|미만))?', re.I)
DURATION = re.compile(r'(?<![\d.])(\d+)\s*(일|시간|분)\s*(이상|초과)')
EXPIRY = re.compile(r'소비\s*기한|유통\s*기한|만료|잔여|기한|남은|남아|신선|짧은|임박')

def run(args, kit):
    text = str(args.get('text') or '')
    if not text.strip() or re.search(r'환불|불만|항의|할인|깎아|흥정|반품|손상|잘못|결제했|제외|빼고|말고|싫|거절|안\s*(?:사|되|돼|받)|아니|이거나|또는|혹은|보다는|보다\s*[높낮]|미달|넘게|이내', text):
        return {'defer': True}
    explicit = set(re.findall(r'\bG[0-9a-fA-F]{8}(?![0-9a-fA-F])', text))
    keys = [key for key, words in ALIASES.items() if any(word in text for word in words)]
    packs = set(re.findall(r'(?<!\d)(\d+)\s*구', text))
    if (not explicit and not keys) or len(explicit) > 1 or len(keys) > 1 or len(packs) > 1:
        return {'defer': True}
    grades = list(GRADE.finditer(text))
    grade_tail = GRADE.sub('', text)
    if len(grades) > 1 or re.search(r'등급|(?<![A-Za-z0-9])(?:[ABCabc][+-]|[12]\+)', grade_tail):
        return {'defer': True}
    allowed = None
    if grades:
        grade, relation = grades[0].groups()
        rank = 'CBA'.index(grade.upper())
        allowed = {value for index, value in enumerate('CBA') if {None:index == rank, '이상':index >= rank, '이하':index <= rank, '초과':index > rank, '미만':index < rank}[relation]}
    duration = list(DURATION.finditer(grade_tail))
    remaining_text = DURATION.sub('', grade_tail)
    if len(duration) > 1 or (EXPIRY.search(text) and not duration):
        return {'defer': True}
    minimum = 0
    exclusive = False
    if duration:
        if not EXPIRY.search(text) or re.search(r'\d+\s*(?:일|시간|분|주|개월)|짧|임박|신선|미만|이하|최대|이상|초과|까지|오늘|내일|모레|이번\s*주', remaining_text):
            return {'defer': True}
        amount, unit, relation = duration[0].groups()
        minimum = int(amount) * {'일':86400, '시간':3600, '분':60}[unit]
        exclusive = relation == '초과'
    try:
        entries = []
        if kit.testing:
            units = args.get('_units', [])
        else:
            base = kit.market.rstrip('/')
            with httpx.Client(timeout=12) as client:
                response = client.get(base + '/api/inventory', headers={'authorization':'Bearer ' + kit.token('shop')})
                response.raise_for_status()
                units = response.json()['units']
                after = 0
                for _ in range(150):
                    response = client.get(base + '/api/ledger', params={'after':after})
                    response.raise_for_status()
                    page = response.json()
                    if isinstance(page, dict):
                        page = page['entries']
                    if not page:
                        break
                    entries.extend(page)
                    next_after = max(int(event['seq']) for event in page)
                    if next_after <= after:
                        raise ValueError('ledger pagination stalled')
                    after = next_after
        def eligible(unit):
            if explicit and unit.get('sku') not in explicit:
                return False
            labels = ' '.join(str(unit.get(field) or '') for field in ('name', 'category'))
            if not explicit and not any(word in labels for key in keys for word in ALIASES[key]):
                return False
            if allowed is not None and unit.get('grade') not in allowed:
                return False
            spec = ' '.join(str(unit.get(field) or '') for field in ('name', 'spec'))
            if packs and set(re.findall(r'(?<!\d)(\d+)\s*구', spec)) != packs:
                return False
            expiry = unit.get('expires_at')
            if not expiry:
                return not duration
            left = float(expiry) - time.time()
            return left > 0 and (left > minimum if exclusive else left >= minimum)
        candidates = [unit for unit in units if eligible(unit)]
        candidates.sort(key=lambda unit: (-(unit.get('expires_at') or 0), unit.get('cost', 0)))
        if kit.testing and args.get('_inspect_candidates'):
            return {'units':[unit['unit'] for unit in candidates]}
        if not candidates:
            return {'reply':'말씀하신 품목·포장·등급·남은 기한에 맞는 재고가 지금 없어요.', 'state':'completed'}
        spec = importlib.util.spec_from_file_location('checkout_impl', 'tools/make_checkout/logic.py')
        checkout = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(checkout)
        for unit in candidates:
            if not eligible(unit):
                continue
            prices = [event['data']['amount'] for event in entries if event.get('kind') == 'settle' and event.get('data', {}).get('sku') == unit['sku'] and isinstance(event['data'].get('amount'), int)]
            cost = int(unit['cost'])
            price = max(((cost + 210) * 100 + 98) // 99, int(statistics.median(prices[-10:])) if prices else 0)
            result = checkout.run({'sku':unit['sku'], 'unit':unit['unit'], 'price':price, 'cost':cost, 'claim':unit.get('grade'), 'task':args.get('task_id')}, kit)
            if not result.get('checkout_jwt'):
                continue
            payload = result['payload']
            now = time.time()
            expiry = unit.get('expires_at')
            timing = '시장 기록 만료 시각 미표기'
            if expiry:
                kst = datetime.timezone(datetime.timedelta(hours=9))
                date = datetime.datetime.fromtimestamp(expiry, kst).strftime('%m월 %d일 %H:%M KST')
                minutes = max(0, int((expiry - now) // 60))
                timing = f'시장 기록 만료까지 {minutes//1440}일 {minutes%1440//60}시간 {minutes%60}분 ({date})'
            grade = unit.get('grade')
            grade_label = grade + '등급' if grade else '등급 미확인'
            reply = f"{unit['name']} {grade_label}, {timing}, {price}크레딧입니다. 결제서를 함께 보내드려요."
            record = {'ts':now, 'unit':unit['unit'], 'sku':unit['sku'], 'id':payload['id'], 'price':price, 'task':payload.get('task'), 'recipient_claimed_unverified':args.get('claimed_from'), 'context_id':args.get('context_id'), 'reply':reply, 'delivery_status':'unknown_no_delivery_receipt', 'checkout_jwt':result['checkout_jwt'], 'payload':payload}
            if not kit.testing:
                with open('auto_checkout.jsonl', 'a', encoding='utf8') as log:
                    log.write(json.dumps(record, ensure_ascii=False) + '\n')
                    log.flush()
                    os.fsync(log.fileno())
            return {'reply':reply, 'data':{'checkout_jwt':result['checkout_jwt'], 'checkout':payload}, 'state':'completed'}
        return {'reply':'맞는 재고는 있으나 현재 결제 가능한 수량이 없어요.', 'state':'completed'}
    except Exception:
        return {'defer': True}
