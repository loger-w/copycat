# PR #282 事後審查收修 · 驗證紀錄(2026-09-19)

審查報告:`docs/superpowers/specs/pr-282-review.md`(+ 證據副檔 `.audit.md`;本批原樣搬入,
兩份 `**Report generation**` 同為 `sha256:2240f71a…`,未手改)。
分支 `fix/pr-282-review-followups`,fixed point = `9192668a`。

11 條 findings:**零 Must Fix、零 Should Fix**。八條收(#1–#8),三條 `no-op` 不收(#9 / #10 / #11)。

## 1. 唯一要 user 拍板的:#7 的行為半邊

#7 拆兩半:註解半邊是本 PR 造成的(把可能永久的狀態寫成暫態),行為半邊**不是本 PR 的迴歸**
(改前的 273 版同狀態也零回饋),而 D4 的拍板字面只涵蓋「無簿日」。

**user 2026-09-19 拍板:收。** 依據是先量後問 ——

- **6 組實例是現用頁面上真的有的**:解 `viewer-cdp.html` payload 與 `viewer-cdp-book/<日>/` 目錄
  逐日比對,`page − file` = `3630` / `4977`,三天各兩檔 = 6 組(`evidence/viewer_browser_checks.md`)。
- **`rpWait` 真的等於「還在飛」**:`rpSettle`(`:610`)在成功與失敗都 `rpWait.delete(key)`,
  `loadReplay`(`:614-626`)只在送出 script 前 `set`,四條終局路徑(`__bk` 的 then / catch、
  `s.onerror`、`s.onload` 且沒以這個 key 呼叫 `__bk`)全部經過 `rpSettle`。
  收修後這件事寫在述詞 `rpInFlight`(`:611-612`)旁邊,不再是 `rpKey` 的註解。
- **四個狀態全部涵蓋**:無簿日 / 載入中 / 沒這一檔 / 解不開,四格都實測過(§6)。

## 2. 八條的做法

| # | 檔 | 做法 |
|---|---|---|
| 1 | 回看頁 `:837` | 面板文案由「它落在有簿的區間內(A–B,目前 n 天)」改成不下含入結論的「它不早於最早有簿的一天(A;目前有簿 n 天,最後一天 B)」—— 中間缺與尾巴缺兩格都為真 |
| 2 | `docs/next-time.md` + `check_trial.py:11` | 同一個錯數字的兩份都改:9 / 6 處 → **12 處**;另補「兩種 grep 形狀各掃一次」與「`parents[N]` 的 N=4 只適用 `evidence/` 子目錄,slug 目錄下是 N=3」。**站點本身不收**(要收要 12 處一次收) |
| 3 | `.claude/bug/pr-281-review-followups/verification.md:92` | 「105 行」→「`wc -l` 全檔 114 行 = 檔頭 `---`/`+++` 2 + hunk 標頭 9 + 內容行 103:context 65 + 加 32 + 減 6」。**第一版寫的是「內容行 105 + hunk 標頭 9」,照抄了報告 #3 自己的誤算**(把 `+++` / `---` 各算成一筆加 / 減);two-axis Std-4 抓到,已改成實測分解,三個數字都講明 |
| 4 | `check_trial.py:5` | 「收修三件」→「兩件」 |
| 5 | `check_trial.py:35-46 / :76` | 早退拆成三句:目錄空 / **代號沒對上**(印目錄裡本來有幾支)/ 有檔但一則都沒有。過濾前的清單先接成 `picked` 才印得出「本來有幾支」 |
| 6 | `make_pr281_check_pages.py:53-57` | 在 `rmtree` 前加一道閘 `if TMP_BOOKDIR == "viewer-cdp-book" or not TMP_BOOKDIR.endswith("-pr281"): raise SystemExit(…)`,把 docstring 的承諾釘成機器可驗(第一版用 `assert`,two-axis Std-5 指出 `python -O` 會整行拿掉,已改) |
| 7 | 回看頁 `:611-612` + `:936-938` | 註解改成「載入中 vs 載入失敗」兩種分開講;行為擴成 `!rpHasBook() \|\| !rpInFlight(state.code, state.date)` 才換日(述詞在 loader 旁邊,`rpKey` 不再伸手讀 `rpWait`、也不再自己組鍵 —— two-axis Std-1 / Std-2 收修) |
| 8 | 回看頁 `:90-96` | 註解三個子主張全部更正,並**不再寫死總數**(原寫「共 20 行」,實測 28 行 / 39 次 —— 寫死必漂);枚舉補上「定義與規則」那幾條 li 並明寫「這串不是全集、一律先 grep 全檔」(two-axis Std-3 / Spec-a2 收修:原改寫仍漏了 `:214` 橫條與 `:222` 成交明細兩條 li) |

### 沒有照抄建議的一處(#6)

報告順帶建議 `if tmp.parent.exists(): rmtree(...)` 改成 `rmtree(..., ignore_errors=True)`。**沒做**:
那會把權限錯誤吞掉,再由下一行 `tmp.mkdir(parents=True)` 拋出對不上原因的 `FileExistsError`;
現行的「先檢查再刪」失敗得比較大聲,也不違反鐵則 E(不吞錯誤)。

報告建議的另一半(用 `assert` 把承諾釘成機器可驗)**做了,但換了寫法** —— two-axis Std-5 指出
`assert` 在 `python -O` 下會被編譯器整行拿掉,而這道閘守的是整個 `.claude/**` 證據語料庫裡
唯一一處破壞性呼叫,拿不得;改成 `if … raise SystemExit(…)`。

## 3. 三條不收的理由(不是漏做)

- **#9 REFUTED**:`code-review-round-1.json` 寫的「1,002 行」在**寫下的時點是對的**,差的 4 行正是
  同一份 json 的 Std-4 / Std-5 收修加進去的 —— 照收會把凍結紀錄改成與它評的對象對不上。
- **#10** `rpTabState` 與 `renderReplay` 的三態順序目前一致、無現存 bug,判斷題且不划算。
- **#11 REFUTED**:`p.trial || []` 先於 `Array.isArray` 是 v3 往下相容的刻意寫法,產生端不可能吐 falsy 非陣列。

## 4. 自動化 gate(worktree 實跑,主樹 venv)

| 指令 | 結果 | exit |
|---|---|---|
| `python -m pytest -q` | `3679 passed, 3 skipped, 2 warnings in 229.07s` | 0 |
| `python -m ruff check copycat tests` | `All checks passed!` | 0 |
| `python -m pyright` | `0 errors, 0 warnings, 0 informations` | 0 |
| `python -m copycat validate --run-four C:/side-project/copycat/out/four_tigers --run-five C:/side-project/copycat/out/five_tigers` | `42/42 PASS` | 0 |

直譯器一律 `C:/side-project/copycat/.venv/Scripts/python`(worktree 沒有自己的 venv;
`pyproject` 的 `pythonpath=["."]` 讓 worktree 的 `copycat` 蓋過 editable `.pth` 的主 tree)。
`validate` 的 `--run-*` 指主 tree 的 `out/`(replay 產物 gitignored,worktree 沒有),**程式碼仍是 worktree 的**。

**前端 gate N-A**:對 `copycat/` `frontend/` `tests/` 三個路徑下 diff,回**零行** —— 改動全落在
`.claude/` 與 `docs/`。所以以上四條全是「沒打壞既有」的回歸,不是本批新增的覆蓋;表內數字是
two-axis 收修**之後**重跑的(收修一樣只動 `.claude/**` 與 `docs/`,仍不在這四條的涵蓋內,
但還是重跑一次而不是沿用前一次的綠)。

## 5. 腳本層實跑

- `evidence/check_trial_paths.txt` —— `check_trial.py` 四條路徑:正常(80 檔 / 390 段 / 7,405 則 /
  0.26% / 盤中段 311 筆,與歸檔數字逐字相同)、**代號沒對上**(exit 2,印「在 … 的 80 支裡一支都沒對上」)、
  目錄不存在(exit 2,印「0 檔 —— 目錄空或日期打錯」)、指定兩個代號(exit 2 → 0,2 檔 / 3 段)。
- `evidence/rmtree_guard_truth_table.{py,txt}` —— **直接把原始碼那道閘抓出來跑真值表**
  (不碰任何真目錄):現值 `viewer-cdp-book-pr281` PASS;`viewer-cdp-book` / `viewer-cdp-book-pr282` /
  `viewer-cdp-bookpr281` / `""` 四種全部 `SystemExit` 擋住。腳本同時印出那道閘的**下一行**是
  `if tmp.parent.exists():`,證明護欄確實擋在 `rmtree` 之前。
  (第一版用 `assert`,two-axis Std-5 指出 `python -O` 會把它整行拿掉、而它守的是「別刪到真資料夾」,
  已改成 `if … raise SystemExit(…)`;真值表依新的閘重跑,五格結果不變。)
- `make_pr281_check_pages.py` 加了那道閘之後重跑兩次(assert 版一次、SystemExit 版一次),
  兩份暫用頁都照常產出、真的 `viewer-cdp-book/2026-09-16` 仍有 80 支檔。

## 6. 真環境驗證(本地 http server + Chrome)

全文見 `evidence/viewer_browser_checks.md`,截圖 `evidence/pr282-01-d3-after-max.jpg`(#1 界後那格)
與 `evidence/pr282-07-no-such-file.jpg`(#7 的「換一檔或換一天」畫面)。摘要:

- **#1** 四格全 PASS(界前 / 有簿 ×2 / **界後**),另在上一批的「界內缺一天」暫用頁回歸一次也 PASS。
- **#7** 四格全 PASS:沒這一檔 → 換日(← → 各一次);有外掛檔 → 日期不動、則號 1 → 3;
  無簿日 → 換日;**載入中 → 不換日**(同一個 JS task 內點分頁 + 送鍵,script 為 async 載入,
  必然落在「在飛」那一格;載完 idx 仍 1 = 鍵被正確吞掉)。
- **#8** 註解的事實主張逐條實測:`getComputedStyle(el,"::after").content` 回傳 `"集合競價"`、
  同一節點的 `innerHTML` / `textContent` 皆 `false`。
- `build_viewer_cdp.py` 重建後與重建前比對:**解壓後 payload 逐位元組相同**(29,950,529 bytes),
  只有 gzip 檔頭 mtime 不同 —— 資料層零改動。

回看頁改動的全文副本與 diff:`viewer_cdp_template.pr282.html` / `.pr282.diff`
(自 #273 出貨狀態起,`wc -l` 全檔 125 行 = 檔頭 `---`/`+++` 2 + hunk 標頭 9 + 內容行 114:context 69 + 加 39 + 減 6
—— 三個數字的口徑同 §2 的 #3,別再只報一個)。
**本批自己的 before/after** 要看的是它與 `.claude/bug/pr-281-review-followups/viewer_cdp_template.pr281.html`
的差(**4 個 hunk**:CSS 註解、面板文案、`rpInFlight` 述詞、`rpKey`)。
現用檔備份 `viewer_cdp_template.html.bak-20260919-pr282-followups`;`viewer-cdp.html` 重建前另存 `viewer-cdp.html.bak-20260919-pre282`。

## 7. 本批自己的 two-axis review(round 1,fixed point = `9192668a`)

兩個 sub-agent 平行(皆顯式帶 `model: opus`),findings 原文與逐條處置見 `code-review-round-1.json`。
**Standards 6 條(零硬違規,全是判斷題)+ Spec 2 條**;Spec 軸另外反向確認了三處(#1 兩格皆真、
#5 真的三分流、#7 的 `rpWait` ⟺ 在飛)並判定 **scope creep 無**。

| # | 處置 |
|---|---|
| Std-1 Feature Envy | **收** —— `rpKey` 不該伸手讀 loader 的 `rpWait`,抽成 `rpInFlight(code, date)` 放在 `rpSettle` 旁邊 |
| Std-2 手搓鍵第 4 處 | **收(新增的那一處)** —— 隨 Std-1 消失;既有三處不收,記 `next-time` |
| Std-3 Shotgun Surgery | **部分收** —— 枚舉改寫成「不是全集、一律先 grep」;收斂成單一產生點記 `next-time`(CSS `content` 那份收不進 JS) |
| **Std-4 假陳述未除淨** | **收 —— 這是本批唯一的實錯**:#3 的新句把 `---`/`+++` 兩行檔頭算進「內容行」。實測 114 = 檔頭 2 + hunk 9 + 內容行 103(context 65 + 加 32 + 減 6)。**根因是報告 #3 原文自己的算式就錯了**(「加 33 / 減 7」把 `+++` / `---` 各算成一筆),本批照抄 —— 已改成實測分解 |
| Std-5 `assert` 在 `-O` 下消失 | **收** —— 守「別刪到真資料夾」的閘改成 `if … raise SystemExit(…)`,真值表重跑五格全擋 |
| Std-6 commit 混性質 | **反駁不收** —— 引用的全域鐵則 C 是**測試紀律**不是 commit 紀律;鐵則 B 要求的「三類不混」指 🔴 行為 / 🟢 新功能 / 🔵 純重構,docstring 修正不在其中,而「純 docstring 一律 chore」講的是**整顆都是文件**的 commit(`chore(docs)` 那顆正是)。拆開會產生「只動一行 docstring、同檔行為改在隔壁 commit」的紀錄,考古更差;前一批 `b33bcaf8 fix(evidence)` 同款前例 |
| Spec-a1 dom_regression 斷言 | **維持延後** —— reviewer 自己實地核過理由為真(三份 mjs 都是各批凍結副本),記 `next-time` |
| Spec-a2 枚舉仍漏兩處 | **收**(與 Std-3 同一處改動) |
| Spec-流程 `evidence/` 還 untracked | **收** —— artifacts commit 含整個 `evidence/` |

**收修動到了 #7 的判斷路徑**(`rpWait.has(k)` → `rpInFlight(...)`),所以回看頁四格行為 + #1 四格 +
#8 兩條事實主張**全部重跑一次**,見 `evidence/viewer_browser_checks.md` 的「第二輪」;
`rmtree` 真值表也依新的閘重跑。

## 8. 沒做的部分

- **prod server 不需重啟**:本批零 runtime 改動(`copycat/` 一個檔都沒動)。
- `sys.path` 那 12 個硬編 worktree 站點**仍未收**,留在 `docs/next-time.md`(要收要 12 處一次收)。
- 回看頁的兩組「同一件事散在多處字面」(「集合競價」≥6 個顯示點、`code+"|"+date` 三處手搓)
  **不收**:動了要全頁重測,不該夾在 Nice to Have 批裡 —— 已記 `docs/next-time.md`
  (two-axis Std-3 / Std-2;本批新增的第四個手搓點已隨 `rpInFlight` 消失,沒有把情況變糟)。
- #8 順帶建議的「在 DOM 回歸腳本加一條 `getComputedStyle` 斷言」**未收**:`dom_regression.mjs` /
  `pp_common.mjs` 是每批各複製一份、釘在該批 before/after 兩頁的凍結證據,沒有活靶可以加 ——
  已記 `docs/next-time.md`,收法是下次寫回看頁 DOM 回歸腳本時一併存進快照。
- repo 外留下的暫用頁(`viewer-cdp-pr282-d3max.html`,與上一批的 `viewer-cdp-pr281-*.html`)沒清 ——
  都可由 `make_pr28*_check_pages.py` 重產,沿上一批前例保留。
