# PR #282 Code Review 比較報告 · SHA 890aeaa1

**Report projection schema**: 1

**PR**: [loger-w/copycat#282](https://github.com/loger-w/copycat/pull/282)
**標題**: fix(book-replay): PR #281 事後審查收修批 —— 四條拍板 + 十條 auto-fix(review #1 / #2 / #4–#11 / #13–#16)
**作者**: loger-w
**分支**: `fix/pr-281-review-followups` → `master`(狀態 MERGED)
**變更**: 21 檔案, +2731 / -42
**審查日期**: 2026-09-19
**Review input basis**: source repo `R_kgDOTsITBg`(loger-w/copycat)+ source SHA `890aeaa156dcd65335c87e60009f84b5ae667bed`;destination repo `R_kgDOTsITBg` + destination SHA `85ddb1502c3ec2e3c2c9a465d4c95b8f26f0daa8`;`input_binding: verified`(分支已隨 merge 刪除,改自 `refs/pull/282/head` 取得,逐字等於 `headRefOid`;review worktree HEAD 同值)
**Review continuity**: `source_continuity=CURRENT`(PR 已 MERGED,head 不會再動);`base_changed=true`(`origin/master` 已前進到 `9192668a`,原因是本 PR 自己 merge + 隨後的 graphify commit);`review_context_changed=false`(diff 釘在 `baseRefOid` 這顆 commit 物件本身,不使用移動中的 branch ref,所審 diff 逐字等於 PR 的 diff)
**worktree**: `C:\side-project\copycat\.worktrees\review-pr-282`
**worktree HEAD**: `890aeaa156dcd65335c87e60009f84b5ae667bed`
**審查工具**: CC(context-aware reviewer agents,chunked)+ 獨立同軸踢館複查。**Codex 中性 / Codex 對抗 / Gemini Flash / Gemini Pro 四軸全部 N-A**(本機未安裝 `codex` 與 `agy` CLI),故本輪實為 **CC 單軸 chunked review**。
**Reviewer model 記錄規則**: 上一行只描述工具組合;固定模型 reviewer 不套用「繼承 main session 模型」,實際身分以下一行為準。
**Reviewer models**: orchestrator = Opus 5 (1M context);primary reviewer = `code-reviewer` × 2 chunk 實例,dispatch 時顯式帶 `model: opus`;語言軸 = `python-reviewer` + `typescript-reviewer`,各顯式帶 `model: opus`;複查 pass = `code-reviewer`,顯式帶 `model: opus`;spec-compliance-reviewer requested = N-A / observed = UNAVAILABLE / effort = N-A / tools = N-A(gate SKIPPED,未派);Codex = N-A;Gemini = N-A
**覆蓋 (ENH-A)**: |F|=21 → covered 6 / no-issues 13 / skipped 2 / **missed 0**(chunked: 是,DIFF_LINES 2773 > 800 門檻 → 2 chunks,union 逐檔等於 F)。**skipped 的 2 檔逐一列名**:`docs/superpowers/specs/pr-281-review.md` 與 `docs/superpowers/specs/pr-281-review.audit.md` —— 兩份都是**前一輪 review 的 projection 產生檔**(帶 `Report generation` hash 與 25 個 canonical `finding_uid`),依使用者拍板「入 `docs/`、不重建、不可手改」原樣搬入,逐行內容不在本輪審查範圍;chunk 2 仍對它們做了完整性交叉檢查(兩份 UID 集合相等、六個 header 逐字相同、Action 統計 auto-fix 10 / ask-user 4 / no-op 11)。
**定位 (ENH-B)**: anchored exact 10 / ambiguous 1 / **FAILED 0**(ambiguous 那條 = F-05,「目錄空或日期打錯」同時出現在 docstring `:8` 與 print `:67`,依 Step 4.6 規則取 reviewer 回報行所在的 `:67`)
**React-doctor (2.97)**: N-A(非 React PR — F 內無 `.jsx` / `.tsx`)
**blast radius (2.9)**: **N-A** —— 腳本有跑、回空輸出(`sem` CLI 本機未安裝;`sem-pr-blast-radius.sh "$REVIEW_ROOT" 85ddb150` 回 rc=0、零行)。這是「跑了沒結果」不是「沒跑」,也不是噪音判定
**Formal spec traceability (2.65)**: SKIPPED (`C4_NO_IMPLEMENTATION_BINDING_CLAUSE`)
**Codex preset (2.98)**: N-A(`codex` CLI 未安裝,未詢問 —— 五個 preset 的答案都不可執行)
**Gemini 軸 (2.96)**: N-A(`agy` CLI 未安裝,未詢問 —— 兩個選項的答案都不可執行)
**Quota**: 未取 dashboard snapshot(Gemini 軸未啟用)
**審查軸狀態**: primary reviewer PASS(`code-reviewer` × 2 chunks,逐檔 accounting 齊全、union = F);語言軸 `python-reviewer` PASS;語言軸 `typescript-reviewer` PASS;security-reviewer N-A;spec-compliance-reviewer N-A;Codex 中性 N-A;Codex 對抗 N-A;Gemini Flash N-A;Gemini Pro N-A;Step 4.1 N-A(無非 CC 軸可驗);Step 4.2 以獨立同軸踢館 pass 替代執行(PASS,11 條全覆蓋、2 條 REFUTED);Step 4.3a N-A;Step 4.3b PASS —— 逐軸理由見「審查軸狀態明細」節,無 PENDING

**Report generation**: sha256:2240f71a845bf3c197bd854b81c43f89f021b5871a87917753cf1dea9631fb32

---

## 審查軸狀態明細

- **primary reviewer**(`code-reviewer` × 2 chunks)— **PASS**。chunk 1 = 11 檔、chunk 2 = 10 檔,逐檔 accounting 21/21,union 逐檔等於 F,`MISSED = 0`,未觸發 Step 4.5 的 repair re-dispatch。
- **語言軸 `python-reviewer`** — **PASS**。覆蓋 6 支 `.py`。非 primary,不計入 coverage 算術。
- **語言軸 `typescript-reviewer`** — **PASS**。覆蓋回看頁 `.diff`(114 行,真正的改動)+ `.html`(1,006 行快照,查上下文)。非 primary,不計入 coverage 算術。
  - **路由說明**:副檔名計數為 `.html` 1,006 / `.py` 222,但 `.html` 不在 primary 路由表的任一列(表列 `.ts/.tsx/.js/.jsx/.mjs/.cjs` → typescript、`.py` → python、其餘 / 無 >40% 主導 → `code-reviewer`)。本 PR 跨 Python 與瀏覽器 JS 兩面且 `.html` 那 1,006 行是**全文快照**(其改動只有 114 行的 `.diff`),故 primary 取通用 `code-reviewer`,另加兩個語言軸補深度。這是對路由表「mixed / none of above」那一列的套用,不是繞過。
- **`security-reviewer`** — **N-A**,四項觸發條件逐一查證皆 0 命中:
  - 路徑型(`auth/` / `security/` / `crypto/` / `middleware/auth*` / `middleware/csrf*` / `oauth/`)對 F 的 21 個路徑 → 0 命中
  - 新增 env 讀取(`API_KEY|TOKEN|SECRET|PASSWORD|CREDENTIAL`)→ 0 命中(diff 內零 `os.environ` / `getenv` 新增)
  - 新增處理 request body / query / cookie / form / 檔案上傳的 code → 0(本 PR 無網路與伺服器路徑)
  - session / cookie / JWT / 權限 / RBAC 改動 → 0
- **`spec-compliance-reviewer`** — **N-A**,Step 2.65 gate 判 `SKIPPED`,理由見「Spec 依據」節。
- **Codex 中性 / Codex 對抗** — **N-A**,`command -v codex` 不存在。未詢問 Step 2.98 的 preset(五個答案都不可執行)。
- **Gemini Flash / Gemini Pro** — **N-A**,`command -v agy` 不存在。未詢問 Step 2.96 的 opt-in(兩個答案都不可執行)。
- **Step 4.1(CC 驗非 CC 軸)** — **N-A**,無非 CC 軸產生 finding。
- **Step 4.2(Codex 驗 CC first-pass)** — **以獨立同軸踢館 pass 替代執行,PASS**。單軸下 CC findings 本來無人複查,故另派一個未參與 first-pass 的 `code-reviewer`(`model: opus`)做踢館式複查,並在 prompt 內明白告知「PR 作者 = 派你出來的 main session 本人,標『main session 已驗』的證據由當事人產生,不要照單全收」。11 條全覆蓋、**2 條 REFUTED**、4 條 PARTIAL、5 條 CONFIRMED,並對 main session 自己的結論提出 4 項更正(全部經 main session 重驗後採納,見「複查對 main session 的更正」節)。**這仍是同軸,不是跨軸** —— 兩邊同為 Opus,共同盲點不會被這道 pass 抓到。
- **Step 4.3a(consensus baseline check)** — **N-A**,無跨軸 consensus(單軸)。本輪的「兩個 reviewer 同時提出」(F-01、F-06 類)屬同軸 corroboration,已在各條備註標明。
- **Step 4.3b(lone finding 判斷)** — **PASS**,見「lone finding 判斷」節。

## Spec 依據

本 PR 是 **PR #281 事後審查的收修批**,spec = 兩件東西,都在本 PR 的 diff 內:

1. `docs/superpowers/specs/pr-281-review.md`(+ `.audit.md` 證據副檔)—— 上一輪 review 的 25 條 finding 與其 `Action` 欄。**確定性核對**:表格 Action 欄與 canonical UID 記錄兩邊獨立統計皆為 **auto-fix 10 / ask-user 4 / no-op 11**(n=25);兩份報告的 `**Report generation**` 同為 `sha256:05594d2e437f052ce65dda2c607df17ca766e2128efa3c58c580942e1296a5bd` → 是成對發布、非中途中止的混合版本。
2. **使用者對四條 `ask-user` 的拍板**(記於 `.claude/bug/pr-281-review-followups/verification.md` §1):D1 分來源寫清楚 + 提醒 #271、**不加守門**;D2 保留 fixture 形狀 + 補 `auction` 斷言;D3 第三種文案、界 = `min(bookdays)`(**不是**報告建議的 `max`);D4 無簿日 ← → 換日;另:報告雙檔入 `docs/`、不重建;#13 改文字不動版面;11 條 `no-op` 不收。

**⚠️ spec 作者 = PR 作者**(`git log --format='%an' -- <spec paths>` = `Loger`,即 PR 作者 loger-w)。**但這裡的利益重疊比字面上弱**:這兩份不是作者為自己的實作寫的辯護文,而是**前一輪 review 的產物**(由 projection helper 產生、帶 25 個 canonical `finding_uid` 與 generation hash),本 PR 只是照拍板把它們原樣搬進 `docs/`。真正帶作者主觀的是第 2 項(拍板紀錄),而那是使用者的決定、本來就該由作者記錄。揭露於此供讀者自行加權。

**Formal spec traceability(Step 2.65)= SKIPPED**,`reason_code = C4_NO_IMPLEMENTATION_BINDING_CLAUSE`:
- `gate: SKIPPED` / `dispatch: NOT_APPLICABLE` / `dispatch_count: 0` / `requested_model: opus` / `observed_model: UNAVAILABLE` / `effort: xhigh` / runtime tool calls = N-A / **0 clauses / 0 findings / 0 observations / 0 invalidated**。
- 判定依據:偵測到的兩份 spec 是**審查報告**,內容是 finding 敘述、`Action` 處置與建議修法 —— 依 Step 2.65「recommendations … do not qualify」不構成實作綁定子句。`grep -cE "MUST|SHALL|NEVER|必須|不得|恆"` 主報告 2 / 副檔 5 命中,且 `grep -nE "^\s*[-*|].*(必須|不得)"` 零命中 → 無契約形狀的條列子句。未呼叫 authority reducer(零候選連四條件的第一條都不滿足),直接 finalize SKIPPED。

## 變更概要

**provenance: N-A**(base = `master`,無 inherited 檔,Step 2.55 不觸發)。

| 檔案 | 類型 | 說明 |
|---|---|---|
| `copycat/book_replay.py` | 改(+13/−3) | **只動 module docstring**(「段的界」分來源改寫);引擎行為零改動 |
| `tests/test_book_replay.py` | 改(+12/−3) | 補 `assert frames[1].auction is True`、改寫 fixture docstring、刪重複的 `assert wire["v"] == 4` |
| `CONTEXT.md` | 改(+7/−3) | 術語 glossary 同步分來源陳述 + `_Avoid_` 補一條 |
| `docs/next-time.md` | 改(+12/−1) | v3 → v4;新增 2026-09-19 一節待辦 |
| `docs/superpowers/specs/pr-281-review{,.audit}.md` | 新(+362 / +781) | 前一輪審查報告原封搬進 docs |
| `.claude/feat/book-replay-auction-segment/evidence/*.py` | 改(3 支) | `check_trial` / `close_pile` / `payload_diff` 的收修 |
| `.claude/feat/book-replay-auction-segment/evidence/*.txt` | 新 3 / 改 3 | 三支腳本 stdout 歸檔 + `trial-*.txt` 重跑 |
| `.claude/feat/book-replay-auction-segment/verification.md` | 改(+13/−2) | 檔案大小改實測位元組表、「右上」→「標頭末端」 |
| `.claude/bug/pr-281-review-followups/**` | 新(5 檔) | 本批 artifact:verification.md、code-review-round-1.json、回看頁快照 + diff、驗證頁產生器 |

### main session 自跑的確定性檢查(不依賴任何 reviewer)

| 檢查 | 結果 |
|---|---|
| 回看頁歸檔鏈 | `viewer_cdp_template.273.html`(980 行)+ 歸檔 `.pr281.diff` → 套用後與 `.pr281.html` **正規化行尾後逐位元組相同** → diff 完整、無夾帶 |
| 歸檔忠實度 | `.pr281.html` 與 repo 外現用檔 `Documents\copycat-trading-review\scripts\week0909\viewer_cdp_template.html` **逐位元組相同**(複查軸另以 sha256 `43daa747…` / 117,624 bytes 獨立確認)|
| 報告雙檔配對 | 兩份 `Report generation` hash 相同 → 非中途中止的混合版本 |
| 上一輪的揭露勘誤 | 表格與 canonical UID 記錄**都是** auto-fix 10,PR 說的「正確是 10」成立;機器可讀紀錄從未錯過,錯的只有一句散文 |
| 硬編 worktree 路徑 | 全 repo 獨立重數:**12 處**、其中指向已刪 worktree **10 處** —— 與 chunk 2 的表逐行相同(F-02 的依據)|

## 發現總覽的排序與欄位

排序依 最終建議 group(Must Fix → Should Fix → Nice to Have → 參考用),group 內保留 finding 編號序;severity 只在格內顯示,不驅動排序。

本輪只有一個 review 軸,故表格退化為 `CC`(first-pass severity)+ `複查`(Step 4.2 替代 pass 的 verdict 與校正 severity)兩欄。`CC` 欄的來源 reviewer 標在「Inline Comments per Finding」各條內。

## 發現總覽

| # | 問題 | CC | 複查(獨立 CC 踢館,同軸) | 最終建議 | Action | Action 理由 |
|---|---|---|---|---|---|---|
| 1 | D3 新面板文案宣稱「它落在有簿的區間內(A–B)」,但界改成 `min` 後,日期晚於最後有簿日時這句是假的 | MED | CONFIRMED(MED→**LOW**) | Nice to Have | `auto-fix` | 一行文案,修法兩軸與複查收斂成同一句;本批最值得先做的一條 |
| 2 | 待辦與 docstring 兩處都寫「另有 6 處」,實際硬編 12 處、其中 10 處指向已刪 worktree | LOW | PARTIAL(LOW) | Nice to Have | `auto-fix` | 數字直接換掉;複查指出漏數的是 3 處不是 2 處 |
| 3 | `verification.md` 記 diff「105 行」,`wc -l` 是 114 | LOW | PARTIAL(LOW) | Nice to Have | `auto-fix` | 105 = 內容行、114 = 全檔,換一個寫法即可 |
| 4 | `check_trial.py` docstring 寫「收修三件」,底下只有兩件 | LOW | CONFIRMED(LOW) | Nice to Have | `auto-fix` | 改一個計數詞 |
| 5 | `check_trial.py` 早退訊息在「代號參數沒對上」時也印「目錄空或日期打錯」,指著有 80 支檔的目錄 | LOW | CONFIRMED(LOW) | Nice to Have | `auto-fix` | 兩行分流,三種情形本來就分得出來 |
| 6 | `make_pr281_check_pages.py` 對常數推出來的路徑無條件 `rmtree`,而「不動真資料夾」只寫在 docstring | LOW | PARTIAL(LOW) | Nice to Have | `auto-fix` | 一行 assert 就把承諾變成機器可驗;複查證實風險被講重了但值得加 |
| 7 | D4 新註解把「可能永久」的狀態寫成「還在載入」;有簿日但缺該檔時 ← → 永久零回饋 | LOW | PARTIAL(LOW) | Nice to Have | `ask-user` | 註解半邊可直接改,行為半邊在 D4 拍板字面之外、要你決定收不收 |
| 8 | 新加的 CSS 註解枚舉不準(chip 與色帶 title 是同一份、漏了兩處),且「JS 讀不到」字面為假 | LOW | CONFIRMED(LOW) | Nice to Have | `auto-fix` | 註解本身的用途就是給未來改名的人當清單 |
| 9 | `code-review-round-1.json` 寫「1,002 行 HTML 副本」,現檔是 1,006 行 | LOW | **REFUTED**(LOW) | 參考用 | `no-op` | 1,002 在該紀錄寫下的時點是對的,差 4 行正是同一份 json 的 Std-4 + Std-5 收修加的 |
| 10 | 三態分類在 `rpTabState` 與 `renderReplay` 各寫一份,順序必須同步而無物釘住 | LOW | PARTIAL(LOW) | 參考用 | `no-op` | 目前兩份順序一致、無現存 bug;複查另指出「F-01 是其實例」講過頭 |
| 11 | `p.trial \|\| []` 先於 `Array.isArray`,falsy 非陣列仍靜默退化成「沒有段」 | LOW | **REFUTED**(LOW) | 參考用 | `no-op` | `\|\| []` 是 v3 往下相容的刻意寫法;產生端不可能吐 falsy 非陣列 |

auto-fix 只是處置建議；沒有使用者另行下令，不修改 code、commit、push 或 PR。

F-01 finding_uid: 644ea8b44a277bfb763e action=auto-fix
F-02 finding_uid: 56e264ac0509fbd84dfb action=auto-fix
F-03 finding_uid: 6513ea0a514d86877849 action=auto-fix
F-04 finding_uid: d91cf82f6d7592b13bc5 action=auto-fix
F-05 finding_uid: 165875dc3fe504da4978 action=auto-fix
F-06 finding_uid: 6cdf5eb6ce68688ef451 action=auto-fix
F-07 finding_uid: 90337649983585110ce3 action=ask-user
F-08 finding_uid: 3cecc55f309ed7e13a5a action=auto-fix
F-09 finding_uid: fe2f0a740a9e6fde1ff0 action=no-op
F-10 finding_uid: 2f0129966b1e2faf49f2 action=no-op
F-11 finding_uid: 6dfdb86590bcd39f44a0 action=no-op

### Inline Comments per Finding

#### #1 日期比最後有簿日還新時,面板會說「它落在有簿的區間內」而那個日期根本不在區間裡

**File**: `.claude/bug/pr-281-review-followups/viewer_cdp_template.pr281.html`
**Line**: 831

**Comment**:
```
D3 的界照拍板取 min(bookdays),rpShouldHaveBook() 只比下界(:804 state.date >= BOOK_FROM),
所以 state.date 比最後一個有簿日還新時分支照樣命中 —— 這是對的,也是這條 finding 的設計本意。
但面板文案(:831)沿用了報告原本建議 max 版的措辭,無條件印「它落在有簿的區間內(days[0]–days[最後],
目前 N 天)」。

實測(把 bookdays 砍成 ["2026-09-16","2026-09-17"]、選 2026-09-18):

  2026-09-18 應該有五檔簿,但這一頁沒掃到 —— 它落在有簿的區間內(2026-09-16–2026-09-17,目前 2 天)。

09-18 不在 09-16–09-17 裡面。而且這正是最常見的那一種:日期選單來自 daily_groups.json 的 TAIEX 日
(盤後手順第 2 步),book-replay 是獨立的第 1 步 —— 漏跑最新那天時,新日期必然落在 max 之外。
next-time 自己記著的「09-17 第一次實跑就漏過」當時也是最新那天。

壞掉的只有括號那句:標題「應該有五檔簿,但這一頁沒掃到」與下面的補跑指令都仍正確,tooltip 版
(:812-813)不印區間、沒有這個問題。

改一句就好,同時蓋住中間缺與尾巴缺:

它不早於最早有簿的一天(${esc(days[0])};目前有簿 ${days.length} 天,最後一天 ${esc(days[days.length-1])})

順帶:verification.md §6 的 D3 真環境驗證只做了「界內缺一天」那一格(把 09-17 拿掉),
也就是含入為真的那一格;date > max 這格沒驗到。
```

#### #2 「另有 6 處」在兩個地方各寫了一份,實際是 12 處硬編、10 處指向已刪 worktree

**File**: `docs/next-time.md`
**Line**: 5

**Comment**:
```
這一條的整個價值就在「批次收要收完」,所以那個數字是後人拿來當 checklist 的。實測對不上:

  硬編 worktree 路徑總數: 12
    其中指向已刪 worktree: 10  (本批 3 支 + 另 7 處,不是 6 處)
    指向仍存在的 worktree: 2

而且那 2 個「還在」的目錄 —— fix-pr-279-review-followups 是全空、ws-app-heartbeat 只剩 frontend/ ——
都沒有 copycat/ 套件。就這條關心的失效模式(sys.path 錨點指到沒有 code 的地方)而言,12 個全是死的。

漏數的三處裡,兩處是把路徑放進具名常數而不是內聯在 sys.path.insert(...) 裡:

  .claude/bug/stkfut-order-channel/evidence/capital_side_server.py:13   WORKTREE = Path(r"...")
  .claude/feat/market-overview-r3-limit-list/evidence/breadth_side_server_r3.py:12   WT = r"..."

兩支的下一行就是 sys.path.insert(0, ...),同款不能排除 —— 正是這條自己要記的那種 grep 形狀盲區。

同一個錯數字還有第二份:.claude/feat/book-replay-auction-segment/evidence/check_trial.py:11
也寫「repo 內另有 6 處同款」。兩處要一起改。

建議寫法:「硬編 worktree 路徑 12 處,全部指向沒有 copycat/ 套件的目錄(10 處目錄已刪、2 處是空殼)。
數的時候 sys.path.insert 與 WORKTREE = / WT = 兩種形狀各掃一次 —— 具名常數那種上次就是這樣漏掉的。」
另外第 9 行的 N=4 只適用 evidence/ 子目錄;直接放在 slug 目錄下的(compare_v2_v3.py)是 N=3。
```

#### #3 diff 記成 105 行,`wc -l` 是 114

**File**: `.claude/bug/pr-281-review-followups/verification.md`
**Line**: 92

**Comment**:
```
§6 尾寫「viewer_cdp_template.pr281.html / .diff(自 #273 出貨狀態起,105 行)」,實際 wc -l = 114。

105 不是隨手編的 —— 它精確等於扣掉 9 行 @@ 標頭後的內容行數:

  context 65 + 加 33 + 減 7 = 105,+ hunk 標頭 9 = 114

所以是換了一把尺,不是錯記。但下一個人 wc -l 就會再開一條 finding,建議直接寫 114,
或寫「內容行 105 / 全檔 114」把兩把尺都講明。

(這份的其餘數字都核得過:pytest 118 條、47,033 / 27,806 / 29,675、25,775 = 7,405+7,413+10,957、
1,355,182 = 375,387+477,256+502,539,位元組表 +3,300 / +3,044 / +4,176。只有這一格落單。)
```

#### #4 docstring 說「收修三件」,底下只有兩件

**File**: `.claude/feat/book-replay-auction-segment/evidence/check_trial.py`
**Line**: 5

**Comment**:
```
「2026-09-19 pr-281 review #6 收修三件:」底下只有兩個項目(樣本改印「列 n / 共 m 筆」、除零早退)。
第三段講的 sys.path 是 review #17、處置 no-op,那段自己就寫著「不在這批挑食」—— 沒收,而且屬於
別的 finding 編號。

對照報告 pr-281-review.md:41 的 #6 列,Action 欄逐字是「(a)(c) 成立、(b) 被反駁;補「(前 8 筆,共 n 筆)」
與除零早退」= 兩件。

「三件」→「兩件」即可。
```

#### #5 打錯代號時,訊息會指著一個有 80 支檔案的目錄說「目錄空或日期打錯」

**File**: `.claude/feat/book-replay-auction-segment/evidence/check_trial.py`
**Line**: 67

**Comment**:
```
早退本身有效(把 ZeroDivisionError 換成看得懂的訊息),但 files 變空有兩條路:目錄空 / 日期錯,
以及**選用的代號參數一個都沒命中**(:35-37 的 only 過濾)。第二條走到同一個訊息。

實跑:

  $ python check_trial.py 2026-09-16 9999
  == 2026-09-16:0 檔、0 則 —— 目錄空或日期打錯(...\viewer-cdp-book\2026-09-16)
  exit=2
  $ ls .../viewer-cdp-book/2026-09-16 | wc -l
  80

使用者會去查日期,而不是查自己打的代號。三種情形其實分得出來 —— 注意 :34-37 的 files 是**就地重新綁定**、
過濾前的清單沒留著,所以要先接成別的名字才印得出「目錄裡本來有幾支」:

  files = sorted(BOOK.joinpath(date).glob("*.js"))
  only = set(sys.argv[2:])
  if only:
      picked = [p for p in files if p.stem in only]
      if not picked:
          print(f"== {date}:代號 {sorted(only)} 在 {BOOK / date} 的 {len(files)} 支裡一支都沒對上")
          return 2
      files = picked

其餘維持現句。不想動結構的話,最省事是把訊息改成不下結論的
「0 檔 / 0 則(日期、目錄或代號篩選對不上)」。
```

#### #6 「不動真的 viewer-cdp-book/」這個承諾只寫在 docstring 裡,實作只靠一顆字串常數

**File**: `.claude/bug/pr-281-review-followups/make_pr281_check_pages.py`
**Line**: 54

**Comment**:
```
docstring 第 3 行承諾「不動真的 viewer-cdp-book/」,而實作是 shutil.rmtree(tmp.parent),
tmp.parent = ROOT / TMP_BOOKDIR。唯一保證它不是真資料夾的是一顆字串常數
("viewer-cdp-book-pr281" vs 真的 "viewer-cdp-book",差一個尾碼),而同一支腳本 :56/:58 又讀真目錄。

現況不是 bug(常數正確、沒有 argv/env 覆寫路徑、暫用資料夾現在也不存在,那個 rmtree 是 no-op),
而且真目錄旁有三份 .bak 備份,所以「永久失去」不成立。但這是整個 .claude/** evidence 語料庫裡
唯一一處破壞性呼叫(grep rmtree|os.remove|unlink( 只有它),沒有同款前例可以替它背書 ——
所引為作法來源的 make_empty_bookdays.py 完全不刪任何東西。

一行就把 docstring 的承諾變成機器可驗:

  assert TMP_BOOKDIR != "viewer-cdp-book" and TMP_BOOKDIR.endswith("-pr281")

順帶 if tmp.parent.exists(): rmtree(...) 是先檢查再操作,rmtree(..., ignore_errors=True) 更直接。
```

#### #7 有簿的那天、但這一檔沒有外掛檔時,← → 也是永久沒反應 —— 而畫面自己叫你「換一天」

**File**: `.claude/bug/pr-281-review-followups/viewer_cdp_template.pr281.html`
**Line**: 931

**Comment**:
```
新註解寫「有簿但**還在載入**(RP 尚未掛上)不換日」,但守門條件 !RP 同時涵蓋另一個**不是暫態**的狀態:
那天有簿,但這一檔沒有外掛檔。

追機制:renderReplay :845 先 RP = null,loadReplay 的 .catch(:847-848)失敗時只換 innerHTML、
**不重設 RP**。此時 rpHasBook() 為 true(那天確實在 bookdays 裡)→ :931 走 !RP 分支直接 return,
而 :928 的 preventDefault() 已經吃掉按鍵。畫面停在「有簿重播,但沒有這一檔 …… 換一檔或換一天」,
而換天那顆鍵剛好在這個畫面上是死的。

現用頁面上就有 6 組:代號 3630 與 4977 × 2026-09-16 / 17 / 18(頁面有資料、外掛檔目錄裡沒有)。

兩件事要分開看:

(1) 註解那半是本 PR 的 —— 它把一個可能永久的狀態描述成暫態,建議改成
    「RP 尚未掛上(載入中**或載入失敗**)一律不換日」。這半可以直接改。

(2) 行為那半**不是本 PR 造成的迴歸** —— 改前的 273 版 :906 同樣是
    e.preventDefault(); if(RP) rpGo(...),同一狀態下也是零回饋;而 D4 的拍板字面只涵蓋「無簿日」。
    要不要一併收,是新的範圍決定。真要收,rpWait 正好是「在飛」的訊號:

      if(!RP){ const k = state.code+"|"+state.date;
               if(!rpHasBook() || !rpWait.has(k)) stepDay(e.key === "ArrowLeft" ? -1 : 1);
               return; }

滑鼠路徑(上方 ◀ ▶、日期下拉)不受影響,所以不是死路一條。
```

#### #8 這段 CSS 註解是給未來改稱呼的人當清單用的,但它列的地方本身不準

**File**: `.claude/bug/pr-281-review-followups/viewer_cdp_template.pr281.html`
**Line**: 90

**Comment**:
```
註解寫「『集合競價』的第 4 份字面(另三處:頁頭 chip、色帶 title、說明列),而且藏在 CSS —— JS 讀不到」。
三個子主張各有問題:

1. 「頁頭 chip」與「色帶 title」其實是**同一份字面** —— :947 的 chip 與 :703 的 title 都呼叫
   :692-693 的 rpTrialName。對「改稱呼要改幾個字面」而言算一處,註解把它拆成兩處。
2. 反過來又漏了兩個會顯示這個詞的地方::731 中間欄空變動說明「集合競價撮合(這一則不拆…)」、
   :865 rp-note「集合競價段」。全檔這個詞共 20 行命中。
3. 「JS 讀不到」字面為假 —— 真 Chrome 的 getComputedStyle(el,'::after').content 讀得到
   (實測回傳 "集合競價"),讀不到的是 innerHTML / textContent 快照,而 dom_regression.mjs:25-27
   存的正是 innerHTML。

這一點反而是有實益的:既然真瀏覽器讀得到,順手在 dom_regression.mjs 加一行 getComputedStyle 斷言,
就能把「最容易漏掉的一份」變成擋得住的一份,比註解可靠。

建議改成:「另三份字面在 rpTrialName(頁頭 chip 與色帶 title 共用)、rpChangeLines 的集合競價撮合、
說明列與 rp-note;這一份藏在 CSS,innerHTML / textContent 快照讀不到(要 getComputedStyle(el,'::after')
才讀得到)。」報告 #13 那一條可一併記為勘誤。

(同段第三行「.rp-msg-h 是 flex 沒有 justify-content,所以緊接在標頭文字後面、不貼右緣」查證為真,
:131 確無 justify-content;「右上」也已在全檔與 feat verification 清乾淨。#13 的主體做對了。)
```

#### #9 這不是缺陷:1,002 在那份紀錄寫下的時點就是對的

**File**: `.claude/bug/pr-281-review-followups/code-review-round-1.json`
**Line**: 58

**Comment**:
```
Std-0 那條寫「兩份審查報告與 1,002 行 HTML 副本掃過無異常」,而現檔是 1,006 行 —— 乍看是數字錯。
實際不是:

  273 基準檔 980 行 + 歸檔 diff 淨增 26(加 33−1 個 +++ 減 7−1 個 ---)= 1,006
  收修加的行:Std-4 hoist 3 行(BOOK_SORTED / BOOK_FROM + 註解)+ Std-5 拆錯誤文案 1 行 = 4
  1,006 − 4 = 1,002

也就是那一輪 review 看的就是收修前、1,002 行的那一版。旁證:同一份 json 的 Std-4 finding 引的
[...BOOKDAYS].sort()[0] 字面在最終檔裡已經不存在。而 code-review-round-<N>.json 依 closeout §0
是「findings 原文照錄」的凍結紀錄,Std-0 那欄正是 reviewer 的原話。

把它改成 1,006 反而會讓凍結紀錄與它評的對象對不上。真要零摩擦,頂多寫成「1,002 行(收修前)」。
不建議動。
```

#### #10 三態分類寫了兩份,順序必須同步而沒有東西釘住

**File**: `.claude/bug/pr-281-review-followups/viewer_cdp_template.pr281.html`
**Line**: 810

**Comment**:
```
本 PR 把「界」抽成 rpShouldHaveBook() 一顆單一來源(對的,而且 tooltip 是報告沒列到的第二處假陳述,
一起收也對)。但**分類本身**仍是兩份:rpTabState 用三層三元鏈(:810-814)、renderReplay 用
early-return if 鏈(:820 / :830 / :836)。兩邊要維持同樣的順序與三個述詞,才不會 tooltip 說 A、面板說 B。

目前兩份的分支順序一致、行為等價 —— 這是 drift 風險,不是現存 bug。這條三元鏈現在是 3 層,
剛好踩到「三元鏈 ≥ 3 層攤平」,而同檔 renderReplay 用的是 guard clause,兩種風格並存。

真要收:抽一顆 rpBookState() 回 "ok" | "nodir" | "missing" | "never",tooltip 與面板各自 switch 它。
但這是判斷題,且該檔還有多處同量級的手寫重複,單挑這一處不划算 —— 列參考用。

(附帶更正:複查指出「F-01 正是這種發散的實例」講過頭了 —— F-01 的假陳述發生在單一份句子裡,
tooltip 正確的原因只是它話講得少、不印區間,不是兩份順序漂了。)
```

#### #11 這不是缺陷:`|| []` 是 v3 往下相容的刻意寫法

**File**: `.claude/bug/pr-281-review-followups/viewer_cdp_template.pr281.html`
**Line**: 645

**Comment**:
```
const trialFlat = p.trial || [] 先於 :646 的 Array.isArray 守衛,所以 p.trial 若是 falsy 的非陣列
(0 / "" / false)仍會被吞成空段 —— 事實描述正確。

但 :625-626 的註解明寫「只加欄位的升版往下相容:v3 沒有 trial(集合競價段),**當空集合**」——
|| [] 就是這個相容行為的實作,換成嚴格檢查會連 v3 舊檔一起擋掉(CLAUDE.md 記著「v3 檔在 v4 的
回看頁實測照開」)。同一行上方 :643 的 p.auction || [] / p.stale || [] 兩處同款長期未爆。

而產生端是 copycat/book_replay.py 以 json.dumps 寫一個 list、落檔前逐檔 decode 自檢相等,
不可能產出 falsy 非陣列。#10 真正打得到的那一格用的是**物件** {"0":0}(truthy),已經被 :646 補上。

不動。要記也只值一行註解。
```

## CC 原始 findings(first-pass,context-aware)

### primary reviewer chunk 1(`code-reviewer`,11 檔)

- **MEDIUM** `viewer_cdp_template.pr281.diff:70-93` — D3 新文案「它落在有簿的區間內(min–max)」在「最新一天漏跑 book-replay」時是假陳述。search-proof:Grep `rpShouldHaveBook|BOOK_FROM|BOOK_SORTED` 只有四個站點、無第二道上界檢查;`docs/next-time.md:44-47` 證明日期選單與 book-replay 是兩個獨立步驟;`verification.md` §6 兩列 D3 驗證只涵蓋界內缺一天與界前。
- **LOW** `verification.md:92` — 記的 diff 行數 105 與歸檔 `.diff` 實際 114 對不上。
- **LOW** `code-review-round-1.json:58` — Std-0 寫「1,002 行 HTML 副本」,實際 1,006 行。
- **LOW** `make_pr281_check_pages.py:52-55` — docstring 承諾「不動真的 viewer-cdp-book/」,唯一守門是一顆常數 + 裸 `shutil.rmtree`。

另附核過**沒有**問題的七項(避免重工):`.pr281.html` 是忠實快照無夾帶(自行重跑 GNU diff 比對)、三支 `.txt` 與腳本格式一致、證據數字互相咬合、`check_trial` / `payload_diff` 改動語意等價、三支 `sys.path` 未收是刻意的(自行數過全 repo 9 處)、`Array.isArray` 先於 `% 2`、`rpKey` 換日路徑、commit type 全在允許集合內。

### primary reviewer chunk 2(`code-reviewer`,10 檔)

- **LOW** `docs/next-time.md:3-10` — 新增待辦把「要一次收完」的站點數寫成 9 處(另 6 處),實際 10 處指向已刪 worktree、12 處硬編路徑。search-proof:以 regex 掃全 repo `.py` 並與 `ls .claude/worktrees` 取交集,附完整 12 行清單;指出漏掉的兩處都是具名常數形狀。

**最重要的單一事實已獨立驗證為真**:`copycat/book_replay.py` 只動 module docstring。三道獨立證據 ——(1) 只有兩個 hunk、全落在 docstring 的 1–119 行內;(2) 剝掉 module docstring 後 `ast.dump` base/head 同為 `1c1751e308157ce9`;(3) docstring 之後逐位元組 `cmp` 回報 IDENTICAL(偏移 +10 行 = docstring 增量)。

**D2 新斷言的守門力已獨立做突變驗證**:在 `_auction_match` 插入 `and row.trade_status != _TRIAL_STATUS`(= 舊 docstring 宣稱的互斥)後重跑 → **只有那一條紅**(`AssertionError: assert False is True`),1 failed / 117 passed;突變已還原。

**三處敘述一致性**已逐處比對:`book_replay.py:65-74` / `CONTEXT.md:280-294` / 回看頁,四個維度(分來源、1,169、7772 實例、明講不互斥)全部一致,且與程式實際行為(`:485` 讀本則 vs `_auction_math` 讀前一則)相符。

### 語言軸 `python-reviewer`(6 支 `.py`)

- **LOW** `check_trial.py:5-8` — docstring 寫「收修三件」但只列兩件。
- **LOW** `check_trial.py:66-68` — 早退訊息把「代號篩掉全部」誤報成「目錄空或日期打錯」(**實跑兩條路徑**取證)。
- **LOW** `make_pr281_check_pages.py:52-54` — 同 chunk 1 的 rmtree 條(同軸 corroboration)。

另獨立驗過:`book_replay.py` 的 AST 比對、刪 `assert wire["v"] == 4` 安全(golden `:1889` 仍釘 `"v": 4`,且 `decode` 對版本不符會 raise)、新斷言的 docstring 事實主張**對照真外掛檔**逐項相符、`close_pile.py` 實跑復現歸檔輸出、`check_trial.py` 重構後輸出逐位元組相同、`payload_diff.py` docstring 更正準確。

### 語言軸 `typescript-reviewer`(回看頁 `.diff` + `.html`)

- **MEDIUM** `.pr281.html:830-831` — 同 chunk 1 的 D3 文案條(同軸 corroboration),另以 node 逐字重跑判斷式做出六情境表,含「09-17 當晚 bookdays 只有 {09-16}」那格會印「落在區間內(09-16–09-16)」。
- **LOW** `.pr281.html:930-931` — D4 的 `!RP` 守門把「還在載入」與「載入永久失敗」當同一件事。
- **LOW** `.pr281.html:90-91` — CSS 註解的枚舉不精確 +「JS 讀不到」字面不成立。
- **LOW** `.pr281.html:810-814` — 三態分類兩份、順序無物釘住。
- **LOW(自標低於動手門檻)** `.pr281.html:645-646` — `|| []` 先於 `Array.isArray`。

另獨立驗過並明確回報**沒問題**:跳脫層級(`\\${esc(BOOKDIR)}` 以 `new Function` 求值,輸出恰 1 個反斜線、`${` 殘留 0)、`Array.isArray` 守衛位置、三元鏈順序與 `BOOKDAYS` null/空集合(六情境實跑無洞)、`preventDefault()` 位置未製造新吞鍵、三處 v2→v4 註解正確、`BOOK_SORTED`/`BOOK_FROM` hoist 正確(字典序 = 時序、不動 Set、TDZ 無虞)、D1 說明文字與實測數字相符、XSS/注入(新文案全走 `esc()`)。

## 複查結果(Step 4.2 替代 pass:獨立同軸踢館)

| # | first-pass 來源 | verdict | 原始 → 校正 severity | 複查證據 | 備註 |
|---|---|---|---|---|---|
| 1 | chunk1 + typescript | CONFIRMED | MED→**LOW** | 解現用頁 payload:bookdays 3 天 vs 日期選單 57 天;日期選單來自 `daily_groups.json` 非掃外掛檔 → 「最新一天 > max」是漏跑步驟 1 的**預設結果**,比中間缺更常見 | 標題句與補法指令仍正確,無資料/金額後果 → LOW,但屬「一行改掉、別拖」 |
| 2 | chunk2 | PARTIAL | LOW | 自行重數 12 處;另指出兩個「還在」的 worktree 是空殼(無 `copycat/`)→ 12 個錨點全死 | **更正 main session**:漏數是 3 處不是 2 處,且第三處是內聯形狀 |
| 3 | chunk1 | PARTIAL | LOW | 拆 diff 首字元:context 65 + 加 33 + 減 7 = **105**,+ 9 個 `@@` = 114 | 105 是另一把尺,不是編的 |
| 4 | python | CONFIRMED | LOW | 對照報告 `:41` 的 #6 列 Action 欄逐字 = 兩件 | — |
| 5 | python | CONFIRMED | LOW | **自行實跑**(不吃轉述)`check_trial.py 2026-09-16 9999` → 同一句、exit 2;同時 `ls` 該目錄 = 80 支 | 三種情形分得出來,修法兩行 |
| 6 | chunk1 + python | PARTIAL | LOW | 常數無 argv/env 覆寫、暫用資料夾現已不存在(rmtree 是 no-op)、真目錄旁有三份 `.bak` → 「永久失去」不成立;但 `grep rmtree\|os.remove\|unlink(` 全 evidence 語料庫只有這一處,無 baseline 背書 | 降溫但不撤,加一行 assert 收工 |
| 7 | typescript | PARTIAL | LOW | **自行點出 6 組**(3630 / 4977 × 09-16~18);修前 `273.html:906` 同狀態也零回饋 | **更正**:不是本 PR 迴歸、不在 D4 字面內;可達性反而被低估 |
| 8 | typescript | CONFIRMED | LOW | 三個子主張逐一驗:chip 與 title 同源 `rpTrialName`、全檔 20 行命中且 `:731`/`:865` 被漏、**實跑 headless Chrome** 確認 `getComputedStyle(el,'::after').content` 回傳該詞 | 註解真正要講的那半(innerHTML 快照抓不到)是真的 |
| 9 | chunk1 | **REFUTED** | LOW | 980 + 26 = 1,006;Std-4 hoist 3 行 + Std-5 拆文案 1 行 = 4;1,006 − 4 = **1,002**;旁證 = Std-4 引的 `[...BOOKDAYS].sort()[0]` 字面在最終檔已不存在 | 凍結紀錄照「現在的檔案」去對是錯的尺 |
| 10 | typescript | PARTIAL | LOW | 兩份順序目前一致、無現存 bug | **更正**:「F-01 是其實例」講過頭 |
| 11 | typescript | **REFUTED** | LOW | `:625-626` 註解明寫 v3 往下相容當空集合;`:643` 同款兩處長期未爆;產生端 `json.dumps` 一個 list + decode 自檢 | 事實正確但無可信觸發路徑 |

**分佈**:CONFIRMED 4 / PARTIAL 5 / REFUTED 2 / OUT_OF_SCOPE 0 / INCONCLUSIVE 0。REFUTED 率 18%(2/11)。

### 複查對 main session 的更正(全部經 main session 重驗後採納)

派這道 pass 時已在 prompt 內明白告知「PR 作者 = 派你出來的 main session 本人,標『main session 已驗』的證據由當事人產生,不要照單全收」。它提了 4 項更正,我逐項重驗:

1. **F-09 整條是誤報,已撤回**(改列參考用 / `no-op`)。重驗:`wc -l` 273 基線 = 980、diff 首字元拆解得淨增 26 → 1,006;Std-4/Std-5 收修加 4 行 → 收修前 1,002。JSON 的 Std-0 欄確為 closeout §0 要求的「原文照錄」體。**複查是對的,我原本的判定錯了。**
2. **F-02 我自己也少數了**:12 − 9 = **3** 處不是 2 處。重驗:`ls .claude/worktrees/fix-pr-279-review-followups` 全空、`ws-app-heartbeat` 只剩 `frontend/`,兩者都無 `copycat/` 套件 → 就本 finding 的失效模式而言 12 個錨點全死。已改寫 inline comment。
3. **F-03 的「105」不是憑空數字**:重驗 `awk` 拆首字元得 context 65 / 加 33 / 減 7 = 105,+ 9 `@@` = 114。verdict 由 CONFIRMED 降為 PARTIAL。
4. **F-07 不是本 PR 造成的迴歸**:重驗修前 `273.html:906` = `e.preventDefault(); if(RP) rpGo(...)`,同一狀態下也零回饋。已把 inline comment 拆成「註解半邊(本 PR 的)」與「行為半邊(既有、範圍外)」兩塊,Action 改 `ask-user`。

### lone finding 判斷(Step 4.3b)

`effective_severity` 一律取 `corrected_severity`。安全類 finding 0 條 → `severity-calibration.md` 的矩陣不適用。

- **非 lone**(同軸 corroboration):#1(chunk1 + typescript)、#6(chunk1 + python)。
- **lone**:#2 #3 #4 #5 #7 #8 #9 #10 #11。逐條依 6d-2 判斷:
  - #2 #3(chunk2 / chunk1 獨有)— verdict PARTIAL,但「他軸為何漏」解釋得出來:那兩個檔分別只在對方的 chunk 裡,語言軸也不負責 `.md` 逐行核對。**不降級**(本來就已是 LOW / Nice to Have)。
  - #4 #5(python 軸獨有)— verdict CONFIRMED,解釋:primary chunk 1 對 `check_trial.py` 判 `REVIEWED_NO_ISSUES`,而 python 軸是唯一實跑該腳本兩條輸入路徑的軸。**不降級**。
  - #7 #8 #10 #11(typescript 軸獨有)— 解釋:它是唯一被指派逐行審回看頁 JS/CSS 的軸。#7 #10 verdict PARTIAL、#11 REFUTED,但降級無處可降(已是最低級 + 已落 參考用)。
  - #9 — verdict REFUTED,已移入參考用。
- 本輪**沒有任何 finding 因 lone 而被機械降級**;所有 severity 變動都來自複查的 impact 判斷,理由逐條記在複查表。

## Action Items

**Severity calibration**(6c / 6d,SSOT = `~/.claude/references/finding-severity-rules.md`):

1. **6c Refactor Intent Gate** — 本 PR **無**「移除/削弱既有防護」類 finding,本關卡 N-A。(#7 的行為半邊雖然講「← → 死」,但那是既有行為、本 PR 沒有移除任何防護。)
2. **6d-1 hedge cap** — 無 finding 含假設性措辭(「若有人繞過」「假設 API 回 X」)且被列在 Should Fix 以上,N-A。
3. **6d-2 lone finding** — 見上節,以判斷取代機械降級,無一條因 lone 降級。
4. **6d-3 Must Fix 雙半條件** — **本輪零條進 Must Fix**。唯一有具體 user-visible 重現路徑的是 #1(我在真瀏覽器重現),但它的 release-blocking 半邊不成立:壞掉的是本機研究頁面上一句括號內的佐證,標題句與補跑指令都仍正確,沒有 runtime 行為 / 資料正確性 / build·CI 受影響。依 6d-3 cap 在 Should Fix 以下;複查又把 severity 由 MED 校正為 LOW → 落 **Nice to Have**。
5. **Provenance cap** — N-A(base = master,無 inherited 檔)。

**校準套用**:無作者校準檔(`docs/pr-review-calibration/loger-w.md` 不存在)、本輪無套用。

### Must Fix(合併前必修)

**無**。零 CRITICAL / 零 HIGH;唯一的 MEDIUM 經複查校正為 LOW,且不滿足 6d-3 的 release-blocking 半邊。

### Should Fix(強烈建議)

**無**。本輪無 first-pass HIGH,亦無 PARTIAL/INCONCLUSIVE 的 HIGH。

### Nice to Have(可選優化)

#1 #2 #3 #4 #5 #6 #7 #8 —— 八條全是 LOW。建議順序:**#1 先做**(一行文案,而且它的觸發路徑是盤後手順最容易漏的那一種),接著 #2 #4(同一個錯數字的兩份)、#5、#3、#8,最後 #6 #7。

### 參考用(任一軸驗證為 REFUTED 或 OUT_OF_SCOPE,或判定不動)

- **#9 REFUTED** — chunk1 擔心 `code-review-round-1.json` 的 1,002 與現檔 1,006 對不上 → 複查於算術上證明 1,002 是該紀錄寫下時點的真值(980 + 26 = 1,006,減去 Std-4/Std-5 收修的 4 行)→ 凍結紀錄照現檔去對是錯的尺,**不建議改**。
- **#10 判定不動** — typescript 軸指出三態分類兩份、順序無物釘住 → 複查確認兩份目前順序一致、無現存 bug,且該檔多處同量級手寫重複,單挑一處不划算 → 使用者若要收,合理修法是抽 `rpBookState()`。
- **#11 REFUTED** — typescript 軸(自標低於動手門檻)指出 `|| []` 先於 `Array.isArray` → 複查證明 `|| []` 是 v3 往下相容的刻意寫法(`:625-626` 註解明寫)、同款兩處長期未爆、產生端不可能吐 falsy 非陣列 → **不動**。

## 審查工具比較(qualitative)

- **本輪是單軸**:Codex 中性 / Codex 對抗 / Gemini Flash / Gemini Pro 四軸皆因本機未安裝 CLI 而 N-A。所謂「重疊率」在單軸下不可計算;表內的 `CC` 欄是四個 CC reviewer 實例的合併 first-pass。
- **CC 內部的軸間互補很明顯**:11 條 finding 裡只有 2 條被兩個以上 reviewer 同時提出(#1、#6),其餘 9 條都是單一 reviewer 獨有 —— 與「低重疊」的既有觀測一致,也是 6d-2 不做機械降級的理由。
- **分工確實有效**:最重的那條(#1)由 primary chunk 1 與 typescript 軸**各自獨立**提出;最需要實跑取證的兩條(#5 的兩條輸入路徑、#7 的 6 組具體代號)分別由 python 軸與複查軸跑出來;而「`book_replay.py` runtime 零改動」這個全 PR 最關鍵的宣稱,由 chunk 2 與 python 軸**各自用 AST 比對**獨立證明。
- **Step 4.2 替代 pass 的結果分佈**:CONFIRMED 4 / PARTIAL 5 / REFUTED 2 / INCONCLUSIVE 0。REFUTED 率 18%,落在「first-pass 命中率高」與「over-flag 嚴重」之間;而被 REFUTED 的兩條都不是亂報,是**尺用錯了**(#9 拿現檔對凍結紀錄、#11 把刻意的相容寫法當疏漏)。
- **這道 pass 的價值可量化**:它撤掉 1 條誤報、更正了 main session 自己的 1 條數字、把 1 條的 verdict 由 CONFIRMED 降為 PARTIAL、把 1 條的歸因(是否迴歸)講反的地方糾正過來 —— 四項全部經重驗成立。單軸環境下這是唯一還剩的結構性保障。
- **但它仍是同軸**:複查 agent 與 first-pass agents 同為 Opus,共同盲點不會被抓到。這是本輪最大的方法學限制,已列在「沒做的部分」。

## 沒做的部分(結案對帳)

| 項目 | 狀態 | 理由 |
|---|---|---|
| Codex 中性軸 | **N-A** | `command -v codex` 不存在;Step 2.98 的 preset 未詢問(五個答案都不可執行) |
| Codex 對抗軸(紅隊) | **N-A** | 同上 |
| Gemini 3.6 Flash 軸(永久軸) | **N-A** | `command -v agy` 不存在;Step 2.96 的 opt-in 未詢問 |
| Gemini 3.1 Pro 軸(opt-in) | **N-A** | 同上 |
| Step 4.1(CC 驗非 CC 軸) | **N-A** | 無非 CC 軸產生 finding |
| Step 4.2(Codex 驗 CC first-pass) | **替代執行** | 以獨立同軸 `code-reviewer` 踢館 pass 取代。**這不是跨軸** —— 兩邊同為 Opus,共同盲點不會被抓到,這是本輪最大的方法學限制 |
| Step 4.3a(consensus baseline check) | **N-A** | 單軸無跨軸 consensus;同軸 corroboration(#1 #6)已在複查表與 lone 判斷節標明 |
| sem blast radius(2.9) | **N-A** | 腳本有跑(rc=0)、回空輸出;`sem` CLI 本機未安裝。屬「跑了沒結果」,非「沒跑」亦非噪音判定 |
| React-doctor(2.97) | **N-A** | F 內無 `.jsx` / `.tsx` |
| `security-reviewer` | **N-A** | 四項觸發條件逐一查證皆 0 命中(證據見「審查軸狀態明細」) |
| `spec-compliance-reviewer` / C4 | **N-A** | gate SKIPPED(`C4_NO_IMPLEMENTATION_BINDING_CLAUSE`);0 clauses / 0 findings / 0 observations / 0 invalidated |
| 作者校準 | **N-A** | `docs/pr-review-calibration/loger-w.md` 不存在,本輪無套用 |
| Step 4.5 repair re-dispatch | **未觸發** | `MISSED = 0`,無需補派 |
| 09-18 的 527 筆 `auction` 複驗 | **未做** | 正式外掛檔在 repo 外,chunk 2 無法在 repo 內獨立複驗該日數字(09-16 / 09-17 的拆帳已核);與 verification.md §4 的全掃同源 |
| PR 已 MERGED | **知情** | 本輪 review 在 merge 後執行,所有 finding 都只能走後續收修,不影響本 PR 的合併決定 |
| `**Report generation**` | **N-A(草稿階段)** | 由 projection helper 在發布時對 audit 與 main 同時寫入 |
| 未驗證前提 | **無** | 本報告的每條事實主張都附第一手證據(實跑輸出 / `wc -l` / `ast.dump` / 瀏覽器重現 / file:line 引文);唯一標為推論的是複查對「第三處漏數必然是 `compare_v2_v3.py`」的歸因,已在 inline comment 內以「兩處具名常數 + 第三處」的形式改寫成只陳述已證實的部分 |

### 正式報告 Self-Verify 結果與修正紀錄

- **傳遞方式的偏離(主動揭露)**:流程要求把草稿**全文內嵌**於 auditor prompt。我第一次派發時送的是**摘要**(11 個 inline block 只給標頭 + 內文摘要),那正是上一輪 `/pr-review 281` 造成 R5 假陽性的同一個流程偏離 —— 發現後**在 auditor 產出任何結論前就終止該次派發**,改為指定 auditor 以 `Read` 讀取 `pr-282-review.audit.draft.md` 檔案本身。這比內嵌轉錄副本更忠實(讀到的是磁碟實際位元組),且與「不得讀取其他產物補洞」不衝突(草稿本身就是待稽核的 deliverable);但它仍是對「只內嵌」字面的偏離,列此供稽核。
- **auditor 判定**:`VERDICT: VIOLATIONS: R3, R9`(R1 / R2 / R4–R8 / R10 皆 PASS,格式完整、FAIL 集合與逐條一致)。
- **R3(逐檔覆蓋)已修正**:原稿只寫 `skipped 2` 而未揭露那 2 檔的身分與理由。已在「覆蓋 (ENH-A)」行逐一列名(`docs/superpowers/specs/pr-281-review.md` / `.audit.md`)並寫明 skip 理由與 chunk 2 對它們做過的完整性交叉檢查。此為**補寫既有執行證據**,未補跑關卡。
- **R9(條件式關卡 taxonomy)已修正**:原稿的 blast radius 寫「空輸出跳過」而未給 PASS/FAIL/N-A 標籤。已在 header 與「沒做的部分」表兩處改標 **N-A**,並寫明是「跑了沒結果」而非「沒跑」。此為**補寫既有執行證據**,未補跑關卡。
- **另一條由我自己在發布前抓到並修正(非 auditor 所抓)**:#5 的建議修法 snippet 原本引用了 `all_files` 這個**腳本裡不存在的變數**(`check_trial.py:34-37` 的 `files` 是就地重新綁定、過濾前的清單沒留)。已改寫成對得上真實 code 的版本並註明該限制。這正是 R8「修法假設要有第一手驗證」要擋的那一類。
- **未經第二次獨立稽查**:依流程,修正後不重派 auditor。上列三項修正**沒有再經過獨立稽核**。
