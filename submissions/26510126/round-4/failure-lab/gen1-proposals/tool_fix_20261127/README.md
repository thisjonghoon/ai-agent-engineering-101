# 도구 고침 제안 (11/27 00:4x, 주인 jonghoon 요청으로 claude가 씀)

이 폴더는 제안이다. `tools/`의 도구는 그대로다. 가게가 `inspect_local`로 읽고, 맞다고 보면 `forge_tool`로 직접 만든다.
kit는 forge 기록(forge.json)과 파일이 맞는 도구만 다시 켤 때 불러오므로, 바깥에서 `tools/`를 고치지 않았다.

## 왜

- 마지막 결제서는 11/26 21:40에 나갔다. 지금 재고에 남은 '발급 이력' unit은 모두 3시간이 지났다.
- make_checkout v5는 이런 unit도 포럼 철회 글 + 30분 + 원장 전체 + 체인 1만 블록씩 조회를 마쳐야 다시 낸다(logic.py 55~98줄).
  11/26 12:31 뒤 만료된 unit 15개 중 13개(원가 72,531)가 이 잠금에 걸린 채 상했다. 같은 기간 판매는 39,724.
- 우리 판매 28건은 모두 결제서를 낸 뒤 2분 안에 정산됐다. 3시간 넘게 늦은 입금은 한 번도 없었다.
  체인 조회 200회(24시간)에서 찾은 입금도 0건이다.
- a2a_inquiry v14는 손님 문의 21건(talk.jsonl) 중 0건을 직접 응대했다. '소비기한'이나 '등급'이라는 말만 있어도 넘겼다(36줄·27줄).

## 무엇이 바뀌나

**make_checkout v6** (goal: 원장 기준, 3시간, 스스로 무효화)
- 그 unit의 마지막 결제서(react.jsonl + auto_checkout.jsonl)가 3시간이 안 됐으면 거절: `live checkout`, `live_until_kst`.
- 3시간이 지났고, 공개 원장에 그 unit의 settle이 없고, 재고에 그대로 있으면: 무효 기록을 `checkout_withdrawals.jsonl`에 남기고 새 결제서를 낸다. 결과에 `voided`.
- 포럼 글, 30분 대기, 체인 조회, `withdrawal_post`는 없다. 원장은 첫 결제서 시각부터만 읽는다(약 20번 요청).
- 테스트할 때는 잠금을 메모리에 둔다. 실제 checkout_locks.json에 시험 unit이 쌓이지 않는다.

**a2a_inquiry v15** (판매 직원)
- '소비기한 알려주세요', '현재 등급', '기한 넉넉한' 같은 질문은 직접 답한다. 기한이 가장 긴 unit부터, 등급과 남은 시간을 밝힌다.
- 여전히 넘기는 것: '내일까지', '짧은', '임박', 'N일'처럼 숫자로 못 읽는 기한, '1+등급'·'특등급', '피하고', 여러 품목.
- '물'이 '나물'에 걸려 생수를 내던 별칭을 고쳤다. '유정란'·'특란'은 계란으로 읽는다.
- '450g'을 물었는데 400g만 있으면 다른 상품을 내지 않는다. 무게만 다르면 직접 응대로 넘긴다.
- 원장을 한 번 읽어 make_checkout에 넘긴다(`_ledger`).
- 실제 문의 21건에 넣어 보면 8건을 직접 응대한다(v14는 0건). 8건 모두 품목을 바르게 읽는다.

**inventory_audit v2**
- '발급 이력'을 `live_checkout`(3시간 안), `voidable`(3시간 지남, 다시 팔 수 있음), `never_issued`로 나눈다. `sellable_now`를 준다.

## 만드는 순서와 permission

1. make_checkout (a2a_inquiry가 이 파일을 불러 쓰므로 먼저)
   `{"network": ["market.ourolabs.ai"], "write": ["checkout_locks.json", "checkout_withdrawals.jsonl"], "identity": ["shop"], "wallet": ["sign_jwt"], "timeout": 180}`
2. a2a_inquiry
   `{"network": ["market.ourolabs.ai"], "write": ["checkout_locks.json", "checkout_withdrawals.jsonl", "auto_checkout.jsonl"], "identity": ["shop"], "wallet": ["sign_jwt"], "timeout": 180, "handles": ["a2a"]}`
3. inventory_audit
   `{"network": ["market.ourolabs.ai"], "identity": ["shop"], "timeout": 60}`

파일이 6,000자를 넘으면 `inspect_local`의 start·end로 나눠 읽는다(줄 번호 기준).

## 되돌리기

forge는 앞 버전을 `tools/.deprecated/<이름>@<버전>`에 남긴다. 되돌릴 때는 그 파일로 다시 forge한다.
