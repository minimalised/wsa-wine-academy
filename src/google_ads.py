"""Google Ads API에서 시트 원본 탭(구글_*) 형식의 행을 가져온다."""
import datetime as dt
import os

from google.ads.googleads.client import GoogleAdsClient

DEVICE = {
    "DESKTOP": "컴퓨터",
    "MOBILE": "휴대전화",
    "TABLET": "태블릿",
    "CONNECTED_TV": "TV 화면",
    "OTHER": "기타",
}

AGE = {
    "AGE_RANGE_18_24": "만 18~24세",
    "AGE_RANGE_25_34": "만 25~34세",
    "AGE_RANGE_35_44": "만 35~44세",
    "AGE_RANGE_45_54": "만 45~54세",
    "AGE_RANGE_55_64": "만 55~64세",
    "AGE_RANGE_65_UP": "65세 이상",
    "AGE_RANGE_UNDETERMINED": "알 수 없음",
}

GENDER = {"MALE": "남성", "FEMALE": "여성", "UNDETERMINED": "알 수 없음"}

METRICS = (
    "metrics.impressions, metrics.clicks, customer.currency_code, "
    "metrics.cost_micros, metrics.conversions, metrics.conversions_value"
)


def _client():
    config = {
        "developer_token": os.environ["GOOGLE_ADS_DEVELOPER_TOKEN"],
        "client_id": os.environ["GOOGLE_ADS_CLIENT_ID"],
        "client_secret": os.environ["GOOGLE_ADS_CLIENT_SECRET"],
        "refresh_token": os.environ["GOOGLE_ADS_REFRESH_TOKEN"],
        "use_proto_plus": True,
    }
    login_id = os.environ.get("GOOGLE_ADS_LOGIN_CUSTOMER_ID", "").replace("-", "")
    if login_id:
        config["login_customer_id"] = login_id
    return GoogleAdsClient.load_from_dict(config)


class GoogleAds:
    def __init__(self):
        self.client = _client()
        self.service = self.client.get_service("GoogleAdsService")
        self.customer_id = os.environ["GOOGLE_ADS_CUSTOMER_ID"].replace("-", "")

    def _search(self, query):
        stream = self.service.search_stream(customer_id=self.customer_id, query=query)
        for batch in stream:
            yield from batch.results

    @staticmethod
    def _metrics(r):
        return [
            r.metrics.impressions,
            r.metrics.clicks,
            r.customer.currency_code,
            round(r.metrics.cost_micros / 1_000_000),
            round(r.metrics.conversions, 2),
            round(r.metrics.conversions_value, 2),
        ]

    @staticmethod
    def _where(start, end):
        return (
            f"WHERE segments.date BETWEEN '{start:%Y-%m-%d}' AND '{end:%Y-%m-%d}' "
            "AND metrics.impressions > 0"
        )

    def campaign_monthly(self, start, end):
        """구글_일반: 월, 캠페인, 노출수, 클릭수, 통화 코드, 비용, 전환, 전환 가치"""
        q = f"SELECT segments.month, campaign.name, {METRICS} FROM campaign {self._where(start, end)}"
        return [
            [_date(r.segments.month), r.campaign.name, *self._metrics(r)]
            for r in self._search(q)
        ]

    def keyword_monthly(self, start, end):
        """구글_일반_키워드: 월, 캠페인, 검색 키워드, 노출수 ~ 전환 가치"""
        q = (
            f"SELECT segments.month, campaign.name, ad_group_criterion.keyword.text, {METRICS} "
            f"FROM keyword_view {self._where(start, end)}"
        )
        return _sum_rows(
            [
                [_date(r.segments.month), r.campaign.name, r.ad_group_criterion.keyword.text, *self._metrics(r)]
                for r in self._search(q)
            ],
            key_len=3,
        )

    def device_daily(self, start, end):
        """구글_일자별_기기: 일, 캠페인, 기기, 노출수 ~ 전환 가치"""
        q = (
            f"SELECT segments.date, campaign.name, segments.device, {METRICS} "
            f"FROM campaign {self._where(start, end)}"
        )
        return [
            [_date(r.segments.date), r.campaign.name, DEVICE.get(r.segments.device.name, r.segments.device.name),
             *self._metrics(r)]
            for r in self._search(q)
        ]

    def age_monthly(self, start, end):
        """구글_연령: 월, 캠페인, 연령, 노출수 ~ 전환 가치"""
        q = (
            f"SELECT segments.month, campaign.name, ad_group_criterion.age_range.type, {METRICS} "
            f"FROM age_range_view {self._where(start, end)}"
        )
        return _sum_rows(
            [
                [_date(r.segments.month), r.campaign.name,
                 AGE.get(r.ad_group_criterion.age_range.type_.name, r.ad_group_criterion.age_range.type_.name),
                 *self._metrics(r)]
                for r in self._search(q)
            ],
            key_len=3,
        )

    def gender_monthly(self, start, end):
        """구글_성별: 월, 캠페인, 성별, 노출수 ~ 전환 가치"""
        q = (
            f"SELECT segments.month, campaign.name, ad_group_criterion.gender.type, {METRICS} "
            f"FROM gender_view {self._where(start, end)}"
        )
        return _sum_rows(
            [
                [_date(r.segments.month), r.campaign.name,
                 GENDER.get(r.ad_group_criterion.gender.type_.name, r.ad_group_criterion.gender.type_.name),
                 *self._metrics(r)]
                for r in self._search(q)
            ],
            key_len=3,
        )


def _date(s):
    return dt.date.fromisoformat(s)


def _sum_rows(rows, key_len):
    """광고그룹 단위로 나뉘어 나오는 행을 앞 key_len개 열 기준으로 합친다. 통화 코드 열은 그대로 둔다."""
    out = {}
    for row in rows:
        key = tuple(row[:key_len])
        if key not in out:
            out[key] = list(row)
            continue
        acc = out[key]
        for i in range(key_len, len(row)):
            if isinstance(row[i], (int, float)):
                acc[i] = round(acc[i] + row[i], 2)
    return list(out.values())
