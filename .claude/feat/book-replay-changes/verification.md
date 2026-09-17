# #269 變動分解 + 重新可見 + 成交明細吃檔欄 —— verification

> 2026-09-17。前半(引擎、測試頁、review round 1)由上一個 session 做,context 將滿換 session;接手 session 收修模板、
> 重驗、切換、收尾。本檔以接手後的最終版本為準,上一版草稿的數字凡被重跑覆蓋的都已換新。

## 改動位置

- **repo 內**(branch `feat/book-replay-changes`;收尾前 rebase 到 origin/master `71c9f077`,零衝突):
  `copycat/book_replay.py`(引擎 + 外掛檔 v2)、`tests/test_book_replay.py`、`CONTEXT.md`(術語)、`CLAUDE.md` §1 簿重播外掛檔那列、
  `docs/next-time.md`。commit(rebase 後 SHA;review JSON 內的舊 SHA 對照見 `code-review-round-1.json` 的 `rebased_onto`):

  | SHA | 類 | 內容 |
  |---|---|---|
  | 8fef187b | feat | 變動分解(掛入 / 撤單 / 成交)寫進外掛檔 v2 `chg` |
  | d64df816 | feat | 視野:被擠出五檔 / 重新可見 / 首次進入五檔,都不算掛單 |
  | a3b46754 | feat | 吃檔 `eat` |
  | b0334897 | feat | decode 自檢補 `chg` / `eat` |
  | 0d365a30 | feat | 五檔全空 = 達錢清空五檔 |
  | a5afc782 | chore | CONTEXT.md 術語、CLAUDE.md §1 改 v2 |
  | ea193356 | refactor | review S-05–S-09(不改行為) |
  | ace31593 | fix | review P-01 同一筆成交扣兩次 |
  | 11a5b225 | feat | review S-01–S-03 / S-10(價位變動 7 格、字面測試) |
  | 549c070c | chore | CLAUDE.md §1 實測數字換成 7 格版重產值 |
  | 43a10553 | chore | next-time:#269 留尾、盤後補資料第 1 步改 v2 CLI |
  | a8060d58 | chore | tc4-market-facts:鎖漲停內外盤旗標也恆 outer(兩天全數核對) |

- **repo 外**(`C:\Users\USER\Documents\copycat-trading-review`,不在 git):回看頁模板 `scripts/week0909/viewer_cdp_template.html`。
  開發期間另一個 session 同時在補 09-17 回看頁,user 拍板「先在旁邊做完,最後一次切換」:
  - 工作模板 = `evidence/viewer_cdp_template.269.html`,由 `evidence/patch_template_269.py` 套在**現用模板複本**上產生
    (保留 CRLF);對現用模板的 diff = `evidence/viewer_cdp_template.diff`(+94 / −9);對 review 當時版本的增量 =
    `evidence/viewer_cdp_template.review1.diff`(+35 / −29)
  - 測試頁 `viewer-cdp.269.html` = 工作模板 + 現用頁資料 blob,外掛檔讀暫存 `viewer-cdp-book-269/`(`evidence/build_stage_page.py`;
    每次重建都先驗「現用頁 == 現用模板 + blob」為 True)
  - 回歸舊頁 `viewer-cdp.pre269.html` = 現用頁複本,讀 `viewer-cdp-book/` 的 v1。**接手時發現原複本是 15:06 版**,另一個 session
    15:36 又重建過現用頁(9/17 群組 55 檔、9/16 六檔回測欄等資料不同),測試頁重建會拿到 15:36 的 blob,兩頁資料對不上 →
    16:29 以現用頁重新複製後才重跑回歸(該 session 事後來訊息確認同一件事)
  - 切換腳本 `evidence/switch_live_269.py`;備份 `viewer-cdp-book.bak-20260917-pre269`(外掛檔資料夾,含 09-16 / 09-17 v1;
    16:1x 逐檔比雜湊 = 現用 v1 兩天各 80 檔全同)

## user 拍板

1. 看得到的範圍 = 價位掉到第五檔之外才算離開;票上「賣 92.0 淨掛 +154」不成立(那 149 張是 92.0 當買方價位時的內盤),
   驗收樣本改 2426 買 98.0(39 → 120,淨掛 +81,2 分 35 秒)與 2489 賣 39.2(80 → 0,期間成交 80,淨掛 0)
2. 成交扣減往後 8 則且 1 秒內;市價排隊減少也先算成交
3. 中間欄 = 到目前這一則為止的最近 N 則,新的在上、目前這則標亮;量沒變的重新可見淡色照列。**N 原定 12,review P-02 證明播放會漏則,
   user 改拍 60**(選項說明已講明「10x 展開時偶爾掉一幀」)
4. 買賣兩側全空的一則 = 達錢清空五檔,不拆變動,下一則跟清空前那一份比
5. 協調:另一個 session 在動現用頁 → 先在旁邊做完、最後一次切換,切換前問 user 那邊收工沒
6. (實作決定,依 user「JS 不重算」)價位變動的掛入 / 撤單張數寫進外掛檔(7 格,檔案 +5.7–8.9%);「首次進入五檔」維持
   (開工時的範圍說明列過、user 回「照這個開工」;review P-03)

前四條已在 #269 留言;第 3 條的「播放跨則不漏」更正、第 6 條待收尾時補留言。

## 紅先行紀錄(review P-05)

測試與實作同 commit,紅燈證據在上一個 session 的對話紀錄
`~\.claude\projects\C--side-project-copycat--claude-worktrees-feat-book-replay-changes\d9c7968b-fe95-48b5-b8f3-fa38d2246aa1.jsonl`
(時刻 UTC;每個切片都是先寫測試跑紅、實作後轉綠再 commit):

| 切片(commit) | 紅燈 | 內容 |
|---|---|---|
| 變動分解(8fef187b) | 06:34:27 | collection ImportError:`cannot import name 'LevelChange'` |
| | 06:36:24 | 1 failed `test_payload_layout_matches_the_documented_v1_literal`(格式本來就要變,開工時已標「該變」) |
| | 06:37:42 | 1 failed `test_fewer_lots_count_the_trade_at_that_price_first_and_the_rest_as_cancelled` |
| | 06:38:54 | 3 failed:掃單晚幾則才反映、`...at_most_eight_messages_and_one_second[8-messages-later / 1000ms-later]` |
| | 06:39:50 | 1 failed `test_a_locked_limit_up_queue_that_shrinks_on_a_trade_reads_as_traded` |
| 視野(d64df816) | 06:44:44 | collection error(新型別尚未存在) |
| 吃檔(a3b46754) | 06:51:07 / 06:52:58 | collection error → 12 failed(外掛檔加 `eat` 後 round-trip 與 decode 拒收測試) |
| decode 自檢(b0334897) | 06:55:44 / 06:56:21 | 12 failed(新竄改案例)→ 1 failed `[reappeared-now]` |
| 五檔全空(0d365a30) | 07:07:02 | 2 failed `TestClearedBook` 兩案 |
| review P-01(ace31593) | 08:03:46 | 1 failed `test_a_trade_counted_while_its_price_was_out_of_view_is_not_taken_again` |
| review S-02 / S-10(11a5b225) | 08:07:46 | 11 failed:v2 字面(7 格)、八種種類碼字面、掛入 / 撤單算式竄改等 |
| review S-05–S-09(ea193356) | — | 純重構不寫新測試;83 條不動全綠,09-16 七檔外掛檔重構前後逐位元組相同 |

## 自動化 gate(`43a10553`,rebase 後;其後只多 `a8060d58` skill 文件一筆,不影響下列 gate)

| gate | 指令 | 結果 |
|---|---|---|
| 測試 | `C:/side-project/copycat/.venv/Scripts/python -m pytest -q -p no:cacheprovider` | exit 0,**3648 passed, 3 skipped**(234.4 s;上次 3644 + review 收修新增 4 條);2 warnings 皆與本改動無關(fastapi testclient 的 Starlette 棄用、`test_tick_persist` 假檔 close 失敗的 unraisable) |
| Lint | `... -m ruff check copycat tests` | exit 0,All checks passed |
| 格式 | `... -m ruff format --check copycat/book_replay.py tests/test_book_replay.py` | exit 0,2 files already formatted |
| 型別 | `... -m pyright` | exit 0,0 errors, 0 warnings, 0 informations |
| Golden | `... -m copycat validate --run-five C:/side-project/copycat/out/five_tigers --run-four C:/side-project/copycat/out/four_tigers --out <scratchpad>` | exit 0,**42/42 PASS** |
| 行長 | 以字元計(ruff 無 E501、formatter 不拆字串)| 兩檔相對 fixed point 新增 > 100 字元的行 0 |
| 前端 | — | N/A:repo 內零 frontend 改動 |
| 模板語法 | `python evidence/syntax_check.py viewer-cdp.269.html`(抽 `<script>` → `node --check`) | SYNTAX-OK |

## 引擎實測

- **CLI 重產**(11a5b225 = 最終引擎;`evidence/run_with_peak_memory.py` 量子行程峰值工作集):
  - 09-16:80 檔 2,841,208 則、**36.4 MB**、157.9 秒、**峰值 5.68 GB**(`evidence/cli_run_20260916.txt`)
  - 09-17:80 檔 3,873,307 則、**49.2 MB**、214.7 秒、**峰值 7.77 GB**(`evidence/cli_run_20260917.txt`)
  - CLI 逐檔解回自檢相等才落檔 → 兩天 160 檔全數落檔 = decode 自檢(含 `chg` / `eat`)全過;抽查 1303 兩天價位變動項為 7 格
- **不重複扣不變式**(P-01 修後,09-16 全 80 檔,`evidence/no_double_count_check.py` → `result_no_double_count.txt`):
  成交則 375,387;有檔位的吃檔 1,279,200 張 = 價位變動算成交 1,279,200 張;五檔外吃檔 969 張 ≥ 重新可見期間成交 808 張;
  吃檔超過成交張數的成交 0。review 點名的 3374 #2288 改成「−2 撤單」不再算成交、6209 #754 吃檔「買五檔外 −61」、#756「買1 −6」
- **當日第一份五檔**:兩天 160 檔第 0 則都不是五檔全空(頁面 `firstBook` 與 decode 的「前一份五檔」同一把尺,現有資料恆為 0)
- **吃檔側別 vs 內外盤**(review 後快篩順帶查,`evidence/eaten_side_check.py` / `eaten_side_breakdown.py`):相反 09-16 33,515 張
  (市價排隊 33,306、同筆兩側 86、集合競價 30、暫緩撮合後 57、其他 36)、09-17 25,237 張(24,389 / 121 / 104 / 486 / 137);
  「其他」逐筆看是鎖板打開時賣方沿買方排隊掃下去(前一簿賣方全空)與 6147 一筆 1 張(前後兩則隔 56 秒)。= 鎖漲停時達錢旗標
  恆外盤,吃檔照實際減量那一側記;引擎不改,畫面註明與否入 next-time
- 上一個 session 在 P-01 修之前量的全 80 檔分布(未重跑,僅供參考):成交扣減同一則 88.08% + 晚 1–8 則 2.38% + 市價排隊 3.02%;
  重新可見 71,845(量有變 26,616)、離開期間有成交 43、首次進入 2,488

## 真實環境(測試頁 `viewer-cdp.269.html`,file:// + headless Chrome 152)

瀏覽器:chrome-devtools-mcp 內嵌 puppeteer 開獨立暫存 profile(`evidence/pp_common.mjs`,沿 #270;`RP_NEW_PAGE` / `RP_OLD_PAGE`
環境變數可改開正式頁)。

### 1. 畫面對標準答案(`rp269_expected.py` → `verify_changes.mjs` → `result_verify_changes.json`)

- 標準答案 = worktree `copycat.book_replay.decode` 解暫存 v2 檔;13 檔 × 兩天(09-16 10 檔含非群組 2305 / 2489 / 6715、09-17 3 檔)
  × 594 則:首末、隨機,與每種變動各抽(被擠出 / 重新可見量有變・量沒變・期間有成交・離開 ≥ 1 分 / 首次進入 / 市價排隊 /
  成交與撤單並存 / 五檔全空與其下一則 / 吃檔 買賣1・深檔・市價・五檔外・沒吃檔 / 時刻異常成交)+ 驗收樣本
- 每則比:則號、中間欄 **60 組**(標頭、每行文字、淡色與否、目前這則標亮;沒有變動的則分「當日第一份五檔」/ 五檔全空 / 沒有變動)、
  成交明細 20 列(時間 / 價 / 張 / 內外 / 吃檔、標亮)
- **594 則 0 不符**;竄改標準答案 3 處(標頭、吃檔、淡色)→ **3/3 抓出**;console 0 錯誤(懸掛縮排 CSS 改完後重跑,結果相同)

### 2. 播放時同一刻 + 流暢度(`rp269_segment_expected.py` → `verify_playback_sync.mjs` → `result_playback_sync.json`)

- 2426 09-16 11:02:00 → 首次鎖漲停(第 61,737 則),標準答案涵蓋 11:02:00–11:03:00 共 966 則;每次重畫(#rpIdx MutationObserver)
  讀中間欄 60 組與成交明細比標準答案:**1x 重畫 423 次、10x 216 次,全部比對、0 不符**(與階梯同一則;懸掛縮排 CSS 改完後的最終測試頁)
- 流暢度(同 #270 口徑,headless;量測時機器閒置 —— 第一次重跑時同時跑了 50 秒的 Python 側別檢查,數字作廢重量):

| 情境 | 真實耗時 | 每幀回呼 p95 / max | 幀間隔 p99 / max | 每秒回呼總耗時 max | 長框 > 50 ms |
|---|---|---|---|---|---|
| 1x 一般 | 50.9 s | 2.9 / 4.3 ms | 16.8 / 16.9 ms | 46.0 ms | 0 |
| 1x 展開 | 50.9 s | 3.4 / 5.8 ms | 16.8 / 16.9 ms | 55.7 ms | 0 |
| 10x 一般 | 5.1 s | 3.1 / 3.8 ms | 16.8 / 16.9 ms | 164.7 ms | 0 |
| 10x 展開 | 5.1 s | 3.9 / 5.8 ms | 16.8 / 16.9 ms | 194.8 ms | 0 |

  逐則步進 798 次同步更新(含強制 layout):一般 p50 5.0 / p95 6.1 / max 10.2 ms、展開 p50 7.7 / p95 10.5 / max 18.1 ms
  (12 則時 2.4 / 3.8 / 8.3、5.0 / 7.2 / 12.6;60 則多畫 5 倍的組,步進仍遠低於一幀)。前一輪同頁量到 10x 展開幀間隔 max 33.6 ms
  (掉一幀)、這一輪沒有 —— 與 user 選 60 則時的說明「10x 展開時偶爾掉一幀」一致。console 0 錯誤

### 3. 既有分頁回歸(`dom_regression.mjs` → `result_dom_regression.json`)

舊頁(v1)與測試頁(v2)同樣操作:7 組 代號|日期(含 09-17、非群組 2305)+ 互動後 + 逐筆分頁 ← →,比分時 / K 線 SVG、頁頭、族群列、
圖例、左欄、逐筆、當日事件、回測、活潑日索引、分頁鈕、定義與規則(新頁扣掉新增的四條與「本頁只讀外掛檔 v2」一句);
重播分頁原有部分 8 組 × 15 拖曳時刻(每 5 個展開一次)比階梯、標籤、成交則、收到、現價、市價佇列、展開鈕、第幾則、兩張圖。
- **1,340 區塊 0 不符**(舊頁換成 15:36 現用頁複本後、懸掛縮排 CSS 改完後各跑一次,皆 0);定義與規則只多 4 條 + 「本頁只讀外掛檔 v2」
  一句;圖雜湊 9 種互不相同(比對非空);兩頁 console 0 錯誤

### 4. 截圖與 AI 截圖對照(`screens.mjs` → `result_screens.json`;sub-agent opus 逐張看 PNG)

截圖 8 張(`evidence/replay269-*.png`):2426 09:48:35 回到五檔 淺 / 深、2305 09:07:47 被擠出、2489 10:04:31 掃單吃檔、2305 09:05:01
清空後 淺 / 深、2426 1,100 寬(兩欄)、390 寬(單欄,`scrollWidth 390 == clientWidth 390`);8 張 console 0 錯誤。

**AI 截圖對照 9 / 9 PASS**(第二輪;第一輪 6 / 7 —— 深色那張沒有淡色行、驗不到「淡色讀得出來」是表述選錯圖,補拍 2305 深色;
另抓到中間欄長行折行後與下一行變動同一起點、數行容易數錯 → 變動行改懸掛縮排後重拍):
- SC-1 淺色三欄、標題與小字、頁頭「第 41,957 / 64,512 則」、中欄標亮組「⟳ 買 98.0 回到五檔 / 離開時 39 → 現在 120 / 離開期間成交 0 →
  淨掛 +81 / 離開 2 分 35 秒 /(一次掛進或分次堆積無法分辨)」、右欄標亮「09:48:35 | 98.5 | 2 | 內 | 吃 買1 −2」—— PASS
- SC-2 深色同內容,標亮組 / 列分得出(底 38,48,74 vs 24,27,34),一般行、分行、小字讀得出 —— PASS
- SC-3 2305 第 10,150 則「買 46.95 0 → 1 +1 掛單」一般色、「買 46.70 112 張被擠出五檔」淡色;46.70 無「掛單」;右欄無標亮 —— PASS
- SC-4 2489 第 11,609 則八行順序(被擠出淡色、⟳ 賣 39.20 分行);右欄「吃 賣五檔外 −56 / −34 / −80、賣5 −21 … 賣1 −7」—— PASS
- SC-5 2305 第 6,866 則、第 6,865 則只有淡色「五檔全空(…;不算撤單)」、第 6,864 則成交與首次進入 —— PASS
- SC-6 1,100 寬兩欄(階梯 | 成交明細,中欄在下方全寬),右緣無截字 —— PASS
- SC-7 390 寬單欄,無截字 —— PASS
- SC-8 深色 2305 清空後:淡色行讀得出且明顯較淡(字 126,134,151 vs 233,235,240)—— PASS
- SC-9 懸掛縮排:折行續行右移 11–12 px、下一條回原位、「回到五檔」分行仍右縮 17 px —— PASS

其他觀察(不改):淡色行對比淺色 3.1:1(標亮組 2.7:1)、深色 4.7:1,低於 12 px 字 AA 4.5:1 —— 沿用全頁既有 `--muted` 色;
價格階梯沒有標題列(#268 既有);箭頭在等寬 / 一般字型下兩種樣子。

### 5. 中間欄 60 則的覆蓋(`playback_window_coverage.py` → `result_playback_window_coverage_2026091{6,7}.txt`)

照頁面每幀(60 fps)推進、取收到時刻 ≤ t 的最後一則,整天播完數從沒出現在中間欄的則:

| 窗 | 09-16 1x / 2x / 5x / 10x | 09-17 1x / 2x / 5x / 10x |
|---|---|---|
| 12 則(原定) | 1.659% / 2.246% / 4.351% / 6.729% | 2.529% / 3.589% / 6.665% / 9.957% |
| **60 則(拍板)** | **0 / 0.005% / 0.070% / 0.260%** | **0 / 0.014% / 0.213% / 0.629%** |
| 跨則補齊 ≤ 200(沒選) | 0 / 0 / 0 / 0 | 0 / 0 / 0 / 0.003% |

09-17 較密集,10x 漏率是 09-16 的 2.4 倍(最多 6147 2.44%);1x 兩天都 0。定義與規則已寫明高速播放可能跨過 60 則以上、要逐則步進。

## review

two-axis round 1(Standards 11 條、Spec 5 條)原文與逐條處置:`code-review-round-1.json`。接手後完成模板側(P-02 / S-04 / S-10 / S-11),
並對 review 後的增量(repo 三個收修 commit + 兩個文件 commit + 模板增量 diff)做 main agent 機械快篩(`incremental_screen`),
沒有要再改的。AI 截圖對照另抓到中間欄折行起點與下一行相同、容易數錯行 → 變動行改懸掛縮排(模板 CSS,重拍重驗)。

## 切換與正式頁

補 09-17 回看頁的 session 16:3x 來訊息說 15:39 收工、之後不再動研究目錄與現用頁;user 16:5x 確認「現在切換」。

- `evidence/switch_live_269.py`(先 `--dry-run`,正式跑輸出 `evidence/result_switch_live.txt`,exit 0):現用模板雜湊 = 開工時
  (28ef9fb7…,期間沒人改過模板)→ 備份 `scripts/week0909/viewer_cdp_template.html.bak-20260917-pre269`、`viewer-cdp.html.bak-20260917-pre269`
  (皆為新檔,既有備份未動)→ 模板換成工作模板(96,292 bytes,CRLF)→ `viewer-cdp-book-269/<日>` 兩天各 80 檔蓋進 `viewer-cdp-book/<日>`
  並逐檔比雜湊 → `build_viewer_cdp.py` 重建 `viewer-cdp.html`(codes 81、extras 26、code-days 3,028、8.15 MB),**新頁 == 新模板 + blob**
- 正式資料夾 `viewer-cdp-book` 兩天 160 檔 = 暫存 v2 檔逐位元組相同,版本 2
- 正式頁語法:`syntax_check.py viewer-cdp.html` → SYNTAX-OK
- 正式頁既有分頁回歸(`RP_NEW_PAGE=viewer-cdp.html RP_OLD_PAGE=viewer-cdp.pre269.html dom_regression.mjs` → `result_dom_regression_live.json`):
  舊頁 = 切換時的頁面備份,由 `evidence/make_old_page_after_switch.py` 複製並把外掛檔改讀 `viewer-cdp-book.bak-20260917-pre269`
  (切換後 `viewer-cdp-book` 已是 v2,舊頁只認 v1,handoff 原寫法會讓舊頁載不進簿檔)。**1,340 區塊 0 不符**,兩頁 console 0 錯誤
- 正式頁對標準答案(`RP_NEW_PAGE=viewer-cdp.html verify_changes.mjs` → `result_verify_changes_live.json`):**594 則 0 不符**、
  竄改 3/3 抓出、console 0 錯誤
- 全過後刪掉測試頁 `viewer-cdp.269.html`、舊頁複本 `viewer-cdp.pre269.html`、暫存 `viewer-cdp-book-269/`;三份備份保留
  (`viewer_cdp_template.html.bak-20260917-pre269`、`viewer-cdp.html.bak-20260917-pre269`、`viewer-cdp-book.bak-20260917-pre269`)。
  evidence 腳本預設開的測試頁已不存在,之後重跑用 `RP_NEW_PAGE` / `RP_OLD_PAGE` 指到正式頁與備份頁
- **P-04 順序**:切換已完成 → 接著 artifacts commit、push / PR、立即 merge、主 tree `git pull`(主 tree 的 CLI 才是 v2);在那之前
  主 tree 跑 `book-replay` 仍產 v1,正式頁會拒讀
