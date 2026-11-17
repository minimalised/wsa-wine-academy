"""네이버 검색광고 API에서 일자별 대용량 보고서(StatReport)를 받아 시트 원본 탭(네이버_*) 형식으로 집계한다."""
import base64
import csv
import datetime as dt
import hashlib
import hmac
import io
import os
import time
from collections import defaultdict
from urllib.parse import urlparse

import requests

BASE_URL = "https://api.searchad.naver.com"

# AD_DETAIL: Date, Customer ID, Campaign ID, Ad Group ID, Ad Keyword ID, Ad ID, Business Channel ID,
#            Hours, Region code, Media code, PC Mobile Type, Impression, Click, Cost, Sum of AD rank, View count
# AD_CONVERSION: Date, Customer ID, Campaign ID, Ad Group ID, Ad Keyword ID, Ad ID, Business Channel ID,
#            Media code, PC Mobile Type, Conversion Method, Conversion Type, Conversion count, Sales by conversion
# 전환은 AD_CONVERSION_DETAIL이 아니라 AD_CONVERSION을 쓴다. DETAIL은 최근 기간만 남아 있어서 지난달 이전은 비어 있다.
DETAIL_COLS = {"campaign": 2, "adgroup": 3, "keyword": 4, "device": 10, "imp": 11, "clk": 12, "cost": 13}
CONV_COLS = {"campaign": 2, "adgroup": 3, "keyword": 4, "device": 8, "type": 10, "count": 11, "sales": 12}
CONV_REPORT = "AD_CONVERSION"

DEVICE = {"P": "PC", "M": "모바일"}
NO_DATA = 10004  # "선택하신 조건에 지표가 확인되지 않습니다"


class NoData(Exception):
    pass


def _error_code(res):
    try:
        return res.json().get("code")
    except ValueError:
        return None
PURCHASE = "purchase"


class NaverAds:
    def __init__(self):
        self.api_key = os.environ["NAVER_API_KEY"]
        self.secret = os.environ["NAVER_SECRET_KEY"]
        self.customer_id = os.environ["NAVER_CUSTOMER_ID"]
        self._names = None

    def _headers(self, method, uri):
        ts = str(int(time.time() * 1000))
        message = f"{ts}.{method}.{uri}".encode()
        signature = base64.b64encode(hmac.new(self.secret.encode(), message, hashlib.sha256).digest()).decode()
        return {
            "X-Timestamp": ts,
            "X-API-KEY": self.api_key,
            "X-Customer": str(self.customer_id),
            "X-Signature": signature,
        }

    def _request(self, method, uri, **kwargs):
        res = requests.request(method, BASE_URL + uri, headers=self._headers(method, uri), timeout=60, **kwargs)
        if res.status_code == 400 and _error_code(res) == NO_DATA:
            raise NoData()
        if not res.ok:
            raise RuntimeError(f"네이버 API {method} {uri} {res.status_code}: {res.text[:500]} (요청: {kwargs.get('json')})")
        return res

    # ---------- 이름 매핑 ----------

    def names(self):
        """캠페인·광고그룹·키워드 ID → 이름. 삭제된 키워드는 보고서에 ID만 남으므로 없으면 ID를 그대로 쓴다."""
        if self._names is None:
            campaigns, keywords = {}, {}
            for c in self._request("GET", "/ncc/campaigns").json():
                campaigns[c["nccCampaignId"]] = c["name"]
            for g in self._request("GET", "/ncc/adgroups").json():
                for k in self._request("GET", "/ncc/keywords", params={"nccAdgroupId": g["nccAdgroupId"]}).json():
                    keywords[k["nccKeywordId"]] = k["keyword"]
            self._names = {"campaign": campaigns, "keyword": keywords}
        return self._names

    # ---------- 대용량 보고서 ----------

    def _report(self, report_tp, day):
        try:
            job = self._request("POST", "/stat-reports", json={"reportTp": report_tp, "statDt": f"{day:%Y%m%d}"}).json()
        except NoData:
            # 그날 해당 지표가 하나도 없으면(예: 전환 0건) 보고서를 만들지 않고 400을 돌려준다.
            return []
        job_id = job["reportJobId"]
        try:
            for _ in range(60):
                job = self._request("GET", f"/stat-reports/{job_id}").json()
                if job["status"] == "BUILT":
                    break
                if job["status"] == "NONE":
                    return []
                if job["status"] in ("ERROR", "AGGREGATING_ERROR"):
                    raise RuntimeError(f"네이버 보고서 생성 실패: {report_tp} {day} {job['status']}")
                time.sleep(3)
            else:
                raise TimeoutError(f"네이버 보고서 대기 시간 초과: {report_tp} {day}")
            url = job["downloadUrl"]
            path = urlparse(url).path
            res = requests.get(url, headers=self._headers("GET", path), timeout=120)
            res.raise_for_status()
            rows = list(csv.reader(io.StringIO(res.content.decode("utf-8")), delimiter="\t"))
            _check_columns(report_tp, rows)
            return rows
        finally:
            self._request("DELETE", f"/stat-reports/{job_id}")

    def daily_facts(self, days):
        """일 × 캠페인ID × 키워드ID × 기기 단위로 노출·클릭·비용·구매완료 전환을 합친 dict."""
        facts = defaultdict(lambda: [0, 0, 0, 0, 0])
        conv_types = defaultdict(lambda: [0, 0])
        for day in days:
            for r in self._report("AD_DETAIL", day):
                key = (day, r[DETAIL_COLS["campaign"]], r[DETAIL_COLS["keyword"]], r[DETAIL_COLS["device"]])
                f = facts[key]
                f[0] += int(r[DETAIL_COLS["imp"]])
                f[1] += int(r[DETAIL_COLS["clk"]])
                f[2] += round(float(r[DETAIL_COLS["cost"]]))
            for r in self._report(CONV_REPORT, day):
                conv_types[r[CONV_COLS["type"]]][0] += int(r[CONV_COLS["count"]])
                conv_types[r[CONV_COLS["type"]]][1] += round(float(r[CONV_COLS["sales"]]))
                if r[CONV_COLS["type"]] != PURCHASE:
                    continue
                key = (day, r[CONV_COLS["campaign"]], r[CONV_COLS["keyword"]], r[CONV_COLS["device"]])
                f = facts[key]
                f[3] += int(r[CONV_COLS["count"]])
                f[4] += round(float(r[CONV_COLS["sales"]]))
        # 시트·광고 관리자 수치와 대조하기 쉽게 전환 유형별 합계를 남긴다.
        summary = ", ".join(f"{t} {c}건 {s:,}원" for t, (c, s) in sorted(conv_types.items()))
        print("네이버 전환 유형별 합계:", summary or "없음")
        return facts

    # ---------- 시트 탭 형식 ----------

    def _label(self, kind, id_):
        if id_ in ("", "-"):
            return "-"
        return self.names()[kind].get(id_, id_)

    def keyword_monthly(self, facts):
        """네이버_일반: 월별('2026.07.'), 캠페인, 키워드, 노출수, 클릭수, 총비용, 구매완료 전환수, 구매완료 전환매출액(원)"""
        out = defaultdict(lambda: [0, 0, 0, 0, 0])
        for (day, camp, kw, _device), f in facts.items():
            key = (f"{day:%Y.%m.}", self._label("campaign", camp), self._label("keyword", kw))
            out[key] = [a + b for a, b in zip(out[key], f)]
        return [[*k, *v] for k, v in out.items()]

    def device_daily(self, facts):
        """네이버_일자별_기기: 일별, 캠페인, PC/모바일 매체, 노출수 ~ 구매완료 전환매출액(원)"""
        out = defaultdict(lambda: [0, 0, 0, 0, 0])
        for (day, camp, _kw, device), f in facts.items():
            key = (day, self._label("campaign", camp), DEVICE.get(device, device))
            out[key] = [a + b for a, b in zip(out[key], f)]
        return [[*k, *v] for k, v in out.items()]


def _check_columns(report_tp, rows):
    """보고서 열 구성이 바뀌면 엉뚱한 열을 합산하지 않도록 바로 멈춘다."""
    cols = DETAIL_COLS if report_tp == "AD_DETAIL" else CONV_COLS
    need = max(cols.values()) + 1
    for r in rows[:1]:
        if len(r) < need or r[cols["device"]] not in DEVICE:
            raise RuntimeError(f"네이버 {report_tp} 열 구성이 예상과 다릅니다: {len(r)}열, 첫 행 {r}")


def days_between(start, end):
    return [start + dt.timedelta(days=i) for i in range((end - start).days + 1)]
