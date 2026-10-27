"""Google Ads·네이버 검색광고 데이터를 구글 시트에 적재한다.

기본 실행(매일): 어제까지 최근 7일은 일자 탭, 이번 달(1~7일에는 지난달 포함)은 월 탭을 다시 쓴다.
수동 실행: --start/--end로 기간을 지정하면 그 기간의 일자와 그 기간이 걸친 월 전체를 다시 쓴다.
"""
import argparse
import calendar
import datetime as dt
import os
from zoneinfo import ZoneInfo

from . import transform
from .sheets import TABS, open_sheet, replace_rows

KST = ZoneInfo("Asia/Seoul")
DAILY_LOOKBACK = 7


def windows(start=None, end=None):
    """(일자 탭 기간, 월 탭 조회 기간)을 돌려준다. 월 탭 기간은 월 1일부터 시작한다."""
    yesterday = dt.datetime.now(KST).date() - dt.timedelta(days=1)
    if start is None:
        end = yesterday
        start = end - dt.timedelta(days=DAILY_LOOKBACK - 1)
        month_start = end.replace(day=1)
        if end.day <= DAILY_LOOKBACK:
            month_start = (month_start - dt.timedelta(days=1)).replace(day=1)
    else:
        end = min(end or yesterday, yesterday)
        month_start = start.replace(day=1)
    month_end = min(end.replace(day=calendar.monthrange(end.year, end.month)[1]), yesterday)
    return (start, end), (month_start, month_end)


REQUIRED = {
    "google": ["GOOGLE_ADS_DEVELOPER_TOKEN", "GOOGLE_ADS_CLIENT_ID", "GOOGLE_ADS_CLIENT_SECRET",
               "GOOGLE_ADS_REFRESH_TOKEN", "GOOGLE_ADS_CUSTOMER_ID"],
    "naver": ["NAVER_API_KEY", "NAVER_SECRET_KEY", "NAVER_CUSTOMER_ID"],
    "sheet": ["GCP_SA_KEY", "SHEET_ID"],
}


def check_env(sources):
    """비어 있는 Secret 이름을 한 번에 알려준다. 값은 출력하지 않는다."""
    missing = [name for key in ("sheet", *sorted(sources)) for name in REQUIRED[key] if not os.environ.get(name)]
    if missing:
        raise SystemExit("등록되지 않았거나 비어 있는 Secret: " + ", ".join(missing))


def run(start, end, dry_run, sources):
    check_env(sources)
    (d_start, d_end), (m_start, m_end) = windows(start, end)
    print(f"일자 탭: {d_start} ~ {d_end} / 월 탭: {m_start} ~ {m_end}")
    sheet = open_sheet()

    def write(tab, rows, s, e, medias=None):
        replace_rows(sheet, TABS[tab], rows, s, e, medias=medias, dry_run=dry_run)

    g_device = g_keyword = g_age = g_gender = []
    n_device = n_keyword = []

    if "google" in sources:
        from .google_ads import GoogleAds

        g = GoogleAds()
        g_campaign = g.campaign_monthly(m_start, m_end)
        g_keyword = g.keyword_monthly(m_start, m_end)
        g_device = g.device_daily(d_start, d_end)
        g_age = g.age_monthly(m_start, m_end)
        g_gender = g.gender_monthly(m_start, m_end)
        write("구글_일반", g_campaign, m_start, m_end)
        write("구글_일반_키워드", g_keyword, m_start, m_end)
        write("구글_일자별_기기", g_device, d_start, d_end)
        write("구글_연령", g_age, m_start, m_end)
        write("구글_성별", g_gender, m_start, m_end)

    if "naver" in sources:
        from .naver_ads import NaverAds, days_between

        n = NaverAds()
        facts = n.daily_facts(days_between(m_start, m_end))
        daily_facts = {k: v for k, v in facts.items() if d_start <= k[0] <= d_end}
        n_keyword = n.keyword_monthly(facts)
        n_device = n.device_daily(daily_facts)
        write("네이버_일반", n_keyword, m_start, m_end)
        write("네이버_일자별_기기", n_device, d_start, d_end)

    medias = {"google": "구글", "naver": "네이버"}
    fetched = {medias[s] for s in sources}
    write("통합_일자별_기기", transform.combined_device(g_device, n_device), d_start, d_end, fetched)
    write("통합_키워드", transform.combined_keyword(g_keyword, n_keyword), m_start, m_end, fetched)
    # 네이버 연령·성별은 API 지원 여부를 확인하기 전까지 기존 행을 그대로 둔다.
    if "google" in sources:
        write("통합_인구통계", transform.combined_demographic(g_age, g_gender), m_start, m_end, {"구글"})


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--start", type=dt.date.fromisoformat, help="YYYY-MM-DD")
    p.add_argument("--end", type=dt.date.fromisoformat, help="YYYY-MM-DD (기본: 어제)")
    p.add_argument("--dry-run", action="store_true", help="시트를 읽기만 하고 교체될 행 수를 출력")
    p.add_argument("--sources", default="google,naver", help="google,naver 중 쉼표로 구분")
    args = p.parse_args()
    if args.end and not args.start:
        p.error("--end는 --start와 함께 써야 합니다")
    run(args.start, args.end, args.dry_run, set(args.sources.split(",")))


if __name__ == "__main__":
    main()
