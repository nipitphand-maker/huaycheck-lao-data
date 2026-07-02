#!/usr/bin/env python3
"""
HuayCheck Lao data bot — scrapes หวยลาวพัฒนา (Lao Pattana) results from Sanook
and publishes a clean JSON the HuayCheck app reads (mirrors the Hanoi bot).

Source (verified 2026-06-28):
  - https://www.sanook.com/news/laolotto/  : Next.js page; results live in the
    embedded <script id="__NEXT_DATA__"> Apollo cache, NOT the rendered DOM:
      * $ROOT_QUERY.recentLaoLotto                 -> the latest draw
      * $ROOT_QUERY.laoLottoes({"first":6}).edges  -> the last ~6 draws
    Each node has dateSlug ("ddmmYYYY" Buddhist era) + a prizeResult ref whose
    object holds last4Prize / last3Prize1 / last3Prize2 / animalName.

Output shape (matches the app's LaoData in lib/foreignFetch.ts):
  { "generatedAt": "...Z",
    "draws":   { "lao_pattana": { ...latest draw... } },
    "history": { "lao_pattana": [ {newest}, ... up to HISTORY_LIMIT ] } }

History is ACCUMULATED across runs: the source only exposes ~6 recent draws, so
we merge each run's draws into the previously-published history (dedup by date,
newest-first, trimmed). Roughly a month fills in within ~3 weeks; the first run
already seeds 6 draws.

Design rules (do NOT break):
  - Output JSON only — the fragile scrape lives HERE, never in the app.
  - Date is AD YYYY-MM-DD (the app does a strict string == compare).
  - `draws.lao_pattana` stays exactly as before → old app versions keep working.
    `history` is additive — old apps ignore it.
  - Freshness guard: never promote a draw older than MAX_STALE_DAYS as "latest".
"""
import json
import os
import re
import ssl
import sys
import time
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
FETCH_RETRIES = 3        # transient network/CDN blips shouldn't cost us a whole run
RETRY_BACKOFF = 4        # seconds; grows 4s, 8s, 12s between attempts
MAX_STALE_DAYS = 4  # Lao draws Mon–Fri; a long weekend can legitimately be ~3 days old
HISTORY_LIMIT = 40  # ~1 month (Lao draws Mon–Fri ≈ 22/mo); keep a little extra
URL = "https://www.sanook.com/news/laolotto/"
OUT = "data/lao.json"


def _fetch(url):
    req = urllib.request.Request(url, headers={
        "User-Agent": UA,
        "Accept": "text/html,application/xhtml+xml",
        "Accept-Language": "th,en;q=0.8",
    })
    last = None
    for attempt in range(1, FETCH_RETRIES + 1):
        try:
            with urllib.request.urlopen(req, timeout=TIMEOUT, context=_SSL_CTX) as r:
                return r.read().decode("utf-8", "ignore")
        except Exception as e:  # network/TLS/HTTP blip — back off and retry
            last = e
            if attempt < FETCH_RETRIES:
                print(f"[lao] fetch attempt {attempt} failed ({e}); retrying…",
                      file=sys.stderr)
                time.sleep(RETRY_BACKOFF * attempt)
    raise last


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


def _node_to_draw(apollo, node):
    """Turn one LaoLotto node (+ its referenced prizeResult) into a draw dict,
    or None if it's incomplete."""
    if not node:
        return None
    iso = _slug_to_ad_iso(node.get("dateSlug"))
    ref = (node.get("prizeResult") or {}).get("id")
    pr = (apollo.get(ref) if ref else None) or {}
    num4 = _digits(pr.get("last4Prize"))
    if not iso or not num4:
        return None
    return {
        "date": iso,
        "num4": num4,
        "top3": _digits(pr.get("last3Prize1")) or "",
        "top2": _digits(pr.get("last3Prize2")) or "",
        "animal": pr.get("animalName") or None,
        "verified": True,
    }


def scrape():
    """Return draws newest-first (the latest + the laoLottoes list), deduped."""
    apollo = _next_data(_fetch(URL))["props"]["serverState"]["apollo"]["data"]

    nodes = []
    recent = apollo.get("$ROOT_QUERY.recentLaoLotto")
    if recent:
        nodes.append(recent)
    # laoLottoes is paginated — the arg string can vary ("first":6 today), so
    # match any edges.N.node key rather than hard-coding the query args.
    edge_keys = sorted(
        k for k in apollo
        if re.fullmatch(r'\$ROOT_QUERY\.laoLottoes\(.*\)\.edges\.\d+\.node', k)
    )
    nodes.extend(apollo[k] for k in edge_keys)

    draws, seen = [], set()
    for n in nodes:
        d = _node_to_draw(apollo, n)
        if d and d["date"] not in seen:
            seen.add(d["date"])
            draws.append(d)
    if not draws:
        raise RuntimeError("no complete Lao draws found in __NEXT_DATA__")
    draws.sort(key=lambda d: d["date"], reverse=True)
    return draws


def _load_existing_history():
    if not os.path.exists(OUT):
        return []
    try:
        with open(OUT, encoding="utf-8") as f:
            prev = json.load(f)
        hist = (prev.get("history") or {}).get("lao_pattana") or []
        # tolerate older JSON that only had draws.lao_pattana
        if not hist:
            latest = (prev.get("draws") or {}).get("lao_pattana")
            if latest:
                hist = [latest]
        return [d for d in hist if d.get("date") and d.get("num4")]
    except Exception as e:
        print(f"[lao] could not read existing {OUT}: {e}", file=sys.stderr)
        return []


def _merge_history(fresh, existing):
    """Newest-first, dedup by date (fresh wins), trimmed to HISTORY_LIMIT."""
    by_date = {}
    for d in existing:
        by_date[d["date"]] = d
    for d in fresh:  # fresh overwrites — re-scrapes may correct a value
        by_date[d["date"]] = d
    merged = sorted(by_date.values(), key=lambda d: d["date"], reverse=True)
    return merged[:HISTORY_LIMIT]


def health_check():
    """Alarm mode: exit non-zero if the *published* latest draw is stale.

    The scraper deliberately exits 0 on a single failed run (a transient miss
    shouldn't paint the Action red when it fires ~8×/day). The downside is that
    a *real* breakage — Sanook changing their JSON, blocking the UA — would keep
    the Action green while data silently rots. This step closes that gap: it
    reads what we actually published and fails the job (→ GitHub emails the
    owner) only once data has been stale beyond MAX_STALE_DAYS, i.e. many runs
    have missed in a row. One-day blips stay quiet; genuine outages get loud.
    """
    if not os.path.exists(OUT):
        print(f"[lao] health: {OUT} is missing", file=sys.stderr)
        sys.exit(1)
    try:
        with open(OUT, encoding="utf-8") as f:
            latest = (json.load(f).get("draws") or {}).get("lao_pattana") or {}
    except Exception as e:
        print(f"[lao] health: cannot read {OUT}: {e}", file=sys.stderr)
        sys.exit(1)

    date = latest.get("date")
    if not date:
        print("[lao] health: no latest draw in published JSON", file=sys.stderr)
        sys.exit(1)

    today = datetime.now(timezone(timedelta(hours=7))).date()  # ICT
    age = (today - datetime.strptime(date, "%Y-%m-%d").date()).days
    if age > MAX_STALE_DAYS:
        print(f"[lao] health: FAIL — latest published draw {date} is {age}d old "
              f"(> {MAX_STALE_DAYS}); the scraper is likely broken.", file=sys.stderr)
        sys.exit(1)
    print(f"[lao] health: OK — latest published draw {date} ({age}d old)")


def main():
    try:
        fresh = scrape()
    except Exception as e:
        print(f"[lao] scrape failed (non-fatal, keeping last JSON): {e}", file=sys.stderr)
        # Exit 0 so a transient miss doesn't fail the Action; we simply don't
        # overwrite the previously-good data/lao.json.
        sys.exit(0)

    # Freshness guard on the LATEST draw only — history may legitimately be old.
    today = datetime.now(timezone(timedelta(hours=7))).date()  # ICT
    newest = datetime.strptime(fresh[0]["date"], "%Y-%m-%d").date()
    age = (today - newest).days
    if age > MAX_STALE_DAYS or age < 0:
        print(f"[lao] newest draw {fresh[0]['date']} too old/foreign (age {age}d) — "
              f"keeping last JSON", file=sys.stderr)
        sys.exit(0)

    history = _merge_history(fresh, _load_existing_history())
    latest = history[0]

    out = {
        "generatedAt": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "draws": {"lao_pattana": latest},
        "history": {"lao_pattana": history},
    }
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=1)
    print(f"[lao] latest {latest['date']} num4={latest['num4']} animal={latest['animal']} "
          f"· history={len(history)} draws")


if __name__ == "__main__":
    if "--health-check" in sys.argv:
        health_check()
    else:
        main()
