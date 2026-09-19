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
## [完整證據副檔](pr-282-review.audit.md)
### finding_uid 索引
[644ea8b44a277bfb763e](pr-282-review.audit.md#發現總覽) · [56e264ac0509fbd84dfb](pr-282-review.audit.md#發現總覽) · [6513ea0a514d86877849](pr-282-review.audit.md#發現總覽) · [d91cf82f6d7592b13bc5](pr-282-review.audit.md#發現總覽) · [165875dc3fe504da4978](pr-282-review.audit.md#發現總覽) · [6cdf5eb6ce68688ef451](pr-282-review.audit.md#發現總覽) · [90337649983585110ce3](pr-282-review.audit.md#發現總覽) · [3cecc55f309ed7e13a5a](pr-282-review.audit.md#發現總覽) · [fe2f0a740a9e6fde1ff0](pr-282-review.audit.md#發現總覽) · [2f0129966b1e2faf49f2](pr-282-review.audit.md#發現總覽) · [6dfdb86590bcd39f44a0](pr-282-review.audit.md#發現總覽)
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
