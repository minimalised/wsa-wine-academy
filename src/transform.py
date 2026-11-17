"""매체별 원본 탭 행을 리포트가 읽는 통합 탭 형식으로 바꾼다."""
import datetime as dt

DEVICE = {"컴퓨터": "PC", "휴대전화": "모바일"}


def _month_start(d):
    return d.replace(day=1)


def _naver_month(s):
    """'2026.07.' → date(2026, 7, 1)"""
    y, m = s.rstrip(".").split(".")
    return dt.date(int(y), int(m), 1)


def _google_metrics(row):
    # 노출수, 클릭수, 통화 코드, 비용, 전환, 전환 가치 → 통화 코드를 뺀다
    imp, clk, _currency, cost, conv, value = row
    return [imp, clk, cost, conv, value]


def combined_device(google_rows, naver_rows):
    """통합_일자별_기기: 일자, 매체, 캠페인, 기기, 노출수, 클릭수, 비용, 전환수, 전환매출, 월"""
    out = []
    for day, camp, device, *m in google_rows:
        out.append([day, "구글", camp, DEVICE.get(device, device), *_google_metrics(m), _month_start(day)])
    for day, camp, device, *m in naver_rows:
        out.append([day, "네이버", camp, device, *m, _month_start(day)])
    return out


def combined_keyword(google_rows, naver_rows):
    """통합_키워드: 월, 매체, 캠페인, 키워드, 노출수, 클릭수, 비용, 전환수, 전환매출"""
    out = []
    for month, camp, kw, *m in google_rows:
        out.append([month, "구글", camp, kw, *_google_metrics(m)])
    for month, camp, kw, *m in naver_rows:
        out.append([_naver_month(month), "네이버", camp, kw, *m])
    return out


def combined_demographic(google_age, google_gender, naver_age=(), naver_gender=()):
    """통합_인구통계: 월, 매체, 캠페인, 구분유형, 구분값, 노출수, 클릭수, 비용, 전환수, 전환매출"""
    out = []
    for kind, rows in (("연령", google_age), ("성별", google_gender)):
        for month, camp, value, *m in rows:
            out.append([month, "구글", camp, kind, value, *_google_metrics(m)])
    for kind, rows in (("연령", naver_age), ("성별", naver_gender)):
        for month, camp, value, *m in rows:
            out.append([month, "네이버", camp, kind, value, *m])
    return out
