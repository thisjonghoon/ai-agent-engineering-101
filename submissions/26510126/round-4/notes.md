G2-01: 2세대 전환, 가게·지갑·재고 유지; archive/failure-lab 코드는 사용하지 않음.
G2-01: 핸들러를 직접 forge하고 카드·원장 가격표·매입을 순서대로 처리하며 held 단위는 판매 금지.
G2-01: 첫 결제서와 첫 정산 시각을 앱에 보고. 소유자 지시 수신 완료.
G2-01 상태: customer_handler v4 통과 및 활성화, prices.json에 원장 기반 SKU 가격 11개 생성, refresh_card로 공개 재고 갱신 완료. 핸들러는 가격 객체·held·3시간 예약을 처리하며 등급/인증서/잔여시간을 표시. 포럼 공지는 아직 미완료; 첫 결제·정산 보고 대기.
이번 실행 학습: /api/ledger 응답은 리스트 또는 records 구조이며 중첩 data를 순회해야 한다. 실제 정산에서 SKU별 가격 객체를 생성했고 핸들러가 이를 풀어 읽도록 v4로 수정했다. 현재 공개 재고 카드 갱신 완료. 남은 일: 포럼에 새 주소 공지, 고객 결제 발생 시 첫 결제서와 clearing 정산 시각을 앱에 보고. 대기 메시지 없음.
S-02 완료: customer_handler v6 테스트 통과. ledger_prices 실행으로 실제 prices.json에 SKU 가격 11개 복구. clean_fake_lock 실행으로 checkout_locks.json의 가짜 s1 예약 제거. supervisor 메시지 m8365c8은 대기 만료로 reply 실패.
S-03 완료: customer_handler v7 통과. SKU-only 카드 재고에서 사과 별칭→G36ca7485 매칭, 박수진 원문 테스트 결과 data.checkout_jwt 확인. 앱 보고 완료. 현재 열린 지시 없음.
O-01 진행: 23:30 KST까지 잘못된 사과 잠금 G36ca7485(이난임-60ba) 제거, customer_handler를 실제 logs/talk.jsonl의 서로 다른 품목 3개 원문으로 시험해 전 재고 품목을 처리하도록 같은 이름으로 교체. 완료 후 owner에게 forge·시험 로그를 보고.
O-01 완료: customer_handler v12 forge·시험 통과(실제 품목 문장 3종을 일반 카드 매칭으로 시험; 재고 품목은 서명 결제서·예약, 없는 생선은 무결제·무예약). clean_fake_lock 실행 결과 removed s1. 원 메시지 m5eb441 만료로 reply 불가.
S-06 완료: customer_handler v13 테스트 통과. 테스트는 test_card.json·test_checkout_locks.json만 사용하며 card.json을 쓰지 않음. remove_bad_lock 실행 결과 G36ca7485 잠금 없음, 기존 KEEP 예약만 보존.
O-02 진행(기한 23:59 KST): 카드의 20개 SKU 각각에 시장 카탈로그 품목명·등급·unit·원가 표를 만들고 customer_handler가 표 기반으로 검색하도록 교체. logs/talk.jsonl 21시 이후 손님 문장 전부를 원문 그대로 시험. 재고 품목은 (원가+210)/0.99 이상 결제서, 없는 품목은 결제서·잠금 없이 없다. 품목명 하드코딩 금지. 완료 보고 형식: O-02 done: 표 SKU 수·시험 문장 수·통과 결과.
O-02 상태: build_catalog로 /api/catalog 5,629개 수집 완료. 아직 내 카드 20개 SKU만 추린 표와 logs/talk.jsonl 21시 이후 원문 전체 시험은 미완료. 소유자 메시지 mafea83는 만료되어 reply 불가.
O-02 재전송 수신: 23:59 KST까지 카드 20개 SKU 각각에 시장 catalog 품목명·등급·unit·원가 표를 만들고, customer_handler가 표 기반 검색을 사용하도록 교체한다. logs/talk.jsonl 21시 이후 손님 원문 전체를 시험한다. 재고 품목은 (원가+210)/0.99 이상 checkout, 없는 품목은 결제서·잠금 없이 없다. 완료 보고: O-02 done: 표 SKU 수·시험 문장 수·통과 결과.
