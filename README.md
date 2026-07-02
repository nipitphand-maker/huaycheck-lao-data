# huaycheck-lao-data

Scraper bot that publishes **หวยลาวพัฒนา (Lao Pattana)** results as clean JSON for
the HuayCheck app. Mirrors `huaycheck-hanoi-data`.

- **Source:** `https://www.sanook.com/news/laolotto/` — parsed from the embedded
  `__NEXT_DATA__` Apollo cache (numbers are NOT in the rendered DOM).
- **Output:** `data/lao.json` →
  `{ generatedAt, draws: { lao_pattana: { date(AD YYYY-MM-DD), num4, top3, top2, animal, verified } } }`
- **Schedule:** GitHub Action, Mon–Fri, sweeping every 30 min from 13:00–16:30 UTC
  (≈20:00–23:30 ICT) — GitHub delays/drops scheduled jobs, so we retry rather than
  rely on one shot. The scraper is idempotent (dedup by date), so repeat runs just
  print "No change". Manual run via *Actions → Run workflow*.
- **App reads:** `lib/foreignFetch.ts` → `LAO_RESULTS_URL` (raw main/data/lao.json).

The scrape is intentionally isolated here so the fragile part never lives in the app.
A failed run keeps the last good `data/lao.json` (exits 0, no overwrite) so a single
blip is silent. **Staleness alarm:** the `--health-check` step fails the Action (→
GitHub emails the owner) only when the *published* data is older than `MAX_STALE_DAYS`,
so a genuine multi-day breakage gets loud instead of rotting behind a green check.
