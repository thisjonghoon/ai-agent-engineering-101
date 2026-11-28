# 실패 유형

한 사건에는 주 유형 하나를 붙였다. 호출·대화·버전 회귀·원장 만료는 서로 다른 관측 단위다. 같은 판매 기회를 여러 행이 설명할 수 있다. 유형은 관측 패턴을 설명하는 원인 후보이며, 특히 등급 불일치나 만료만으로 에이전트 책임을 확정할 수 없다.

## 시간 예산과 응답 경로

busy 문구 또는 대기가 끝났다는 reply 오류. defer는 동일 문의 본문과 응답 직전 81초 안의 도구 관찰이 같이 있어야 붙인다.

총 88건, 저신뢰 0건. 첫 2026-11-24T20:38:45+09:00, 마지막 2026-11-27T23:34:28+09:00. 원장 폐기 원가 미산출, 확인된 잠금 하한 미산출 unit·시간.
동일 패턴 반복 간격 최소 9초, 중앙값 1313초, 최대 12470초.

- `talk-123-defer_timeout` 응답 시한을 넘겨 손님에게 busy 문구가 갔다. [logs/talk.jsonl 123행](../logs/talk.jsonl#L123) · [logs/react.jsonl 7864행](../logs/react.jsonl#L7864)
- `react-7866-reply_failed` reply가 대기 중인 메시지에 연결되지 않았다. [logs/react.jsonl 7866행](../logs/react.jsonl#L7866)
- `talk-106-busy_reply` 응답 시한을 넘겨 손님에게 busy 문구가 갔다. [logs/talk.jsonl 106행](../logs/talk.jsonl#L106)

## 메시지 식별자와 호출 계약

reply 대상 이름이나 ID가 현재 대기 이벤트와 맞지 않아 오류가 난 호출.

총 104건, 저신뢰 0건. 첫 2026-11-24T19:07:15+09:00, 마지막 2026-11-27T21:33:41+09:00. 원장 폐기 원가 미산출, 확인된 잠금 하한 미산출 unit·시간.
동일 패턴 반복 간격 최소 21초, 중앙값 1983초, 최대 131791초.

- `react-7727-reply_failed` reply가 대기 중인 메시지에 연결되지 않았다. [logs/react.jsonl 7727행](../logs/react.jsonl#L7727)
- `react-7655-reply_customer_name` 메시지 ID 대신 손님 이름으로 답하려다 실패했다. [logs/react.jsonl 7655행](../logs/react.jsonl#L7655)
- `react-7662-reply_failed` reply가 대기 중인 메시지에 연결되지 않았다. [logs/react.jsonl 7662행](../logs/react.jsonl#L7662)

## 도구 변경과 회귀 검증

코드 변경으로 기존 경로가 좁아졌거나 체크아웃 호출에서 처리 오류가 난 사례. 매입의 비시간창 오류도 포함한다.

총 47건, 저신뢰 9건. 첫 2026-11-24T21:24:48+09:00, 마지막 2026-11-27T22:27:20+09:00. 원장 폐기 원가 미산출, 확인된 잠금 하한 미산출 unit·시간.
동일 패턴 반복 간격 최소 7초, 중앙값 1825초, 최대 132283초.

- `react-7730-handler_regression` v24에서 이전 판매 경로가 좁아졌다. 인증서 공란 차단을 다시 도입했다. [logs/react.jsonl 7730행](../logs/react.jsonl#L7730) · [logs/forge.jsonl 91행](../logs/forge.jsonl#L91) · [logs/ledger.jsonl 156행](../logs/ledger.jsonl#L156) · [logs/react.jsonl 7767행](../logs/react.jsonl#L7767) · [logs/react.jsonl 7785행](../logs/react.jsonl#L7785)
- `react-6563-rules_test_data_residue` 규칙 복원 뒤 읽기 결과에 시험 문장이 남아 후속 도구로 제거했다. [logs/react.jsonl 6563행](../logs/react.jsonl#L6563) · [.kit/chat.jsonl 128행](../.kit/chat.jsonl#L128) · [logs/react.jsonl 6560행](../logs/react.jsonl#L6560) · [logs/react.jsonl 6564행](../logs/react.jsonl#L6564) · [logs/react.jsonl 6565행](../logs/react.jsonl#L6565)
- `react-7790-make_checkout_failed` make_checkout 호출이 실패하거나 보호 조건으로 중단됐다. [logs/react.jsonl 7790행](../logs/react.jsonl#L7790)

## 실행 간 주인 지시 보존

주인 지시 뒤 같은 규칙과 어긋나는 코드 변경 또는 외부 행동을 확인한 사례.

총 2건, 저신뢰 0건. 첫 2026-11-27T21:35:14+09:00, 마지막 2026-11-27T22:25:05+09:00. 원장 폐기 원가 미산출, 확인된 잠금 하한 미산출 unit·시간.
동일 패턴 반복 간격 최소 2991초, 중앙값 2991초, 최대 2991초.

- `react-7785-owner_rule_reversal` 공란 인증서를 허용하라는 지시와 v25 수정 뒤 판매 불가 공지를 게시했다. [logs/react.jsonl 7785행](../logs/react.jsonl#L7785) · [.kit/chat.jsonl 239행](../.kit/chat.jsonl#L239) · [logs/react.jsonl 7767행](../logs/react.jsonl#L7767) · [logs/react.jsonl 7784행](../logs/react.jsonl#L7784) · [logs/react.jsonl 7787행](../logs/react.jsonl#L7787)
- `react-7730-owner_rule_reversal` 공란 인증서를 허용하라는 앞선 주인 지시가 있었으나 다시 차단했다. [logs/react.jsonl 7730행](../logs/react.jsonl#L7730) · [.kit/chat.jsonl 206행](../.kit/chat.jsonl#L206) · [logs/react.jsonl 7383행](../logs/react.jsonl#L7383)

## 판매 규칙과 집행 경로

대기 손님 없는 발급, 손님 조건 배제 누락, 기존 결제서 관련 잠금·중복 방어가 관찰된 사례.

총 37건, 저신뢰 8건. 첫 2026-11-25T21:33:35+09:00, 마지막 2026-11-27T23:29:55+09:00. 원장 폐기 원가 미산출, 확인된 잠금 하한 1.364 unit·시간.
동일 패턴 반복 간격 최소 3초, 중앙값 58초, 최대 78791초.

- `react-7857-checkout_lost_to_timeout` 반찬 문의에 결제서를 발급했으나 해당 대화에 기록된 답은 busy였다. [logs/react.jsonl 7857행](../logs/react.jsonl#L7857) · [logs/react.jsonl 7854행](../logs/react.jsonl#L7854) · [logs/react.jsonl 7856행](../logs/react.jsonl#L7856) · [logs/react.jsonl 7858행](../logs/react.jsonl#L7858) · [logs/talk.jsonl 121행](../logs/talk.jsonl#L121)
- `react-7559-checkout_without_customer` 손님 없이 고등어 결제서를 냈고 81분 뒤 같은 발급 시각을 가진 활성 결제서가 손님 문의에서 재발급을 막았다. [logs/react.jsonl 7559행](../logs/react.jsonl#L7559) · [logs/react.jsonl 7652행](../logs/react.jsonl#L7652) · [logs/talk.jsonl 109행](../logs/talk.jsonl#L109)
- `talk-119-buyer_condition_ignored` C등급 제외 조건에 C등급 결제서를 안내했다. [logs/talk.jsonl 119행](../logs/talk.jsonl#L119)

## 단위와 데이터 의미

단위, 등급·인증서, 원장 집계 또는 견적의 의미 혼선. 등급 불일치 보호 동작도 포함한다.

총 50건, 저신뢰 1건. 첫 2026-11-25T18:24:22+09:00, 마지막 2026-11-28T08:42:13+09:00. 원장 폐기 원가 미산출, 확인된 잠금 하한 미산출 unit·시간.
동일 패턴 반복 간격 최소 12초, 중앙값 2268초, 최대 115712초.

- `react-7783-false_zero_settlements` 도구가 보고한 24시간 판매 0을 채택했지만 같은 날 정산이 로컬 원장에 있다. [logs/react.jsonl 7783행](../logs/react.jsonl#L7783) · [logs/react.jsonl 7782행](../logs/react.jsonl#L7782) · [logs/ledger.jsonl 156행](../logs/ledger.jsonl#L156) · [tools/shop_health/logic.py 26행](../tools/shop_health/logic.py#L26)
- `react-7321-currency_confusion` 크레딧 잔액의 천분의 일 표시를 다시 크레딧으로 해석했다. [logs/react.jsonl 7321행](../logs/react.jsonl#L7321) · [tools/chain_balance/logic.py 14행](../tools/chain_balance/logic.py#L14)
- `react-8281-buy_stock_failed` buy_stock 호출이 실패하거나 보호 조건으로 중단됐다. [logs/react.jsonl 8281행](../logs/react.jsonl#L8281)

## 시장 시간창과 재고 수명

원장 만료, 매입 HTTP 실패, 열리기 직전 확인했으나 놓친 재입고 창.

총 178건, 저신뢰 1건. 첫 2026-11-24T19:23:47+09:00, 마지막 2026-11-28T08:46:53+09:00. 원장 폐기 원가 336675, 확인된 잠금 하한 미산출 unit·시간.
동일 패턴 반복 간격 최소 3초, 중앙값 1010초, 최대 77471초.

- `ledger-208-stock_expired` 원장에 재고 1개 만료가 기록됐다. [logs/ledger.jsonl 208행](../logs/ledger.jsonl#L208) · [logs/ledger.jsonl](../logs/ledger.jsonl)
- `react-8292-buy_stock_failed` buy_stock 호출이 실패하거나 보호 조건으로 중단됐다. [logs/react.jsonl 8292행](../logs/react.jsonl#L8292)
- `react-7877-restock_window_missed` 90초 안에 열릴 창을 확인했으나 같은 SKU 매입은 창 안에 없고 닫힌 뒤 재시도했다. [logs/react.jsonl 7877행](../logs/react.jsonl#L7877) · [logs/react.jsonl 7887행](../logs/react.jsonl#L7887)

## 원인 미확인

답변 텍스트는 있으나 실패 또는 원인을 판정하기에 데이터가 부족한 구매 관련 대화.

총 36건, 저신뢰 36건. 첫 2026-11-26T19:42:59+09:00, 마지막 2026-11-28T07:39:46+09:00. 원장 폐기 원가 미산출, 확인된 잠금 하한 미산출 unit·시간.
동일 패턴 반복 간격 최소 4초, 중앙값 1820초, 최대 21108초.

- `talk-64-no_checkout_in_text` 구매 관련 답변에서 결제서 전달 문구가 확인되지 않았다. [logs/talk.jsonl 64행](../logs/talk.jsonl#L64) · [logs/react.jsonl 7109행](../logs/react.jsonl#L7109)
- `talk-46-no_checkout_in_text` 구매 관련 답변에서 결제서 전달 문구가 확인되지 않았다. [logs/talk.jsonl 46행](../logs/talk.jsonl#L46) · [logs/react.jsonl 6929행](../logs/react.jsonl#L6929)
- `talk-43-no_checkout_in_text` 구매 관련 답변에서 결제서 전달 문구가 확인되지 않았다. [logs/talk.jsonl 43행](../logs/talk.jsonl#L43) · [logs/react.jsonl 6906행](../logs/react.jsonl#L6906)
