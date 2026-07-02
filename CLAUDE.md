# CLAUDE.md — huaycheck-lao-data

Scraper bot ที่ดึงผล **หวยลาวพัฒนา (Lao Pattana)** จาก Sanook แล้ว publish เป็น
`data/lao.json` ให้แอป HuayCheck อ่าน (mirror ของ `huaycheck-hanoi-data`)

## สถาปัตยกรรมโดยย่อ
- **Source:** `https://www.sanook.com/news/laolotto/` — เลขอยู่ใน `__NEXT_DATA__`
  Apollo cache (`recentLaoLotto` + `laoLottoes` edges), **ไม่ใช่** ใน rendered DOM
  → เรา parse JSON ไม่ใช่ HTML
- **Output:** `data/lao.json` = `{ generatedAt, draws.lao_pattana, history.lao_pattana }`
  - `date` เป็น **AD `YYYY-MM-DD`** (แอปเทียบ string ตรงๆ — ห้ามเป็นพุทธศักราช)
  - `history` สะสมข้ามรอบ (source โชว์แค่ ~6 งวด) dedup by date, เก็บ `HISTORY_LIMIT=40`
- **แอปอ่านจาก:** `lib/foreignFetch.ts` → `LAO_RESULTS_URL` = raw `main/data/lao.json`
  → **การแก้ต้อง merge เข้า `main`** ถึงจะมีผล (ทั้งแอปและ scheduled Action รันจาก main)

## การทำงาน / กติกาที่ห้ามพัง
- **ออกผล:** จันทร์–ศุกร์ ~20:30 ICT (= 13:30 UTC) เสาร์-อาทิตย์ไม่ออก
- **Schedule:** cron `*/30 13-16 * * 1-5` (กวาดทุก 30 นาที ~20:00–23:30 ICT)
  GitHub ดีเลย์/ดรอป scheduled job เป็นปกติ → เลยยิงหลายรอบ สคริปต์ idempotent
  (dedup by date) รันซ้ำเจอข้อมูลเดิมก็ `No change` ฟรี
- **Freshness guard:** ไม่ promote งวดที่เก่ากว่า `MAX_STALE_DAYS=4` เป็น "ล่าสุด"
  (4 วันครอบเสาร์-อาทิตย์พอดี)
- **พังแล้วเงียบ = ห้าม:** scrape fail → `exit 0` (เก็บ JSON เดิม, ไม่ทับ) เพื่อ
  ไม่ให้ blip วันเดียวทำ Action แดง **แต่** มี `python scrape.py --health-check`
  (step `if: always()`) ที่ทำ Action **แดง + GitHub เมลเจ้าของ** เมื่อข้อมูลที่
  publish แล้วเก่าเกิน `MAX_STALE_DAYS` = พังจริงต่อเนื่อง

## แก้ปัญหาที่เจอบ่อย
- **"ข้อมูลไม่อัพเดทวันนี้"** → เช็กก่อนว่าเป็นเสาร์-อาทิตย์ไหม (ไม่ออกผล = ปกติ),
  หรือ Action วันนี้ยังไม่ทันรัน (GitHub ดีเลย์ ~1–3 ชม.) ถ้าหวยออกแล้วอยากได้ทันที
  → กด manual: Actions → Run workflow (workflow_dispatch) บน main
- **เช็กว่า bot พังจริงไหม** → ดู Actions runs ว่ามี fail ไหม + เทียบ
  `data/lao.json` (`date`) กับวันนี้ ถ้าห่างเกิน 4 วันในวันธรรมดา = พังจริง
- **ถ้าเมลเตือน (health-check fail) เด้ง** = ควรเข้าดูจริงจัง ยกเว้นช่วงวันหยุดยาว
  (สงกรานต์/ปีใหม่) ที่ลาวหยุดหลายวัน อาจเป็น false alarm — ค่อยพิจารณาขยับ
  `MAX_STALE_DAYS`

## กติกา dev
- **เปลี่ยน output shape = ระวังสุด** — `draws.lao_pattana` ต้องคงรูปเดิม (แอปเก่า
  ยังอ่านได้), `history` เป็น additive
- **network hiccup:** `_fetch` retry 3× backoff อยู่แล้ว
- ใน 環境 sandbox นี้ scrape จริงจะโดน proxy block (403) — ทดสอบ scrape จริงต้อง
  ผ่าน GitHub Action; แต่ `--health-check` กับ logic อื่นทดสอบ local ได้
