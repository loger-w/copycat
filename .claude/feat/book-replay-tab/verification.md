# #268 回看頁「重播」分頁 —— verification

## 改動位置

- **repo 內**:零 code 改動;本分支只有 `.claude/feat/book-replay-tab/` artifacts。
- **repo 外**(`C:\Users\USER\Documents\copycat-trading-review`,不在 git):
  - `scripts/week0909/viewer_cdp_template.html`(備份 `viewer_cdp_template.html.bak-20260917`;diff = `evidence/viewer_cdp_template.diff`)
  - `viewer-cdp.html`(`build_viewer_cdp.py` 重產;備份 `viewer-cdp.html.bak-20260917`)
  - 新資料夾 `viewer-cdp-book/2026-09-16/`(80 檔、19.4 MB,copycat `book-replay` 產生)
  - 模板換行維持 CRLF(`LF 670 / CRLF 670`)

## 自動化 gate

| gate | 指令 | 結果 |
|---|---|---|
| pytest / ruff / pyright / validate / 前端 | — | N/A:repo 內零 code 改動(`git diff master...HEAD` 只有 artifacts);ticket 議定 viewer 不建測試框架 |
| 外掛檔產生 | `.venv\Scripts\python -m copycat book-replay --date 20260916 --dir data\ticks --out <回看頁>\viewer-cdp-book` | exit 0;「簿重播 2026-09-16:80 檔、2841208 則(達錢時刻異常、不當標籤時刻的成交 1 則),外掛檔 19.4 MB,耗時 69.3 秒」 |
| 回看頁重產 | `python scripts\week0909\build_viewer_cdp.py` | exit 0;`codes 55 code-days 2921 raw MB 28.07 gz MB 5.84 html MB 7.86` |
| 資料不變 | 解壓新舊 `viewer-cdp.html` 的 blob 比對 | payload 28,072,444 bytes **逐位元組相同**(gzip 檔頭 mtime 不同所以 base64 不同);`viewer-cdp.html == 模板 + blob` True |

## 真實環境(file:// 直接開,Chrome DevTools MCP,無任何服務)

1. **驗收樣本**:09/16 · 2426 · 拖到 11:02:44.5 → 標籤「成交 11:02:43 之後第 12 則」、收到 11:02:44.493、**99.1 那格 187 張**。
   同一格其他時刻對 #268 留言表:11:02:40.5 → 24;11:02:45.4 → 186;11:02:45.7 → 183。
   11:02:44.025 顯示「之後第 3 則」(留言表寫第 2 則):Python 解碼確認第 2、3 則收到時刻同為 39,764,025 ms,
   拖曳取「收到時刻 ≤ t 的最後一則」,兩則都是 187 張;逐則步進屬 #270。
2. **對照 Python 標準答案**(`evidence/rp_expected.py`,`copycat.book_replay.decode` 當 oracle):6 檔(2426 / 1815 / 3441 / 8064 / 2344 / 6770,
   含最大檔 2344)× 181 個隨機收到時刻(含首末則、1815 的異常成交則),比對標籤文字、買賣各價位量、市價佇列個數、現價列 ——
   **181 / 181 相同、0 失敗**;其中 70 個時刻有鎖停市價佇列。解碼 + 自檢耗時 36–102 ms。
3. **預設 ±10 檔 / 位置固定**:2426 9:30→11:03 共 8 個時刻皆 21 列、價格由高到低;現價在中心 ±5 檔內移動時整排不捲
   (9:30–9:35 top 98.9 不變),離開才重新置中;碰到漲停 99.8 時貼頂(現價列在第 3 列)。
4. **展開**:「展開漲停–跌停」→ 181 列 99.8…81.8(= 頁頭漲停 99.8、前收 90.8 的跌停);收回 → 21 列。
5. **橫條**(user 09-17 拍板改基準 = 收到時刻 13:25 前最大單格量):6 檔頁面說明列的基準值 = `evidence/qmax_before_1325.py` 獨立算的值(2426 4,087 / 1815 1,967 / 3441 1,428 / 8064 914 / 2344 3,680 / 6770 4,273);2426 99.1 的 187 張寬 4.6%(改前 1.5% = 187 / 全天 12,785);13:29:47 漲停 99.8 排隊 12,785 張畫滿 100%。
6. **十字線**:拖曳後分時 / K 線兩張圖十字線顯示「11:02:44」與現價「99.6 9.69%」。
7. **沒有簿的日子**:09/15 → 「這天沒有這檔的簿重播檔 viewer-cdp-book/2026-09-15/2426.js …」;回到 09/16 沿用原重播時刻。
8. **既有分頁未變**:舊頁(備份)與新頁各開獨立 context,5 組 代號|日期(2426|09-16、8064|09-09、1815|07-01、3441|09-10、2344|08-20)
   + 一組互動(開前三個圖例、回測選 A、K 週期 5)後,分時 SVG / K 線 SVG / 頁頭 / 族群列 / 圖例 / 左欄 / 逐筆 / 當日事件 / 回測 / 活潑日索引 / 分頁鈕
   的 innerHTML 雜湊**全部相同**;「定義與規則」在新增「重播」段之前的內容只差 2 個縮排空白。
9. **窄版**:390 寬(視窗實際 485)`scrollWidth == clientWidth`,無水平捲動;console 零 error / warn。

### review 收修後重跑(code-review-round-1.json 處置後,模板重產)

- Python 對照 **181 / 181 相同**;拖曳 181 點期間逐筆表 DOM 重繪 **0 次**(O-01 修正確認);解碼 + 自檢 33–88 ms。
- 驗收:11:02:44.5 → 「成交 11:02:43 之後第 12 則」、99.1 = 187、十字線「11:02:44 / 99.6 9.69%」、漲停列 99.8(改讀 D.lim 後不變)。
- 舊新頁 DOM 回歸:5 組 + 互動共 72 個區塊雜湊,舊頁 `7a9e70ce:1173` = 新頁 `7a9e70ce:1173`(「定義與規則」去尾端空白後比)。
- console 零 error / warn;模板 CRLF 671 / LF 671;回看頁 blob 仍是同一份資料(build 輸出 raw 28.07 MB 同前)。

截圖:`evidence/replay-2426-110244-after-qmax.png`(最終版)、`evidence/replay-2426-110244-fullpage.png`(改基準前)、`evidence/replay-2426-narrow-390.png`。

## 追加:非群組(簿重播)26 檔(user 09-17 拍板「先走 16 號的回放資料」)

改動(repo 外,備份皆 `.bak-20260917`;模板追加前另存 `viewer_cdp_template.html.pre-extras-20260917`):
新 `scripts/week0909/extras_from_archive.py`、`build_viewer_cdp.py`(diff `evidence/round2_build_viewer_cdp.diff`)、
`build_ticks_js.py`(`evidence/round2_build_ticks_js.diff`)、模板(`evidence/round2_template.diff`)。
資料:`data/ticks_archive/2026-09-16/`(27 檔,**刻意不放 `data/ticks/`** —— `combo_panel.py` / `bigtick_bt.py` 會掃整個資料夾)、`data/daily_extras.json`。

| 項目 | 指令 / 證據 | 結果 |
|---|---|---|
| 轉檔語意驗證 | `extras_from_archive.py --codes 2426,3441,8064,2344,1815,6770 --out-dir <scratch> --no-daily` + `evidence/archive_vs_history.py` | 6 檔對達錢歷史逐筆:盤中 1 分 K **逐根相同**,唯一差最後一根 = 歷史多 14:30 盤後定價交易一筆(存檔當天沒收到);內外盤「中」較少(存檔用成交前真實五檔) |
| 正式轉檔 | `.venv\Scripts\python -X utf8 extras_from_archive.py --date 2026-09-16` | exit 0;27 檔逐筆寫入、略過 0;日線 27 檔各 76 列到 2026-09-16 |
| 逐筆外掛檔 | `python build_ticks_js.py` | 「寫入 27 檔,略過 3024」—— 既有外掛檔零改寫;9/16 資料夾 82 檔 |
| 回看頁 | `python build_viewer_cdp.py` | `codes 81 extras 26`(7772 當日 2 筆 < 50 筆門檻略過) |
| 只加不改 | `evidence/payload_additive_check.py` | 新 payload 扣掉非群組新增 == 舊 payload **True**;非群組只出現在 2026-09-16 |
| 既有分頁回歸 | `evidence/dom_regression_compare.py cap_old.json cap_new.json` | 72 區塊 **0 不符**(左欄 / 活潑日索引 = 舊內容為新內容前綴,只在 9/16 左欄與索引尾多一段) |
| 頁面實測 | DevTools MCP | 2305 全友 9/16:頁頭前收 44.95 / 漲停 49.4 / 收盤鎖死、族群列說明、分時 / K 線、逐筆 4,942 筆、重播(10:30 → 現價 49.4、市價買 2229 張、十字線)、回測頁仍寫「55 檔」、索引含非群組;console 零 error。截圖 `evidence/extras-2305-replay.png` |

### round-2 review 收修後重跑(code-review-round-2.json)

- 轉檔重跑(is_trade 標記、pac 改名後)輸出與前版 `diff -rq` **相同**;`build_ticks_js.py`「寫入 0 檔,略過 3051」。
- `payload_additive_check.py`:扣非群組新增後仍 == 舊 payload **True**(`bars_of` 重構零行為);逐筆不完整只標 2243(12%)/ 6147(34%);
  6147 頁頭 開 201.5 / 高 207.5 / 低 197.5 / 收 207.5 / 振 5.0% / 開在 CDP-NH(= FinMind)。`extras_completeness.py`:其餘 24 檔量 94–100% 且開高低收與 FinMind 全等。
- DOM 回歸(`cap_old.json` vs `cap_new2.json`)**0 / 72 不符**。
- 頁面:6147 頁頭橘字「逐筆不完整:存檔第一筆 11:35:25、量 22,236 / 全日 64,857 張(34%)…」;活潑日索引 2305 碰觸 / 迴盪欄「— —」;
  驗收 2426 11:02:44.5 → 「成交 11:02:43 之後第 12 則」、99.1 = 187、橫條 4.6%;console 零 error。

## 已知 / 交給 user

- 橫條基準已依 user 拍板改成 13:25 前最大單格量(見上方第 5 點);置中維持遲滯。
- 非群組只有 2026-09-16;之後每天盤後依序跑 `book-replay` → `extras_from_archive.py --date` → `build_ticks_js.py` → `build_viewer_cdp.py`。
- 7772 耀穎(當日 2 筆)、3630 新鉅科 / 4977 眾達-KY(群組內,但 09-16 tick 存檔沒有它們的列,原因未查)沒有重播。
