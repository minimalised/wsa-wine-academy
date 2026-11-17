"""임시 진단: 네이버 전환 데이터가 어떤 보고서·API로 오는지 확인한다."""
import datetime as dt
import json

from .naver_ads import NaverAds, NoData


def main():
    n = NaverAds()
    days = [dt.date(2026, 8, 5), dt.date(2026, 8, 20), dt.date(2026, 11, 10), dt.date(2026, 11, 16)]
    for tp in ("AD_CONVERSION", "AD_CONVERSION_DETAIL", "CONVERSION", "AD_DETAIL"):
        for day in days:
            try:
                rows = n._report(tp, day)
                print(f"[{tp} {day}] {len(rows)}행", rows[:2])
                if "CONVERSION" in tp and rows:
                    print("   전환 유형 열 후보:", sorted({tuple(r[11:13]) for r in rows})[:10])
            except Exception as e:  # noqa: BLE001
                print(f"[{tp} {day}] 오류 {type(e).__name__}: {str(e)[:300]}")

    camps = n._request("GET", "/ncc/campaigns").json()
    ids = [c["nccCampaignId"] for c in camps]
    print("캠페인 수:", len(ids))
    for since, until in (("2026-08-01", "2026-08-31"), ("2026-11-01", "2026-11-16")):
        params = {
            "ids": ",".join(ids),
            "fields": json.dumps(["impCnt", "clkCnt", "salesAmt", "ccnt", "convAmt"]),
            "timeRange": json.dumps({"since": since, "until": until}),
        }
        try:
            data = n._request("GET", "/stats", params=params).json()
            rows = data.get("data", [])
            total = {k: sum(r.get(k, 0) or 0 for r in rows) for k in ("impCnt", "clkCnt", "salesAmt", "ccnt", "convAmt")}
            print(f"[/stats {since}~{until}] 합계 {total}")
        except NoData:
            print(f"[/stats {since}~{until}] 지표 없음")
        except Exception as e:  # noqa: BLE001
            print(f"[/stats {since}~{until}] 오류 {str(e)[:300]}")


if __name__ == "__main__":
    main()
