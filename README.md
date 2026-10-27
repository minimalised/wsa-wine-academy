# WSA 와인아카데미 광고 리포트 자동화

Google Ads와 네이버 검색광고 데이터를 매일 구글 시트에 적재합니다. Looker Studio 리포트는 이 시트의 통합 탭을 읽습니다.

## 동작

GitHub Actions(`.github/workflows/daily-ads-report.yml`)가 매일 07:00 KST에 `python -m src.main`을 실행합니다.

- 일자 탭(`*_일자별_기기`): 어제까지 최근 7일을 다시 씁니다. 늦게 잡히는 전환을 반영하기 위해서입니다.
- 월 탭: 이번 달을 다시 씁니다. 매월 1~7일에는 지난달도 다시 써서 확정치로 맞춥니다.
- 기간 밖의 기존 행은 건드리지 않습니다. 같은 기간을 여러 번 돌려도 중복되지 않습니다.

| 탭 | 단위 | 출처 |
| --- | --- | --- |
| 구글_일반 | 월 × 캠페인 | `campaign` |
| 구글_일반_키워드 | 월 × 캠페인 × 키워드 | `keyword_view` |
| 구글_일자별_기기 | 일 × 캠페인 × 기기 | `campaign` + `segments.device` |
| 구글_연령 / 구글_성별 | 월 × 캠페인 × 연령(성별) | `age_range_view` / `gender_view` |
| 네이버_일반 | 월 × 캠페인 × 키워드 | StatReport `AD_DETAIL` + `AD_CONVERSION_DETAIL`(구매완료) |
| 네이버_일자별_기기 | 일 × 캠페인 × PC/모바일 | 위와 같음 |
| 통합_일자별_기기, 통합_키워드, 통합_인구통계 | 두 매체 합본 | 위 탭을 `src/transform.py`에서 가공 |

Google Ads API는 연령×성별 교차 데이터를 주지 않아서 기존 `구글_연령성별` 대신 `구글_연령`, `구글_성별` 탭에 씁니다. 네이버 연령·성별(`네이버_연령`, `네이버_성별`)은 아직 자동화하지 않았고, `통합_인구통계`의 네이버 행은 그대로 둡니다.

## 설정

1. Google Cloud에서 서비스 계정을 만들고 Google Sheets API를 켠 뒤 JSON 키를 받습니다. 시트를 서비스 계정 이메일에 **편집자**로 공유합니다.
2. 저장소 Settings → Secrets and variables → Actions에 아래 값을 등록합니다.

| Secret | 내용 |
| --- | --- |
| `GOOGLE_ADS_DEVELOPER_TOKEN` `GOOGLE_ADS_CLIENT_ID` `GOOGLE_ADS_CLIENT_SECRET` `GOOGLE_ADS_REFRESH_TOKEN` | Google Ads API 인증 |
| `GOOGLE_ADS_CUSTOMER_ID` | 광고 계정 ID (하이픈 있어도 됨) |
| `GOOGLE_ADS_LOGIN_CUSTOMER_ID` | MCC를 통해 접근하면 관리자 계정 ID, 아니면 비워 둠 |
| `NAVER_API_KEY` `NAVER_SECRET_KEY` `NAVER_CUSTOMER_ID` | 네이버 검색광고 API |
| `GCP_SA_KEY` | 서비스 계정 JSON 전체 |
| `SHEET_ID` | 시트 URL의 `/d/` 뒤 ID |

3. 수동 실행으로 확인을 마친 뒤 Settings → Secrets and variables → Actions → Variables에 `ADS_REPORT_ENABLED` = `true`를 추가하면 매일 예약 실행이 시작됩니다.

## 수동 실행

Actions → Daily ads report → Run workflow에서 기간과 매체를 넣고 실행합니다. `dry_run`이 켜져 있으면(기본값) 시트는 읽기만 하고 탭별로 교체될 행 수만 출력합니다.

로컬에서는 같은 환경변수를 설정하고 실행합니다.

```
pip install -r requirements.txt
python -m src.main --start 2026-09-01 --dry-run
```
