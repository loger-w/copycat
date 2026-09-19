# PR #281 事後審查收修 · 驗證紀錄(2026-09-19)

分支 `fix/pr-281-review-followups`(worktree)。審查報告 25 條,其中 4 條 `ask-user`、10 條 `auto-fix`、
11 條 `no-op`(已附反證,不收)。user 2026-09-19 凌晨逐條拍板。報告雙檔隨本批移進
`docs/superpowers/specs/pr-281-review{,.audit}.md`。

**runtime 零改動**:`copycat/` 只動模組說明 docstring,引擎行為一行沒變 → **prod server 不需重啟**。
行為有變的只有 repo 外的回看頁(D3 / D4 / #10)。

## 1. 四條 ask-user 的拍板與做法

| 拍板 | 做法 |
|---|---|
| **D1(#1)**「段的界」分來源寫清楚 + 提醒 #271 | 原句把 `trial` / `auction` 講成互斥。實測**不是全錯,是漏了第三種來源**:收盤集合競價與處置股分盤撮出來的成交,狀態確實已回正常盤(三天 1,169 筆 `auction` 零落在段內,含整天推試撮簿的處置股 3055 於 09-16 的 130 段 / 130 筆);但**盤中暫緩撮合的延遲成交**送來時狀態可能還停在試撮(7772 於 09-16 / 09-17),那種則就在段內。三處同步改成分來源陳述,並在模組說明加「兩旗標不互斥,#271 不得寫成 `if auction … elif trial …`」 |
| **D2(#14)** 保留 fixture 形狀 + 補 `auction` 斷言 | docstring 改成「成交那一列取自 7772 實錄;**前一則試撮簿是構造的**(實錄裡那筆是當天第一則)」,並加 `assert frames[1].auction is True` —— 這支測試因此變成 D1 新說法的反例守門 |
| **D3(#9)** 加第三種文案,界 = `min(bookdays)` | 界抽成 `rpShouldHaveBook()` 單一來源,`renderReplay` 面板與分頁 tooltip 共用(tooltip 是同一句假陳述的第二處,報告沒列到) |
| **D4(#11)** 無簿日 ← → 直接換日 | `rpKey`:`!RP` 時,`!rpHasBook()` → `stepDay(±1)`;有簿但還在載入 → 不換日(免得手一快跳走) |

## 2. 十條 auto-fix

| # | 檔案 | 做法 |
|---|---|---|
| 2 | `docs/next-time.md:36` | v3 → v4、「回看頁讀 v2 / v3」→「v2 / v3 / v4」。**這次全庫掃**(上次只掃 `copycat/` 才漏掉它):活著的檔只有這一處,其餘全是歸檔產物(`.claude/**/evidence`、`docs/superpowers/specs/pr-279-*`、`graphify-out/`),不回頭改 |
| 4 | `evidence/payload_diff.py:41` | `SystemExit(1 if (diff or removed or changed) else 0)`;`added` 刻意不進 gate |
| 5 | 同上 `:1` | docstring「逐位元組」→「語意逐鍵」(兩邊都先經 `payload_dump.py` 正規化);刪死變數 `tot` |
| 6 | `evidence/check_trial.py:50` | 樣本改印「列 n / 共 m 筆」(修前剛好列滿 8 筆,看不出截掉 97%);`total_msgs == 0` 早退免 ZeroDivisionError。**`sys.path` 寫死已刪 worktree 那條沒收** —— 那是 review #17、處置 `no-op`(見 §8 two-axis Spec-b) |
| 7 | `evidence/close_pile.py` | 拿掉 13:25 閘與「只讀簿 parquet」重寫重跑。**docstring 的數字沒有改**(reviewer 的方向是對的:缺的是證據涵蓋面不是數字) |
| 8 | 同上 | `close_pile` / `no_close` / `merged_run` 三支的 stdout 歸檔成 `.txt`(簿 parquet 只留 120 交易日,過期後這些數字永久不可重驗) |
| 10 | 回看頁 `rpBuild` | `if(!Array.isArray(trialFlat) \|\| trialFlat.length % 2) bad(…)` |
| 13 | 回看頁 CSS / 說明 | 說明列「每則**右上**」→「每則**標頭末端**」(版面不動 —— AC1 截圖已驗過);CSS `::after` 旁加註它是「集合競價」的第 4 份字面、DOM 腳本抓不到 |
| 15 | `tests/test_book_replay.py:1378` | 刪 `assert wire["v"] == 4`(golden 字面測試已釘) |
| 16 | `verification.md:72` | 「完全相同」為假 → 改同 CLAUDE.md 口徑 + 逐檔加總的實測位元組表 |

**順帶(同 #2 的漏網類型)**:回看頁三處註解仍指向已改名的章節「外掛檔 v2」→ v4(`RP_CHG_WIDTH`、
`rpChangeLines` ×2)。與 #273 round-1 收修 A-1 修掉的三處 Python docstring 是同一個缺陷類。

## 3. 量測:#7 拿掉兩個窄化後的數字(`evidence/close_pile.txt`)

| 日 | 段內列(成交 + 簿) | 全段單格最大 | 13:25 前段內最大 |
|---|---|---|---|
| 2026-09-16 | 7,405 | **47,033** 5314 賣一 13:29:43 | 37,845 5314 賣一 09:00:09 |
| 2026-09-17 | 7,413 | **27,806** 5314 賣一 13:29:53 | 8,140 2489 賣一 09:06:29 |
| 2026-09-18 | 10,957 | **29,675** 5314 買一 13:27:53 | 29,300 2303 賣三 09:06:18 |

粗體三個數字與 `copycat/book_replay.py` 模組說明逐字相同 → **docstring 的數字本來就是全段最大值,不必改**。
09-18 的裕度只有 **375 張**(29,675 vs 29,300),所以把「13:25 前的最大」一起留在輸出裡。

## 4. D1 的實測依據(本 session 自己重跑,非轉述 reviewer)

- 三天 246 支正式外掛檔全掃:`auction` 1,169 筆、段內則 25,775、**重疊 0**。
- 但段內的**成交**則三天只有 **2 筆**(7772 於 09-16、09-17),原始 parquet 覆核:
  09-16 成交列 375,387 筆中帶試撮狀態 1 筆、09-17 477,256 筆中 1 筆、09-18 502,539 筆中 0 筆。
- 那 2 筆都恰好是當天第一則(7772 全天只有 3 則訊息),沒有前一則可比 → `auction` 為 False。
  暫緩撮合期間每分鐘約 10 則試撮簿,延遲成交夾在中間到達就會兩旗標齊發 —— 所以零重疊是樣本薄,
  不是結構保證,**不能加守門**(加了會在達錢合法送得出來的形狀上炸掉 `book-replay`)。
- 7772 耀穎**不是處置股**(處置名單 2026-06-01~09-17 含上市櫃,它一次都沒出現);那兩筆的來源是
  **盤中暫緩撮合**:09-16 成交 11:40:29 / 收到 11:42:27,09-17 成交 12:34:36 / 收到 12:36:22。

## 5. 自動化 gate(worktree 實跑,主樹 venv)

- `pytest -q`:**3,679 passed / 3 skipped**(238.94 s;`tests/test_book_replay.py` 118 條)
- `ruff check copycat tests`:All checks passed
- `pyright`:0 errors, 0 warnings, 0 informations
- `copycat validate`(`--run-four` / `--run-five` 指主樹 `out/`):**42/42 PASS**
- 回看頁 inline JS:`node --check` rc=0
- 證據腳本八支:`ast.parse` 全 OK

**突變證據(D2 的新斷言是否真的擋得住東西)**:在 `_auction_match` 加一條
`row.trade_status != _TRIAL_STATUS`(= 舊 docstring 宣稱的「兩旗標互斥」),
`test_a_late_delayed_match_trade_carries_the_trial_flag_itself` 立刻紅在
`assert frames[1].auction is True` → `AssertionError: assert False is True`;
還原後 `tests/test_book_replay.py` 118 passed。也就是說,這條斷言正好釘住 D1 校正掉的那個宣稱。

## 6. 真環境驗證(本地 http server + Chrome,`viewer-cdp.html` 已重建)

驗證用暫用頁由 `make_pr281_check_pages.py` 產生(不動真的 `viewer-cdp-book/`、不覆寫 `viewer-cdp.html`;
沿 `make_empty_bookdays.py` 的作法),驗完刪除。

| 驗 | 做法 | 結果 |
|---|---|---|
| **D3** 界內缺一天 | `bookdays` 拿掉 2026-09-17 | 09-17 → 「應該有五檔簿,但這一頁沒掃到 —— 它落在有簿的區間內(2026-09-16–2026-09-18,目前 2 天)」+ 補跑指令 **PASS** |
| **D3** 界前照舊 | 同一頁選 2026-09-15 | 「沒有五檔簿 —— 不是故障 … 達錢歷史 TICKS … 不含五檔」**PASS** |
| **D3** tooltip 三態 | 分頁鈕 `title` | 09-15 舊句 / 09-17 新句 / 09-16 無 tooltip **PASS** |
| **D4** 無簿日換日 | 09-15、重播分頁開著,送 ArrowLeft / ArrowRight | 09-15 → 09-14 → 09-15 **PASS** |
| **D4** 有簿日不換日 | 09-16,送 ArrowRight | 日期不動、則號 1 → 2 **PASS**(回歸) |
| **#10** `trial` 非陣列 | 暫用 `bookdir` 放一支 `trial` 改成物件的 1303.js | 「簿重播檔解不開:外掛檔格式不符:trial(集合競價段)**不是陣列(object)**」**PASS**(修前會靜默當成沒有段;文案在 two-axis Std-5 收修後才由「格數 undefined」改成講型別) |
| **#10** 對照組 | 同資料夾未動過的 1312.js | 照常播放、段標註在 **PASS** |
| **#13** 說明文字 | 「定義與規則」全文 | 已無「右上」**PASS** |
| **D1** 說明文字 | 同上「段的界」那段 | 已是分來源陳述、含「兩個標記各讀各的、不互斥」**PASS** |
| 回歸 | 正式 `bookdays` 下 09-16 開播 | 15,073 則、段標註「集合競價(盤中暫緩撮合 / 處置股分盤)」**PASS** |

回看頁改動的全文副本與 diff:`viewer_cdp_template.pr281.html` / `.diff`(自 #273 出貨狀態起,`wc -l` 全檔 114 行 = 內容行 105 + hunk 標頭 9)。
現用檔備份 `viewer_cdp_template.html.bak-20260919-pr281-followups`;`viewer-cdp.html` 已以
`build_viewer_cdp.py` 重建(codes 91 / code-days 3,113 / html 8.4 MB)。

## 7. 本批自己的 two-axis review(round 1,fixed point = `85ddb150`)

兩個 sub-agent 平行(model `opus`),findings 原文與逐條處置見 `code-review-round-1.json`。
**Standards 6 條 + Spec 3 條實錯,全部 CONFIRMED、全部收,零反駁。**

| 軸 | 條 | 收法 |
|---|---|---|
| Std-H1(硬違規) | commit type `docs` 不在 CLAUDE.md §6 允許集合 | 自查 250 筆歷史:只改文件的 55 筆 **全部**是 `chore`、零 `fix` 零 `docs` → 改寫成 `chore(docs)`;純 docstring 的 `fix(book-replay)` 一併改 `chore(book-replay)` |
| Std-1 / Std-2 | `close_pile.py` 五元 tuple 靠位置編碼、空字串當哨兵 | 改 `class Peak(NamedTuple)` + `SOURCES` 一張表;歸檔的 `.txt` 因此自述(#8 的用意就是「120 交易日後還讀得懂」)。重跑數字不變 |
| Std-3 | `payload_diff.py` 宣稱「舊交易日」但 gate 的 `d` 是 catch-all | **只改註解不改 gate** —— gate 那一行維持報告 #4 逐字建議,超出建議自己發明判斷正是 Spec-b 抓到的那種越界 |
| Std-4 / Std-5 | 回看頁「最早有簿日」算兩次;`trial` 非陣列時把型別錯講成格數錯 | hoist `BOOK_SORTED` / `BOOK_FROM`;錯誤文案拆兩條 |
| **Spec-b** | **收了報告明說 `no-op` 的 #17**(三支 `sys.path`) | 報告原文「要收就整批收,不該只挑本 PR 這三支」,user 拍板也沒授權 → **三支全部還原**(`no_close.py` / `merged_run.py` 對 HEAD 的差分歸零),改記 `docs/next-time.md` 待 9 處整批收 |
| **Spec-c** | **我寫的辯護理由是假的** | 「不改就跑不起來」為假:venv 是 editable 安裝,死路徑被靜默略過、fallback 到主 tree 同一份 code。實證:還原後重跑 `check_trial.py 2026-09-16`,輸出與歸檔 `.txt` **逐位元組相同** |
| Spec-a | `.claude/feat/…/verification.md:48` 仍寫「右上」 | 同 #13 的假陳述,一併改成「標頭末端」 |

收修後全部重跑:pytest / ruff / pyright / validate 全綠(數字同 §5)、回看頁 `node --check` rc=0、
`close_pile.py` 重跑數字不變、#10 與 D3 / D4 的瀏覽器驗證重做一次全 PASS。

## 8. 沒做的部分

- **報告裡「auto-fix 11 條」的算錯數字沒有改**:兩份報告有 hash 對應、不可手改,要改得重建 draft
  再跑 projection。user 2026-09-19 拍板「入 `docs/`,不重建,勘誤寫在 PR」——
  **正確是 10 條**(canonical UID 記錄也是 auto-fix 10 / ask-user 4 / no-op 11)。
- **11 條 `no-op` 未收**(報告已附反證;其中 #23 / #24 為 REFUTED,照收反而會在已有明文豁免處加防禦碼)。一度誤收了 #17,已於 two-axis round 1 還原,這個數字重新成立。
- AC2「集合競價段不產生厚檔事件」仍延後在 **#271**(user 2026-09-18 拍板),閘與兩條義務已備好。
