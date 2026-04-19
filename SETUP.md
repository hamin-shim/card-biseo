# 카드 비서 PWA — 세팅 가이드

다른 기기나 다른 Claude 계정에서 이 프로젝트를 이어서 작업할 때 참고하는 문서.

---

## 프로젝트 개요

- **앱 주소**: https://hamin-shim.github.io/card-biseo/
- **GitHub 레포**: https://github.com/hamin-shim/card-biseo
- **목적**: 카드 결제 직전 최적 카드 추천 + 전월실적 현황 트래킹 PWA
- **구조**: 단일 index.html + localStorage + data.json(GitHub Pages) + Telegram 봇 연동

---

## 환경 복원 순서

### 1. 코드 클론

```bash
git clone https://github.com/hamin-shim/card-biseo.git
cd card-biseo
```

### 2. .env 파일 생성 (GitHub에 없음 — 직접 입력)

```bash
echo "BOT_TOKEN=8572009690:AAHiLewVB1fG7NQabNhpSjWmYYUsIbG9pfs" > .env
```

> ⚠️ 토큰 분실 시: 텔레그램 @BotFather → `/revoke` → 재발급

### 3. GitHub CLI 로그인

```bash
gh auth login
```

GitHub 계정: **hamin-shim**

### 4. Notion MCP 재연결

Claude Code 설정에서 Notion MCP 재인증 (claude.ai 계정 연동)

---

## 파일 구조

```
credit_card_usage/
├── index.html          # 앱 전체 (카드 데이터 + UI + 로직 모두 포함)
├── manifest.json       # PWA 설치용
├── sw.js               # 오프라인 캐시용 서비스워커
├── data.json           # Telegram 파싱 결과 (Claude가 push하는 파일)
├── fetch_telegram.py   # 텔레그램 메시지 수신 스크립트
├── .env                # BOT_TOKEN (gitignore — 직접 생성 필요)
├── .gitignore
├── idea.md             # 초기 기획 문서
└── SETUP.md            # 이 파일
```

---

## 카드 데이터 수정 위치

`index.html` 상단 `const CARDS = [...]` 배열.
카드별 ID, 혜택, 실적조건이 모두 여기에 있음.

| 카드명 | id | 실적조건 |
|---|---|---|
| 신한 Deep Dream Platinum+ | `shinhan-deepdream` | 50만원 |
| 롯데백화점 롯데카드 | `lotte-dept` | 롯데백화점 6개월 누적 30만원 |
| 삼성 신세계이마트 SFC7 | `samsung-sfc7` | 30만원 |
| KB 톡톡 with | `kb-toktok` | 40만원 |
| MG새마을금고 더나은체크 | `mg-better` | 30만원 |

> ⚠️ 신한카드, MG카드는 SMS 알림 미신청 상태 → 문자 등록 후 패턴 추가 필요

---

## Telegram 연동 워크플로

### 일상 사용
1. 카드 결제 SMS 수신
2. 텔레그램 봇으로 포워딩 (봇 username은 BotFather에서 확인)
3. 주 1회 Claude에게: **"텔레그램 결제 내역 읽어서 카드 앱 업데이트해줘"**

### Claude가 하는 작업
```bash
python3 fetch_telegram.py          # 텔레그램 메시지 수신 → telegram_raw.json
# Claude가 내용 파싱 → data.json 업데이트
git add data.json && git commit -m "결제 파싱: ..." && git push
```

### 카드사별 SMS 문자 패턴

| 카드 | 문자 패턴 | 예시 |
|---|---|---|
| 삼성카드 | `삼성XXXX승인 성*명 금액원 일시불 MM/DD HH:MM 가맹점 누적XXX원` | `삼성7056승인 심*민 7,490원 일시불 04/18 14:32 롯데백화점잠실점 누적392,495원` |
| 롯데카드 | `SR 금액원 승인 성*명 가맹점(카드번호) 일시불, MM/DD HH:MM` | `SR 94,200원 승인 심*민 롯데백화점(3*4*) 일시불, 04/15 20:02` |
| KB국민카드 | `KB국민카드XXXX승인 성*명님 금액원 일시불 MM/DD HH:MM 가맹점 누적XXX원` | `KB국민카드1000승인 심*민님 143,500원 일시불 04/16 10:49 (주)비바리퍼블리카 누적209,910원` |
| 신한카드 | 미확인 (SMS 알림 미신청) | — |
| MG체크카드 | 미확인 (SMS 알림 미신청) | — |

---

## 매월 루틴

| 시점 | 할 일 |
|---|---|
| 매월 1일 | 앱 ⚙️ → "이번달 초기화" → 지난달 실적 확정 |
| 수시 | 결제 SMS → 텔레그램 봇 포워딩 |
| 주 1회 | Claude에게 업데이트 요청 |
| 실적 변동 시 | ⚙️ → 전월 실적 수동 입력 |

---

## 참고 링크

- 앱: https://hamin-shim.github.io/card-biseo/
- GitHub: https://github.com/hamin-shim/card-biseo
- Notion 카드 혜택 정리: https://www.notion.so/347d562f3b5981a58dc2fd8154a50265
- MG 더나은체크 혜택: https://mgcheck.kfcc.co.kr/pers/appl/persTheNaeunGuid.do
- 신한 Deep Dream Platinum+: https://brunch.co.kr/@valuechampion/160
