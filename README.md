# 신고가·신저가 보드 (미국 · 일본)

매일 장 마감 후 GitHub Actions가 자동으로 집계해서 GitHub Pages에 올리는 정적 사이트입니다.

- **신고가 / 신저가**: 역대 기록과 52주 기록을 나눠서, 업종별(공통 대분류 › 세부)로 묶어 금일 · 5일 · 1달 등락률 표시
- **ETF**: `config/etfs.json`에 넣은 ETF의 금일 · 5일 · 1달 등락률
- 종목을 누르면 **최근 1년 캔들 차트**(거래량, 직전 52주 고·저가 선, 신고가 표시)
- **텍스트 복사** 버튼: 텔레그램 등에 붙여넣기 좋은 요약문 생성
- 주소로 바로 이동 가능: `.../#jp/newhigh/2026-11-12`, `.../#us/newlow/2026-11-13`, `.../#us/etf`

## 처음 설정 (10분)

1. GitHub에서 **새 저장소** 만들기 (예: `sector-board`, **Public**으로 — 무료 계정은 Public만 Pages 사용 가능)
2. 이 폴더의 파일을 전부 올리기
   - 웹: 저장소 첫 화면 → *uploading an existing file* → 압축 푼 파일·폴더를 끌어다 놓기 → Commit
     (`.github` 폴더가 숨김이라 안 보일 수 있습니다. 안 올라갔으면 *Add file → Create new file*에서
     이름을 `.github/workflows/update.yml`로 적고 내용을 붙여넣으세요.)
   - 또는 터미널: `git init && git add . && git commit -m init && git remote add origin <주소> && git push -u origin main`
3. **Settings → Actions → General → Workflow permissions** → *Read and write permissions* 선택 → Save
4. **Settings → Pages** → Source: *Deploy from a branch* → Branch: `main`, 폴더: `/docs` → Save
5. **Actions 탭 → Daily update → Run workflow** (market: `all`) 로 첫 데이터 생성 (20~40분 소요)
6. 사이트 주소: `https://<내 아이디>.github.io/<저장소 이름>/`

이후로는 자동으로 돌아갑니다.

| 시장 | 실행 시각 | 대상 |
|---|---|---|
| 일본 | 평일 16:10 (한국/일본 시간) | JPX 상장 내국주식 전체 (프라임·스탠다드·그로스, 약 3,800종목) |
| 미국 | 평일 22:00 UTC = 한국 다음 날 07:00 | S&P 500 + 400 + 600 (약 1,500종목) |

GitHub 예약 실행은 몇십 분 늦게 시작될 때가 있습니다. 휴장일에 돌면 직전 거래일 데이터를 다시 덮어쓸 뿐이라 문제없습니다.

## 판정 기준 (`config/settings.json`에서 변경)

- **52주 신고가**: 당일 장중 고가 > 직전 252거래일 최고가, 그리고 전일 대비 상승 마감, 양봉(종가 > 시가)
- **52주 신저가**: 당일 장중 저가 < 직전 252거래일 최저가, 그리고 하락 마감, 음봉
- **역대 신고가/신저가**: 위 조건을 만족한 종목 중 Yahoo Finance에 있는 전체 기간 기록도 넘어선 경우
  (상장이 오래된 종목은 Yahoo 데이터 시작 시점 이후 기준입니다 — 차트 창에 기준 연도 표시)
- 상장 240거래일 미만 종목은 제외 (신규 상장주가 매일 신고가로 잡히는 것 방지)
- 상승·양봉 조건을 빼고 싶으면 `rules`의 값을 `false`로
- **5일** = 5거래일 전 종가 대비, **1달** = 한 달 전 날짜의 종가 대비
- **[소형주]**: 일본은 TOPIX Small 및 TOPIX 미편입, 미국은 S&P 600

## 고치고 싶을 때

- **ETF 목록**: `config/etfs.json` (일본 종목은 `1306.T`처럼 `.T` 붙이기)
- **업종 한글명 / 대분류 묶음**: `scripts/industry_map.py`
- **화면**: `docs/index.html`, `docs/style.css`, `docs/app.js`
- 한국식 색상: 상승 빨강, 하락 파랑

## 폴더 구조

```
.github/workflows/update.yml   매일 실행 스케줄
scripts/update.py              시세 받기 → 판정 → JSON 저장
scripts/universe.py            종목 목록 (JPX / 위키백과)
scripts/industry_map.py        업종 매핑
config/                        설정, ETF 목록
cache/                         종목 목록·영문명 캐시 (자동 생성)
docs/                          웹사이트 (GitHub Pages 루트)
docs/data/<jp|us>/<날짜>.json  일별 결과
docs/data/charts/<jp|us>/      종목별 1년 차트 데이터 (마지막으로 걸린 날 기준)
```

## 알아둘 점

- 데이터는 Yahoo Finance 비공식 API(yfinance)라 가끔 일부 종목이 빠지거나 요청이 막힐 수 있습니다. 실패하면 Actions 탭에서 다시 실행하면 됩니다.
- 차트 파일은 종목별로 하나만 두고 덮어씁니다. 예전 날짜 종목을 눌러도 그 종목이 마지막으로 신고가/신저가에 걸린 날까지의 1년 차트가 나옵니다.
- 저장소에 60일간 아무 활동이 없으면 GitHub가 예약 실행을 끕니다. 매일 자동 커밋이 되므로 보통은 문제없지만, 꺼졌다면 Actions 탭에서 다시 켜면 됩니다.
- 내 PC에서 미리 보기: `pip install -r requirements.txt && python scripts/update.py --market jp && python -m http.server -d docs` → http://localhost:8000
