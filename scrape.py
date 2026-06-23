#!/usr/bin/env python3
"""
HuayCheck Lao data bot — scrapes หวยลาวพัฒนา (Lao Pattana) results from Sanook
and publishes a clean JSON the HuayCheck app reads (mirrors the Hanoi bot).

Source (verified 2026-06-23):
  - https://www.sanook.com/news/laolotto/  : Next.js page; results live in the
    embedded <script id="__NEXT_DATA__"> Apollo cache (recentLaoLotto +
    laoLottoes), NOT in the rendered DOM. We parse the JSON, not the HTML.

Output shape (matches the app's LaoDraw in lib/foreignFetch.ts):
  { "generatedAt": "...Z",
    "draws": { "lao_pattana": { "date": "YYYY-MM-DD",  # AD, not Buddhist era
                                "num4": "3818", "top3": "818", "top2": "18",
                                "animal": "แมวป่า", "verified": true } } }

Design rules (do NOT break):
  - Output JSON only — the fragile scrape lives HERE, never in the app.
  - Date is AD YYYY-MM-DD (the app does a strict string == compare).
  - Freshness guard: never emit a draw older than MAX_STALE_DAYS as current.
"""
import json
import re
import ssl
import sys
import urllib.request
from datetime import datetime, timezone, timedelta

try:
    import certifi
    _SSL_CTX = ssl.create_default_context(cafile=certifi.where())
except Exception:
    _SSL_CTX = ssl.create_default_context()

UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/148.0 Safari/537.36")
TIMEOUT = 30
MAX_STALE_DAYS = 4  # Lao draws Mon–Fri; a long weekend can legitimately be ~3 days old
URL = "https://www.sanook.com/news/laolotto/"
OUT = "data/lao.json"


def _fetch(url):
    req = urllib.request.Request(url, headers={
        "User-Agent": UA,
        "Accept": "text/html,application/xhtml+xml",
        "Accept-Language": "th,en;q=0.8",
    })
    with urllib.request.urlopen(req, timeout=TIMEOUT, context=_SSL_CTX) as r:
        return r.read().decode("utf-8", "ignore")


def _next_data(html):
    m = re.search(
        r'<script id="__NEXT_DATA__" type="application/json">(.*?)</script>',
        html, re.S)
    if not m:
        raise RuntimeError("no __NEXT_DATA__ block")
    return json.loads(m.group(1))


def _slug_to_ad_iso(slug):
    """'22062569' (ddmm + Buddhist year) -> '2026-06-22' (AD)."""
    if not slug or not re.fullmatch(r"\d{8}", slug):
        return None
    dd, mm, be = int(slug[:2]), int(slug[2:4]), int(slug[4:])
    ad = be - 543
    try:
        return datetime(ad, mm, dd).strftime("%Y-%m-%d")
    except ValueError:
        return None


def _digits(s):
    return s if (isinstance(s, str) and s.isdigit()) else None


def scrape():
    data = _next_data(_fetch(URL))
    apollo = data["props"]["serverState"]["apollo"]["data"]

    node = apollo.get("$ROOT_QUERY.recentLaoLotto") or {}
    pr = apollo.get("$ROOT_QUERY.recentLaoLotto.prizeResult") or {}

    slug = node.get("dateSlug")
    iso = _slug_to_ad_iso(slug)
    num4 = _digits(pr.get("last4Prize"))
    top3 = _digits(pr.get("last3Prize1")) or ""
    top2 = _digits(pr.get("last3Prize2")) or ""
    animal = pr.get("animalName") or None

    if not iso or not num4:
        raise RuntimeError(f"incomplete recentLaoLotto: slug={slug} num4={pr.get('last4Prize')!r}")

    # Freshness guard: reject a draw that's too old to be "current".
    today = datetime.now(timezone(timedelta(hours=7))).date()  # ICT
    draw_day = datetime.strptime(iso, "%Y-%m-%d").date()
    age = (today - draw_day).days
    if age > MAX_STALE_DAYS or age < 0:
        raise RuntimeError(f"stale/foreign-dated draw {iso} (age {age}d) — refusing to emit")

    return {
        "lao_pattana": {
            "date": iso,
            "num4": num4,
            "top3": top3,
            "top2": top2,
            "animal": animal,
            "verified": True,
        }
    }


def main():
    try:
        draws = scrape()
    except Exception as e:
        print(f"[lao] scrape failed (non-fatal, keeping last JSON): {e}", file=sys.stderr)
        # Exit 0 so a transient miss doesn't fail the Action; we simply don't
        # overwrite the previously-good data/lao.json.
        sys.exit(0)

    out = {
        "generatedAt": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "draws": draws,
    }
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=1)
    d = draws["lao_pattana"]
    print(f"[lao] {d['date']} num4={d['num4']} animal={d['animal']}")


if __name__ == "__main__":
    main()
