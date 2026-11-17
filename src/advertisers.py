"""advertisers.yml을 읽어 GitHub Actions matrix로 쓸 광고주 목록(JSON)을 출력한다."""
import argparse
import json
import pathlib

import yaml

CONFIG = pathlib.Path(__file__).resolve().parent.parent / "advertisers.yml"
SOURCES = {"google", "naver"}
DESTINATIONS = {"sheets_wsa"}


def load():
    items = yaml.safe_load(CONFIG.read_text(encoding="utf-8"))["advertisers"]
    ids = [a["id"] for a in items]
    if len(ids) != len(set(ids)):
        raise SystemExit("advertisers.yml에 같은 id가 두 번 있습니다")
    for a in items:
        unknown = set(a["sources"]) - SOURCES
        if unknown:
            raise SystemExit(f"{a['id']}: 지원하지 않는 매체 {sorted(unknown)}")
        if a["destination"] not in DESTINATIONS:
            raise SystemExit(f"{a['id']}: 지원하지 않는 적재 방식 {a['destination']}")
    return items


def select(items, only):
    """only가 비어 있으면 enabled인 광고주 전부, 있으면 쉼표로 적은 id만(enabled와 무관)."""
    if not only:
        return [a for a in items if a.get("enabled", True)]
    wanted = {s.strip() for s in only.split(",") if s.strip()}
    unknown = wanted - {a["id"] for a in items}
    if unknown:
        raise SystemExit(f"advertisers.yml에 없는 광고주: {sorted(unknown)}")
    return [a for a in items if a["id"] in wanted]


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--only", default="", help="쉼표로 구분한 광고주 id")
    args = p.parse_args()
    matrix = [
        {"id": a["id"], "name": a["name"], "prefix": a.get("secret_prefix", ""), "sources": ",".join(a["sources"])}
        for a in select(load(), args.only)
    ]
    if not matrix:
        raise SystemExit("실행할 광고주가 없습니다")
    print(json.dumps(matrix, ensure_ascii=False))


if __name__ == "__main__":
    main()
