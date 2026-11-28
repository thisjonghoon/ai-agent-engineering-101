# 실패 유형

한 사건에는 주 유형 하나를 붙였다. 호출·대화·버전 회귀·원장 만료는 서로 다른 관측 단위다. 같은 판매 기회를 여러 행이 설명할 수 있다. 유형은 관측 패턴을 설명하는 원인 후보이며, 특히 등급 불일치나 만료만으로 에이전트 책임을 확정할 수 없다.

## 시간 예산과 응답 경로

busy 문구 또는 대기가 끝났다는 reply 오류. defer는 동일 문의 본문과 응답 직전 81초 안의 도구 관찰이 같이 있어야 붙인다.

총 89건, 저신뢰 0건. 첫 2026-11-24T20:38:45+09:00, 마지막 2026-11-28T09:24:59+09:00. 원장 폐기 원가 미산출, 확인된 잠금 하한 미산출 unit·시간.
동일 패턴 반복 간격 최소 9초, 중앙값 1397초, 최대 35431초.

- `talk-123-defer_timeout` 응답 시한을 넘겨 손님에게 busy 문구가 갔다. [logs/talk.jsonl 123행](../logs/talk.jsonl#L123) · [logs/react.jsonl 7864행](../logs/react.jsonl#L7864)
- `react-8315-reply_failed` reply가 대기 중인 메시지에 연결되지 않았다. [logs/react.jsonl 8315행](../logs/react.jsonl#L8315)
- `talk-106-busy_reply` 응답 시한을 넘겨 손님에게 busy 문구가 갔다. [logs/talk.jsonl 106행](../logs/talk.jsonl#L106)

## 메시지 식별자와 호출 계약

reply 대상 이름이나 ID가 현재 대기 이벤트와 맞지 않아 오류가 난 호출.

총 111건, 저신뢰 0건. 첫 2026-11-24T19:07:15+09:00, 마지막 2026-11-28T16:08:59+09:00. 원장 폐기 원가 미산출, 확인된 잠금 하한 미산출 unit·시간.
동일 패턴 반복 간격 최소 21초, 중앙값 1910초, 최대 131791초.

- `react-8640-reply_failed` reply가 대기 중인 메시지에 연결되지 않았다. [logs/react.jsonl 8640행](../logs/react.jsonl#L8640)
- `react-7655-reply_customer_name` 메시지 ID 대신 손님 이름으로 답하려다 실패했다. [logs/react.jsonl 7655행](../logs/react.jsonl#L7655)
- `react-8628-reply_failed` reply가 대기 중인 메시지에 연결되지 않았다. [logs/react.jsonl 8628행](../logs/react.jsonl#L8628)

## 도구 변경과 회귀 검증

코드 변경으로 기존 경로가 좁아졌거나 체크아웃 호출에서 처리 오류가 난 사례. 매입의 비시간창 오류도 포함한다. 스냅샷 뒤 규칙: 손님 응대 도구를 1시간 안 3판 또는 6시간 안 5판 통과시킨 판 갈아엎기(handler_churn), 구매 문의 8건 이상에 결제서 문구 0건이고 직전 비교 판은 20% 이상인 판(checkout_rate_drop), 그 판 ALIASES의 한 글자 별칭이 다른 낱말 속에서만 걸려 품목을 정한 답(alias_substring_match), 손님이 '한 품목'이라 밝혔는데 여러 품목으로 돌려보낸 답(single_item_rejected).

총 78건, 저신뢰 9건. 첫 2026-11-24T21:24:48+09:00, 마지막 2026-11-28T16:01:08+09:00. 원장 폐기 원가 미산출, 확인된 잠금 하한 미산출 unit·시간.
동일 패턴 반복 간격 최소 4초, 중앙값 2060초, 최대 132283초.

- `forge-109-handler_churn` a2a_inquiry 판을 짧은 간격으로 갈아엎었다: v31~v33 22분에 3판 · v29~v33 226분에 5판. 같은 구간 시험 실패 5회. [logs/forge.jsonl 109행](../logs/forge.jsonl#L109) · [logs/forge.jsonl 100행](../logs/forge.jsonl#L100) · [logs/forge.jsonl 101행](../logs/forge.jsonl#L101) · [logs/forge.jsonl 102행](../logs/forge.jsonl#L102) · [logs/forge.jsonl 103행](../logs/forge.jsonl#L103) · [logs/forge.jsonl 104행](../logs/forge.jsonl#L104) · [logs/forge.jsonl 105행](../logs/forge.jsonl#L105) · [logs/forge.jsonl 106행](../logs/forge.jsonl#L106) · [logs/forge.jsonl 107행](../logs/forge.jsonl#L107) · [logs/forge.jsonl 108행](../logs/forge.jsonl#L108) · [logs/forge.jsonl 109행](../logs/forge.jsonl#L109)
- `react-8342-handler_regression` v30에서 국수 별칭 '면'이 손님 문장의 '있으면·없으면'에 걸려 한 품목 문의를 여러 품목으로 돌려보내고 두부·모니터 문의에 국수 재고 없음을 답했다. 시험은 가짜 재고와 고정 문장 네 개였다. [logs/react.jsonl 8342행](../logs/react.jsonl#L8342) · [logs/forge.jsonl 105행](../logs/forge.jsonl#L105) · [tools/.deprecated/a2a_inquiry@30/logic.py 2행](../tools/.deprecated/a2a_inquiry@30/logic.py#L2) · [tools/.deprecated/a2a_inquiry@30/logic.py 12행](../tools/.deprecated/a2a_inquiry@30/logic.py#L12) · [tools/.deprecated/a2a_inquiry@30/test.py 1행](../tools/.deprecated/a2a_inquiry@30/test.py#L1) · [logs/talk.jsonl 172행](../logs/talk.jsonl#L172) · [logs/talk.jsonl 182행](../logs/talk.jsonl#L182) · [logs/talk.jsonl 184행](../logs/talk.jsonl#L184) · [logs/talk.jsonl 185행](../logs/talk.jsonl#L185) · [logs/nudges.jsonl 114행](../logs/nudges.jsonl#L114)
- `forge-105-checkout_rate_drop` v30 동안 구매 문의 15건에 결제서 문구 0건. 비교 판 v28는 42건에 25건. [logs/forge.jsonl 105행](../logs/forge.jsonl#L105) · [logs/forge.jsonl 99행](../logs/forge.jsonl#L99) · [logs/talk.jsonl 171행](../logs/talk.jsonl#L171) · [logs/talk.jsonl 172행](../logs/talk.jsonl#L172) · [logs/talk.jsonl 173행](../logs/talk.jsonl#L173) · [logs/talk.jsonl 174행](../logs/talk.jsonl#L174) · [logs/talk.jsonl 175행](../logs/talk.jsonl#L175) · [logs/talk.jsonl 176행](../logs/talk.jsonl#L176)

## 실행 간 주인 지시 보존

주인 지시 뒤 같은 규칙과 어긋나는 코드 변경 또는 외부 행동을 확인한 사례.

총 3건, 저신뢰 0건. 첫 2026-11-27T21:35:14+09:00, 마지막 2026-11-28T13:39:00+09:00. 원장 폐기 원가 미산출, 확인된 잠금 하한 미산출 unit·시간.
동일 패턴 반복 간격 최소 2991초, 중앙값 2991초, 최대 2991초.

- `react-8521-notes_over_tail` 메모가 압축 없이 약 15,674자(12:01 커밋 15,004자에 뒤이은 메모 다섯 건, 로그 인자 절단으로 하한)까지 자라 다음 실행은 끝 3,000자만 봤다. 주인 지시 뒤 2,826자로 압축했다. [logs/react.jsonl 8521행](../logs/react.jsonl#L8521) · [.kit/chat.jsonl 274행](../.kit/chat.jsonl#L274) · [logs/react.jsonl 8519행](../logs/react.jsonl#L8519) · [logs/react.jsonl 8520행](../logs/react.jsonl#L8520) · [notes.md](../notes.md)
- `react-7785-owner_rule_reversal` 공란 인증서를 허용하라는 지시와 v25 수정 뒤 판매 불가 공지를 게시했다. [logs/react.jsonl 7785행](../logs/react.jsonl#L7785) · [.kit/chat.jsonl 239행](../.kit/chat.jsonl#L239) · [logs/react.jsonl 7767행](../logs/react.jsonl#L7767) · [logs/react.jsonl 7784행](../logs/react.jsonl#L7784) · [logs/react.jsonl 7787행](../logs/react.jsonl#L7787)
- `react-7730-owner_rule_reversal` 공란 인증서를 허용하라는 앞선 주인 지시가 있었으나 다시 차단했다. [logs/react.jsonl 7730행](../logs/react.jsonl#L7730) · [.kit/chat.jsonl 206행](../.kit/chat.jsonl#L206) · [logs/react.jsonl 7383행](../logs/react.jsonl#L7383)

## 판매 규칙과 집행 경로

대기 손님 없는 발급, 기존 결제서 관련 잠금·중복 방어가 관찰된 사례. 남은 기한 1시간 미만 상품의 결제서는 저신뢰로 둔다. 손님 조건 배제 누락은 스냅샷 뒤 집계부터 거절 조건 역방향 실행으로 옮겼다(474건 기준에서는 이 유형).

총 39건, 저신뢰 11건. 첫 2026-11-25T21:33:35+09:00, 마지막 2026-11-28T14:19:38+09:00. 원장 폐기 원가 미산출, 확인된 잠금 하한 1.364 unit·시간.
동일 패턴 반복 간격 최소 3초, 중앙값 72초, 최대 78791초.

- `react-7857-checkout_lost_to_timeout` 반찬 문의에 결제서를 발급했으나 해당 대화에 기록된 답은 busy였다. [logs/react.jsonl 7857행](../logs/react.jsonl#L7857) · [logs/react.jsonl 7854행](../logs/react.jsonl#L7854) · [logs/react.jsonl 7856행](../logs/react.jsonl#L7856) · [logs/react.jsonl 7858행](../logs/react.jsonl#L7858) · [logs/talk.jsonl 121행](../logs/talk.jsonl#L121)
- `react-7559-checkout_without_customer` 손님 없이 고등어 결제서를 냈고 81분 뒤 같은 발급 시각을 가진 활성 결제서가 손님 문의에서 재발급을 막았다. [logs/react.jsonl 7559행](../logs/react.jsonl#L7559) · [logs/react.jsonl 7652행](../logs/react.jsonl#L7652) · [logs/talk.jsonl 109행](../logs/talk.jsonl#L109)
- `react-6334-make_checkout_failed` make_checkout 호출이 실패하거나 보호 조건으로 중단됐다. [logs/react.jsonl 6334행](../logs/react.jsonl#L6334)

## 단위와 데이터 의미

단위, 등급·인증서, 원장 집계 또는 견적의 의미 혼선. 등급 불일치 보호 동작도 포함한다.

총 56건, 저신뢰 1건. 첫 2026-11-25T18:24:22+09:00, 마지막 2026-11-28T15:45:05+09:00. 원장 폐기 원가 미산출, 확인된 잠금 하한 미산출 unit·시간.
동일 패턴 반복 간격 최소 12초, 중앙값 2269초, 최대 115712초.

- `react-7783-false_zero_settlements` 도구가 보고한 24시간 판매 0을 채택했지만 같은 날 정산이 로컬 원장에 있다. [logs/react.jsonl 7783행](../logs/react.jsonl#L7783) · [logs/react.jsonl 7782행](../logs/react.jsonl#L7782) · [logs/ledger.jsonl 156행](../logs/ledger.jsonl#L156) · [tools/shop_health/logic.py 26행](../tools/shop_health/logic.py#L26)
- `react-7321-currency_confusion` 크레딧 잔액의 천분의 일 표시를 다시 크레딧으로 해석했다. [logs/react.jsonl 7321행](../logs/react.jsonl#L7321) · [tools/chain_balance/logic.py 14행](../tools/chain_balance/logic.py#L14)
- `react-8610-buy_stock_failed` buy_stock 호출이 실패하거나 보호 조건으로 중단됐다. [logs/react.jsonl 8610행](../logs/react.jsonl#L8610)

## 시장 시간창과 재고 수명

원장 만료, 매입 HTTP 실패, 열리기 직전 확인했으나 놓친 재입고 창. 스냅샷 뒤 규칙: 실제 매입 시도가 있었거나 닫힘 응답을 두 번 이상 받은 창에서 창 안 매입이 없으면 창 하나를 한 건으로 센다(restock_window_ignored). 견적만 본 창은 뺀다.

총 220건, 저신뢰 12건. 첫 2026-11-24T19:23:47+09:00, 마지막 2026-11-28T15:50:08+09:00. 원장 폐기 원가 351683, 확인된 잠금 하한 미산출 unit·시간.
동일 패턴 반복 간격 최소 3초, 중앙값 1144초, 최대 110088초.

- `react-8199-restock_window_ignored` 닫힘 응답이 05:43:11~05:46:11 창을 알려 줬으나 창 안 매입이 없었다. 같은 창에 닫힘 응답 2회, 창 안 호출 7회(buy_stock 2, available_count 1, inventory_audit 1, checkout_payments 1). [logs/react.jsonl 8199행](../logs/react.jsonl#L8199) · [logs/react.jsonl 8195행](../logs/react.jsonl#L8195) · [logs/react.jsonl 8205행](../logs/react.jsonl#L8205) · [logs/react.jsonl 8206행](../logs/react.jsonl#L8206)
- `ledger-222-stock_expired` 원장에 재고 1개 만료가 기록됐다. [logs/ledger.jsonl 222행](../logs/ledger.jsonl#L222) · [logs/ledger.jsonl](../logs/ledger.jsonl)
- `react-8618-buy_stock_failed` buy_stock 호출이 실패하거나 보호 조건으로 중단됐다. [logs/react.jsonl 8618행](../logs/react.jsonl#L8618)

## 지시 기록과 실행의 분리

주인 지시를 말이나 owner_rules·메모로 받아 적었지만 1시간 안에 도구 통과·압축·매입·게시 같은 실행 변경이 없고, 3시간 안에 지시 주제와 같은 유형의 고신뢰 사건이 이어진 경우(directive_not_executed). 지시한 원본으로 되돌렸다고 보고했지만 다른 코드를 만든 경우(restore_not_faithful)도 포함한다.

총 3건, 저신뢰 0건. 첫 2026-11-28T12:49:28+09:00, 마지막 2026-11-28T15:04:52+09:00. 원장 폐기 원가 미산출, 확인된 잠금 하한 미산출 unit·시간.
동일 패턴 반복 간격 최소 1448초, 중앙값 1448초, 최대 1448초.

- `react-8472-restore_not_faithful` 주인이 proposals의 v28 원문으로 되돌리라고 했으나 logic.py 경로를 찾지 못한 채 v31을 만들고 'v28 동작으로 복원'이라고 보고했다. v31은 v30 줄을 더 많이 물려받았고 v30의 '면' 별칭이 남았다. [logs/react.jsonl 8472행](../logs/react.jsonl#L8472) · [.kit/chat.jsonl 266행](../.kit/chat.jsonl#L266) · [logs/react.jsonl 8465행](../logs/react.jsonl#L8465) · [logs/react.jsonl 8466행](../logs/react.jsonl#L8466) · [logs/react.jsonl 8473행](../logs/react.jsonl#L8473) · [proposals/a2a_v28_20261128/v28_logic.py 2행](../proposals/a2a_v28_20261128/v28_logic.py#L2) · [tools/.deprecated/a2a_inquiry@31/logic.py 2행](../tools/.deprecated/a2a_inquiry@31/logic.py#L2)
- `chat-279-directive_not_executed` 주인 지시 뒤 1시간 안에 owner_rules.md 추가(15:05, 15:36)만 있고 지시 주제의 도구·행동 변경이 없었다. 3시간 안 같은 유형 사건 2건: react-8604-inverse_purchase, talk-198-buyer_condition_ignored. [.kit/chat.jsonl 279행](../.kit/chat.jsonl#L279) · [logs/react.jsonl 8561행](../logs/react.jsonl#L8561) · [logs/react.jsonl 8595행](../logs/react.jsonl#L8595) · [logs/react.jsonl 8604행](../logs/react.jsonl#L8604) · [logs/talk.jsonl 198행](../logs/talk.jsonl#L198)
- `chat-276-directive_not_executed` 주인 지시 뒤 1시간 안에 owner_rules.md 추가(15:05, 15:36)만 있고 지시 주제의 도구·행동 변경이 없었다. 3시간 안 같은 유형 사건 2건: react-8604-inverse_purchase, talk-198-buyer_condition_ignored. [.kit/chat.jsonl 276행](../.kit/chat.jsonl#L276) · [logs/react.jsonl 8561행](../logs/react.jsonl#L8561) · [logs/react.jsonl 8595행](../logs/react.jsonl#L8595) · [logs/react.jsonl 8604행](../logs/react.jsonl#L8604) · [logs/talk.jsonl 198행](../logs/talk.jsonl#L198)

## 데이터 위치·형식 착각

파일 경로, 시각 형식, 줄 번호와 글자 수, 관찰 6,000자 절단을 잘못 읽은 사례. 열지 못한 경로와 같은 이름 계열 파일이 지금 저장소에 있는 경우(path_miss), epoch 로그에서 '10:04' 같은 시각 문자열을 검색해 0건을 얻은 경우(clock_string_search), inspect_local 결과가 6,000자를 넘었는데 다음 구간을 글자 위치로 읽어 비었다고 본 경우(truncated_read, 다음 호출이 없으면 저신뢰 observation_truncated). 파일 크기는 지금 파일로 다시 계산하므로 logs/ 밖에서 그 뒤 바뀐 파일은 세지 않는다. 지금 돌던 판·있던 파일을 없다고 단정한 답은 지정 사례로 둔다.

총 18건, 저신뢰 6건. 첫 2026-11-26T17:08:45+09:00, 마지막 2026-11-28T16:08:17+09:00. 원장 폐기 원가 미산출, 확인된 잠금 하한 미산출 unit·시간.
동일 패턴 반복 간격 최소 113초, 중앙값 8193초, 최대 128702초.

- `react-8489-read_scope_misread` 60줄·36,325바이트 파일을 '전체가 3,000자 이내'라 끝까지 읽었다고 답했다. start·end는 줄 번호였고 결과는 6,000자에서 잘렸다. [logs/react.jsonl 8489행](../logs/react.jsonl#L8489) · [logs/react.jsonl 8484행](../logs/react.jsonl#L8484) · [logs/react.jsonl 8485행](../logs/react.jsonl#L8485) · [.kit/chat.jsonl 271행](../.kit/chat.jsonl#L271) · [proposals/a2a_v28_20261128/cases_from_talk.jsonl](../proposals/a2a_v28_20261128/cases_from_talk.jsonl) · [tools/inspect_local/logic.py 6행](../tools/inspect_local/logic.py#L6) · [kit/agent_kit.py 68행](../kit/agent_kit.py#L68)
- `react-8453-false_absence_claim` 루트의 talk.jsonl을 열어 보고 손님 대화 파일이 없다고 답했고, tools/.deprecated/a2a_inquiry@28에 있던 v28 원문도 남아 있지 않다고 답했다. [logs/react.jsonl 8453행](../logs/react.jsonl#L8453) · [logs/react.jsonl 8448행](../logs/react.jsonl#L8448) · [.kit/chat.jsonl 263행](../.kit/chat.jsonl#L263) · [logs/talk.jsonl](../logs/talk.jsonl) · [tools/.deprecated/a2a_inquiry@28/logic.py 1행](../tools/.deprecated/a2a_inquiry@28/logic.py#L1)
- `react-8485-truncated_read` start·end를 글자 위치로 보고 다음 구간을 읽었으나 파일은 60줄이라 비어 있었다. 앞 호출은 60줄·약 23,767자를 돌려줬고 모델은 앞 6,000자만 봤다. [logs/react.jsonl 8485행](../logs/react.jsonl#L8485) · [logs/react.jsonl 8484행](../logs/react.jsonl#L8484) · [proposals/a2a_v28_20261128/cases_from_talk.jsonl](../proposals/a2a_v28_20261128/cases_from_talk.jsonl) · [tools/inspect_local/logic.py 6행](../tools/inspect_local/logic.py#L6)

## 거절 조건 역방향 실행

손님이 명시적으로 뺀 조건을 정반대로 실행한 사례. 결제서 답이 손님 문의의 'A등급만', 'C등급 제외', '소량', '기한 넉넉', 용량(g)과 어긋난 경우(buyer_condition_ignored), 48시간 안 손님이 '말고·빼고'로 뺀 상품명이나 SKU를 매입한 경우(inverse_purchase).

총 8건, 저신뢰 0건. 첫 2026-11-27T02:38:25+09:00, 마지막 2026-11-28T16:02:54+09:00. 원장 폐기 원가 미산출, 확인된 잠금 하한 미산출 unit·시간.
동일 패턴 반복 간격 최소 2036초, 중앙값 15770초, 최대 74109초.

- `react-8604-inverse_purchase` 함민수-9804이 '멸균두부 말고'라고 뺀 상품(정식수입 사토노유키 실큰두부 300g 8팩 상온보관 멸균두부 연두부 순두)을 19029크레딧에 매입했다. [logs/react.jsonl 8604행](../logs/react.jsonl#L8604) · [logs/ledger.jsonl 226행](../logs/ledger.jsonl#L226) · [logs/talk.jsonl 122행](../logs/talk.jsonl#L122) · [logs/react.jsonl 8618행](../logs/react.jsonl#L8618) · [logs/react.jsonl 8622행](../logs/react.jsonl#L8622)
- `talk-198-buyer_condition_ignored` 손님이 적은 조건과 다른 결제서를 냈다: 소량 요구에 대용량. [logs/talk.jsonl 198행](../logs/talk.jsonl#L198)
- `talk-189-buyer_condition_ignored` 손님이 적은 조건과 다른 결제서를 냈다: A등급 요구에 C급, 450g 요구에 400g. [logs/talk.jsonl 189행](../logs/talk.jsonl#L189)

## 원인 미확인

답변 텍스트는 있으나 실패 또는 원인을 판정하기에 데이터가 부족한 구매 관련 대화.

총 37건, 저신뢰 37건. 첫 2026-11-26T19:42:59+09:00, 마지막 2026-11-28T16:02:49+09:00. 원장 폐기 원가 미산출, 확인된 잠금 하한 미산출 unit·시간.
동일 패턴 반복 간격 최소 5초, 중앙값 2326초, 최대 23520초.

- `talk-64-no_checkout_in_text` 구매 관련 답변에서 결제서 전달 문구가 확인되지 않았다. [logs/talk.jsonl 64행](../logs/talk.jsonl#L64) · [logs/react.jsonl 7109행](../logs/react.jsonl#L7109)
- `talk-46-no_checkout_in_text` 구매 관련 답변에서 결제서 전달 문구가 확인되지 않았다. [logs/talk.jsonl 46행](../logs/talk.jsonl#L46) · [logs/react.jsonl 6929행](../logs/react.jsonl#L6929)
- `talk-43-no_checkout_in_text` 구매 관련 답변에서 결제서 전달 문구가 확인되지 않았다. [logs/talk.jsonl 43행](../logs/talk.jsonl#L43) · [logs/react.jsonl 6906행](../logs/react.jsonl#L6906)
