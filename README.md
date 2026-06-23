# huaycheck-lao-data

Scraper bot that publishes **หวยลาวพัฒนา (Lao Pattana)** results as clean JSON for
the HuayCheck app. Mirrors `huaycheck-hanoi-data`.

- **Source:** `https://www.sanook.com/news/laolotto/` — parsed from the embedded
  `__NEXT_DATA__` Apollo cache (numbers are NOT in the rendered DOM).
- **Output:** `data/lao.json` →
  `{ generatedAt, draws: { lao_pattana: { date(AD YYYY-MM-DD), num4, top3, top2, animal, verified } } }`
- **Schedule:** GitHub Action, Mon–Fri ~20:30 + 22:00 ICT. Manual run via *Actions → Run workflow*.
- **App reads:** `lib/foreignFetch.ts` → `LAO_RESULTS_URL` (raw main/data/lao.json).

The scrape is intentionally isolated here so the fragile part never lives in the app.
A failed run keeps the last good `data/lao.json` (exits 0, no overwrite).
