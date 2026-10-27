"""구글 시트 탭에서 갱신 기간에 해당하는 행만 새 행으로 교체한다."""
import datetime as dt
import json
import os
import re

import gspread
from google.oauth2.service_account import Credentials

EPOCH = dt.date(1899, 12, 30)
SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]

GOOGLE_METRICS = ["노출수", "클릭수", "통화 코드", "비용", "전환", "전환 가치"]
NAVER_METRICS = ["노출수", "클릭수", "총비용", "구매완료 전환수", "구매완료 전환매출액(원)"]
COMBINED_METRICS = ["노출수", "클릭수", "비용", "전환수", "전환매출"]


class Tab:
    def __init__(self, name, header, period, date_formats, media_col=None):
        self.name = name
        self.header = header
        self.period = period  # "day" | "month": 첫 열의 단위
        self.date_formats = date_formats  # {열 번호: 표시 형식}, 기존 시트와 같은 형식
        self.media_col = media_col  # 통합 탭에서 매체 열. 이번에 받은 매체의 행만 교체한다


TABS = {
    t.name: t
    for t in [
        Tab("구글_일반", ["월", "캠페인", *GOOGLE_METRICS], "month", {0: "yyyy년 m월"}),
        Tab("구글_일반_키워드", ["월", "캠페인", "검색 키워드", *GOOGLE_METRICS], "month", {0: "yyyy년 m월"}),
        Tab("구글_일자별_기기", ["일", "캠페인", "기기", *GOOGLE_METRICS], "day", {0: "yyyy-mm-dd"}),
        Tab("구글_연령", ["월", "캠페인", "연령", *GOOGLE_METRICS], "month", {0: "yyyy년 m월"}),
        Tab("구글_성별", ["월", "캠페인", "성별", *GOOGLE_METRICS], "month", {0: "yyyy년 m월"}),
        Tab("네이버_일반", ["월별", "캠페인", "키워드", *NAVER_METRICS], "month", {}),
        Tab("네이버_일자별_기기", ["일별", "캠페인", "PC/모바일 매체", *NAVER_METRICS], "day", {0: "yyyy-mm-dd"}),
        Tab("통합_일자별_기기", ["일자", "매체", "캠페인", "기기", *COMBINED_METRICS, "월"], "day",
            {0: "yyyy-mm-dd", 9: "yyyy-mm-dd"}, media_col=1),
        Tab("통합_키워드", ["월", "매체", "캠페인", "키워드", *COMBINED_METRICS], "month", {0: "yyyy-mm"}, media_col=1),
        Tab("통합_인구통계", ["월", "매체", "캠페인", "구분유형", "구분값", *COMBINED_METRICS], "month",
            {0: "yyyy-mm"}, media_col=1),
    ]
}


def open_sheet():
    info = json.loads(os.environ["GCP_SA_KEY"])
    creds = Credentials.from_service_account_info(info, scopes=SCOPES)
    return gspread.authorize(creds).open_by_key(os.environ["SHEET_ID"])


def to_date(cell):
    """시트 셀 값(일련번호, '2026.07.', '2026-07-01')을 date로. 날짜가 아니면 None."""
    if isinstance(cell, (int, float)) and not isinstance(cell, bool):
        return EPOCH + dt.timedelta(days=int(cell))
    if isinstance(cell, str):
        m = re.fullmatch(r"(\d{4})[.-](\d{1,2})[.-]?(\d{1,2})?\.?", cell.strip())
        if m:
            return dt.date(int(m[1]), int(m[2]), int(m[3] or 1))
    return None


def to_cell(value):
    if isinstance(value, dt.date):
        return (value - EPOCH).days
    return value


def _col_letter(i):
    s = ""
    i += 1
    while i:
        i, r = divmod(i - 1, 26)
        s = chr(65 + r) + s
    return s


def replace_rows(sheet, tab, rows, start, end, medias=None, dry_run=False):
    """tab에서 [start, end] 기간(월 탭은 해당 월들)이면서 medias에 속한 행을 지우고 rows로 바꾼다."""
    if tab.period == "month":
        start, end = start.replace(day=1), end.replace(day=1)

    def in_window(row):
        d = to_date(row[0]) if row else None
        if d is None or not start <= d <= end:
            return False
        return tab.media_col is None or medias is None or row[tab.media_col] in medias

    try:
        if sheet is None:
            raise gspread.WorksheetNotFound(tab.name)
        ws = sheet.worksheet(tab.name)
        existing = ws.get_all_values(
            value_render_option="UNFORMATTED_VALUE", date_time_render_option="SERIAL_NUMBER"
        )
    except gspread.WorksheetNotFound:
        ws, existing = None, []

    header = existing[0] if existing else tab.header
    old = [r for r in existing[1:] if any(c != "" for c in r)]
    kept = [r for r in old if not in_window(r)]
    new = [[to_cell(v) for v in r] for r in rows]
    merged = sorted(kept + new, key=lambda r: (to_date(r[0]) or dt.date.min, str(r[1])))

    summary = f"{tab.name}: 기존 {len(old)}행 중 {len(old) - len(kept)}행 교체 → 새 {len(new)}행, 합계 {len(merged)}행"
    if dry_run:
        print("[dry-run]", summary)
        return

    if ws is None:
        ws = sheet.add_worksheet(tab.name, rows=len(merged) + 1, cols=len(tab.header))
    total_rows = len(merged) + 1
    if ws.row_count < total_rows:
        ws.add_rows(total_rows - ws.row_count)

    # 먼저 덮어쓰고 남는 아래쪽만 지운다. 중간에 실패해도 기존 데이터가 통째로 비지 않게 하기 위함.
    ws.update([header] + merged, "A1", value_input_option="RAW")
    last_col = _col_letter(max(len(header), len(tab.header)) - 1)
    if len(existing) > total_rows:
        ws.batch_clear([f"A{total_rows + 1}:{last_col}{len(existing)}"])
    for col, pattern in tab.date_formats.items():
        letter = _col_letter(col)
        ws.format(f"{letter}2:{letter}{total_rows}", {"numberFormat": {"type": "DATE", "pattern": pattern}})
    print(summary)
