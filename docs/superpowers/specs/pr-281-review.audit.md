# PR #281 Code Review 比較報告 · SHA 40f7171b

**Report projection schema**: 1

**PR**: [loger-w/copycat#281](https://github.com/loger-w/copycat/pull/281)
**標題**: feat(book-replay): 集合競價段標註 + 無簿日子降級 + 頁面五條限制(#273)
**作者**: loger-w
**分支**: `feat/book-replay-auction-segment` → `master`(狀態 MERGED)
**變更**: 20 檔案, +1949 / -19
**審查日期**: 2026-09-18
**Review input basis**: source repo `R_kgDOTsITBg`(loger-w/copycat)+ source SHA `40f7171b9b94a8c2ef44edddadd6ad01b3a4f545`;destination repo `R_kgDOTsITBg` + destination SHA `fdb654551cfa2427ff2126859f0847d8a1de2ba1`;`input_binding: verified`(review worktree HEAD 逐字等於 source SHA、base 解得到)
**Review continuity**: `source_continuity=CURRENT`;`base_changed=false`;`review_context_changed=false`(dispatch 前後各 refetch 一次,headRefOid / baseRefOid 未變)
**worktree**: `C:\side-project\copycat\.worktrees\review-pr-281`
**worktree HEAD**: `40f7171b9b94a8c2ef44edddadd6ad01b3a4f545`
**審查工具**: CC(context-aware reviewer agents,chunked)+ cross-axis verification。**Codex 中性 / Codex 對抗 / Gemini Flash / Gemini Pro 四軸全部 N-A**(本機未安裝 `codex` 與 `agy` CLI),故本輪實為 **CC 單軸 chunked review**。
**Reviewer model 記錄規則**: 上一行只描述工具組合;固定模型 reviewer 不套用「繼承 main session 模型」,實際身分以下一行為準。
**Reviewer models**: orchestrator = Opus 5 (1M context);primary reviewer = `python-reviewer` × 3 chunk 實例,dispatch 時顯式帶 `model: opus`;verification pass = `code-reviewer`,顯式帶 `model: opus`;spec-compliance-reviewer requested = N-A / observed = UNAVAILABLE / effort = N-A / tools = N-A(gate SKIPPED,未派);Codex = N-A;Gemini = N-A
**覆蓋 (ENH-A)**: |F|=20 → covered 14 / no-issues 6 / skipped 0 / **missed 0**(chunked: 是,DIFF_LINES 1968 > 800 門檻 → 3 chunks,union 逐檔等於 F)
**定位 (ENH-B)**: anchored exact 25 / ambiguous 0 / **FAILED 0**
**React-doctor (2.97)**: N-A(非 React PR — F 內無 `.jsx` / `.tsx`)
**blast radius (2.9)**: 空輸出跳過(`sem` 未安裝,`sem-pr-blast-radius.sh` 回空)
**Formal spec traceability (2.65)**: SKIPPED (`C4_NO_IMPLEMENTATION_BINDING_CLAUSE`)
**Codex preset (2.98)**: N-A(`codex` CLI 未安裝,未詢問 —— 五個 preset 的答案都不可執行)
**Gemini 軸 (2.96)**: N-A(`agy` CLI 未安裝,未詢問 —— 兩個選項的答案都不可執行)
**Quota**: 未取 dashboard snapshot(Gemini 軸未啟用)
**審查軸狀態**: primary reviewer PASS(python-reviewer × 3 chunks,逐檔 accounting 齊全、union = F);security-reviewer N-A;spec-compliance-reviewer N-A;Codex 中性 N-A;Codex 對抗 N-A;Gemini Flash N-A;Gemini Pro N-A;Step 4.1 N-A;Step 4.2 以同軸稽核替代執行;Step 4.3a N-A;Step 4.3b PASS —— 逐軸理由與 search-proof 見「審查軸狀態明細」節,無 PENDING

**Report generation**: sha256:05594d2e437f052ce65dda2c607df17ca766e2128efa3c58c580942e1296a5bd

---

## 審查軸狀態明細

- primary reviewer(`python-reviewer` × 3 chunks)— **PASS**,逐檔 accounting 齊全、union = F
- domain reviewer `security-reviewer` — **N-A**,觸發條件四項逐一查證皆 0 命中(Self-Verify R6 補證):
  - 路徑型:`grep -Ei 'auth/|security/|crypto/|middleware/auth|middleware/csrf|oauth/'` 對 `git diff --name-only fdb65455 40f7171b` 的 20 個路徑 → **0 命中**
  - secret 類 env:`git diff fdb65455 40f7171b -- copycat tests CLAUDE.md CONTEXT.md | grep '^+' | grep -Ei 'API_KEY|TOKEN|SECRET|PASSWORD|CREDENTIAL|getenv|environ'` → **0 命中**
  - request body / cookie / session / JWT / RBAC:`git diff fdb65455 40f7171b -- copycat tests | grep '^+' | grep -Ei 'request\.|cookie|session|jwt|token|role|permission|rbac'` → **0 命中**
  - 語意面:本 PR 的 runtime 改動只有 `copycat/book_replay.py` 的純函式編 / 解碼,無網路、無檔案 IO、無外部輸入(IO 全在 CLI 薄殼)
- domain reviewer `spec-compliance-reviewer` — **N-A**(Step 2.65 gate SKIPPED)
- Codex 中性 — **N-A**(CLI 未安裝)
- Codex 對抗 — **N-A**(CLI 未安裝)
- Gemini Flash — **N-A**(CLI 未安裝)
- Gemini Pro — **N-A**(CLI 未安裝,且本輪預設不加)
- cross-axis verification Step 4.1(CC 驗非 CC 軸)— **N-A**(無非 CC 軸 finding 可驗)
- cross-axis verification Step 4.2(Codex 驗 CC first-pass)— **以替代方式執行**:改派一個未參與 first-pass 的獨立 `code-reviewer` 稽核 agent 跑同一套踢館 prompt(exploitation / impact / baseline-comparable / mitigation 四測)。**這是同軸複查,不是 cross-axis 證據** —— 它擋得住 over-flag,但擋不住「兩個同型 reviewer 犯同一種錯」。報告一律以此口徑呈現。
- Step 4.3a consensus baseline check — **N-A**(單軸,無 cross-axis consensus)
- Step 4.3b lone-finding 判斷 — **PASS**(見 Action Items)

## Spec 依據

- **未偵測到 spec / plan 檔案**:Step 2.6 的路徑與檔名 heuristic 對本 PR 的 20 個檔案全部不命中(`verification.md` 位於 `.claude/feat/<slug>/`,不在 `/specs/` `/plans/` `/design/` 等路徑,檔名也不是 `*-spec.md` 型)。
- **實際的 binding spec 是 GitHub issue**:ticket #273(五條 acceptance criteria)、parent spec #265(簿重播整體設計,含「唯一測試 seam = 引擎公開介面」「零 IO 純函式」等約束)。兩者的內容已逐字注入三個 chunk reviewer 與驗證 pass 的 prompt。
- **spec 作者同人檢查**:issue #273 / #265 的作者為 `loger-w`,**= PR 作者**。⚠️ spec 作者 = PR 作者 —— 本報告凡以「spec 明文排除」作為 OUT_OF_SCOPE 判準之處,讀者應知悉這層利益重疊(本輪實際上沒有任何 finding 被判 OUT_OF_SCOPE,故此揭露不影響任何結論)。
- **動工前兩個 user 拍板**(已注入所有 reviewer,且明示不得重新爭論):(1) AC2「集合競價段不產生厚檔事件」刻意延後到 #271;(2) 段的判準刻意用達錢 `TradeStatus == "1"` 而非牆鐘 13:25–13:30 窗。
- **`SPEC_COMPLIANCE` receipt**:`gate=SKIPPED`、`dispatch=NOT_APPLICABLE`、`dispatch_count=0`、`reason_code=C4_NO_IMPLEMENTATION_BINDING_CLAUSE`、`requested_model=N-A`、`observed_model=UNAVAILABLE`、`effort=N-A`、runtime tool calls N-A。判定理由:repo 內無 `openspec/`;binding requirement 是 GitHub issue 的 checkbox 驗收條款,屬 Step 2.65 排除清單明列的「informal plan/design prose」,不具 `NORMATIVE_KEYWORD` / `INVARIANT` / `FORMULA` / `STATE_TRANSITION` / `ERROR_CONTRACT` 型別,也沒有 repo 內的 stable `path:line`。唯一形似 in-repo invariant 的是 `CLAUDE.md` §4「改欄序 = 改外掛檔格式,`FORMAT_VERSION` +1」,但本 PR 已正確 bump 3 → 4,不存在 criterion 4 要求的「可能缺漏的必要行為」,故無候選進入 clause inventory、reducer 未被呼叫。0 clauses / 0 findings / 0 observations / 0 invalidated;`invalidated_ids ∩ report_finding_ids = ∅`(兩者皆空),整份報告零 C4 候選與零 invalidated 語意內容。

## 變更概要

**provenance**: N-A(base = master,20 檔全數 authored,無 inherited)。

| 檔案 | 類型 | 說明 |
|---|---|---|
| `copycat/book_replay.py` | M +66/-10 | 本 PR 的實質改動:`Frame.trial` 旗標、外掛檔 v3 → v4 新增 `trial` 則號閉區間、`_trial_ranges` / `_check_trial_ranges`、模組說明新增「集合競價段」段落 |
| `tests/test_book_replay.py` | M +136/-8 | 新 `TestAuctionSegment`(4 條行為 + 6 條 parametrize 拒收);既有 v3 字面測試更名為 v4 並補 `trial` 鍵 |
| `CONTEXT.md` | M +10 | 新術語「集合競價段」 |
| `CLAUDE.md` | M +1/-1 | §1 簿重播外掛檔那列改 v4 + 實測數字 |
| `.claude/feat/book-replay-auction-segment/verification.md` | A +177 | 本 PR 的驗證紀錄 |
| `.claude/feat/book-replay-auction-segment/code-review-round-1.json` | A +85 | 出貨前 two-axis review 的 11 條 finding 與逐條處置 |
| `.../evidence/viewer_cdp_template.273.html` | A +980 | repo **外**回看頁模板的逐位元組歸檔副本(該頁是 user 每日用的離線 HTML,repo gate 蓋不到,故以副本入版控) |
| `.../evidence/viewer_cdp_template.diff` | A +222 | 上述模板本次改動的 unified diff |
| `.../evidence/build_viewer_cdp.diff` | A +16 | 回看頁產生器本次改動的 diff(新增 `bookdays` / `bookdir`) |
| `.../evidence/{check_trial,close_pile,merged_run,no_close,payload_diff,payload_dump,make_empty_bookdays}.py` | A +244 | 七支一次性驗證腳本 |
| `.../evidence/trial-2026-09-1{6,7,8}.txt` | A +12 | `check_trial.py` 的歸檔輸出 |
| `.../evidence/ac1-2305-0916-close-auction-head-and-bands.png` | A (binary) | AC1 截圖 |

## 發現總覽的排序與欄位

排序依 最終建議 group(Must Fix → Should Fix → Nice to Have → 參考用),group 內保留 finding 編號序;severity 只在格內顯示,不驅動排序。

本輪只有一個 review 軸,故表格退化為 `CC`(first-pass severity)+ `複查`(Step 4.2 替代 pass 的 verdict 與校正 severity)兩欄。

## 發現總覽

| # | 問題 | CC | 複查(獨立 CC 稽核,同軸) | 最終建議 | Action | Action 理由 |
|---|---|---|---|---|---|---|
| 1 | 「段的界」把 `trial` / `auction` 互斥寫成不變量,程式沒保證,PR 自己的測試就造得出反例 | MED | CONFIRMED(MED→MED) | Should Fix | `ask-user` | 兩條修法方向不同(降級成實測陳述 vs 真的加守門+測試),要你拍板 |
| 2 | `docs/next-time.md:36` 還寫「外掛檔 v3、回看頁讀 v2 / v3」;round-1 自述「已 grep 確認全庫零殘留」不準確 | MED | CONFIRMED(MED→**LOW**) | Nice to Have | `auto-fix` | 一行字面,契約 SoT 已正確,零執行路徑受影響 |
| 3 | round-1 記帳「收修 8」把一條零動作的 F-scope 算進去 | LOW | CONFIRMED(LOW) | Nice to Have | `no-op` | 凍結的審查紀錄,改它等於竄改歷史;記在本報告即可 |
| 4 | AC4 證明腳本 `payload_diff.py` 的 exit code 沒蓋住報告真正引用的那一行 | MED | CONFIRMED(MED→**LOW**) | Nice to Have | `auto-fix` | 一行 `or removed or changed`,結論本身沒錯 |
| 5 | 同檔 docstring 寫「逐位元組相同」但實際比語意相等;`tot` 是死變數 | LOW | CONFIRMED(LOW) | Nice to Have | `auto-fix` | 用詞校正 + 刪死碼 |
| 6 | `check_trial.py` 盤中段樣本截在 8 筆,存檔看不出被截掉約 97% | LOW | PARTIAL(LOW) | Nice to Have | `auto-fix` | (a)(c) 成立、(b) 被反駁;補「(前 8 筆,共 n 筆)」與除零早退 |
| 7 | `close_pile.py` 只量收盤窗 + 只讀簿 parquet,但它撐的宣稱是「**段內**單格最大」 | LOW | PARTIAL(LOW) | Nice to Have | `auto-fix` | 數字經我重量後正確,缺的是證據涵蓋面;補跑歸檔、**不動任何數字** |
| 8 | 三支腳本的 stdout 沒歸檔,而其數字進了永久文件;簿 parquet 只留 120 交易日 | LOW | CONFIRMED(LOW) | Nice to Have | `auto-fix` | 各只有幾行,補存即可 |
| 9 | 簿存檔上線後、只是還沒跑 `book-replay` 的日子,會被解釋成「達錢歷史 TICKS 不含五檔」(假陳述) | LOW | CONFIRMED(LOW) | Nice to Have | `ask-user` | 要加第三種文案 = 新行為,且在 #273 AC 之外 |
| 10 | `p.trial` 不是陣列時靜默當空集合,與同函式其他欄位的 fail-loud 不一致 | LOW | CONFIRMED(LOW) | Nice to Have | `auto-fix` | 加一個 Array.isArray 守衛即可 |
| 11 | 無簿日 + 重播分頁開著時,鍵盤 ← → 完全沒反應 | LOW | PARTIAL(LOW) | Nice to Have | `ask-user` | 「換日」與「直接 return」兩種修法行為不同 |
| 12 | 五條限制兩份副本、第②條已分岐 | LOW | CONFIRMED(LOW) | Nice to Have | `no-op` | AC5 已滿足,兩份刻意一詳一簡 |
| 13 | `content:"集合競價"` 是第 4 份字面且 JS 摸不到;`::after` 不是說明寫的「右上」 | LOW | CONFIRMED(LOW) | Nice to Have | `auto-fix` | 說明文字與實作對齊 |
| 14 | 新 fixture 自稱 7772 實錄但形狀不符,且靜默造出 #1 的反例卻零斷言 | LOW | CONFIRMED(LOW) | Nice to Have | `ask-user` | 修法綁在 #1 的拍板上 |
| 15 | `assert wire["v"] == 4` 把同一份 diff 才剛拿掉的版本字面加回來 | LOW | CONFIRMED(LOW) | Nice to Have | `auto-fix` | 刪一行 |
| 16 | `verification.md:72`「檔案大小完全相同」為假,與同 PR 的 CLAUDE.md 互斥 | LOW | CONFIRMED(LOW) | Nice to Have | `auto-fix` | 已有實測位元組數可填 |
| 17 | 三支證據腳本把 `sys.path` 釘死在已不存在的 worktree | LOW | PARTIAL(LOW) | 參考用 | `no-op` | baseline:repo 內另有 6 處同款長年未爆;fallback 落到同一份 v4 code |
| 18 | blob 解碼區塊在兩支腳本整段複製 | LOW | PARTIAL(LOW) | 參考用 | `no-op` | baseline:同段碼在 8 個 evidence 目錄被抄過 14 份,是本 repo 明確做法 |
| 19 | 誤設狀態(`bookdays` 空)的分頁樣式與良性狀態相同 | LOW | PARTIAL(LOW) | 參考用 | `no-op` | 「大聲」的通道是面板文案(已真環境驗過),且誤設時**每一天**都灰 = 第二個區別訊號 |
| 20 | `trial` 與 `trialRuns` 是同一事實的兩份表示 | LOW | PARTIAL(LOW) | 參考用 | `no-op` | 同一迴圈導出、不會不同步;兩個讀者需求本就不同 |
| 21 | `.rp-bands` 的 `8px` 是綁死 UA thumb 尺寸的魔術數字 | LOW | PARTIAL(LOW) | 參考用 | `no-op` | 次像素級視覺偏差;旁邊有 title 與「第 n / m 則」兩個精確讀數兜底 |
| 22 | `RP_QMAX_END` 的理由被本 PR 自己的事實打穿(處置股整天在段內) | LOW | PARTIAL(LOW) | 參考用 | `no-op` | 明確在 #273 AC 之外;是 next-time 素材,不是本 PR 的債 |
| 23 | 非整數 `trial` 丟裸 `TypeError` 而非 `PluginFormatError` | LOW | **REFUTED**(LOW) | 參考用 | `no-op` | `decode` docstring 同段最後一行已明文豁免型別檢查,承諾與實作一致 |
| 24 | `trial` 用區間而非既有的「遞增則號清單」慣例 | LOW | **REFUTED**(LOW) | 參考用 | `no-op` | reviewer 自己判 keep,而其唯一行動建議(補 docstring 說明)原文已存在 |
| 25 | `CONTEXT.md` 沒跟上 F-1 的「兩條義務」拆分 | LOW | PARTIAL(LOW) | 參考用 | `no-op` | 留的是 F-1 判定中較強的那側;glossary 本就是摘要體 |

auto-fix 只是處置建議；沒有使用者另行下令，不修改 code、commit、push 或 PR。

F-01 finding_uid: 567969df50535eabb244 action=ask-user
F-02 finding_uid: 4c16567868297a5fb156 action=auto-fix
F-03 finding_uid: fd7be86f5642e3def16c action=no-op
F-04 finding_uid: 592be6d7ff00a4581dd5 action=auto-fix
F-05 finding_uid: a3d5bb2b5458c6c81788 action=auto-fix
F-06 finding_uid: 5ba21972c41ffec0668f action=auto-fix
F-07 finding_uid: ebc19ce34ced3e3dfd8f action=auto-fix
F-08 finding_uid: b0c236b5b88a6ce586bd action=auto-fix
F-09 finding_uid: b7d72fa711fd19532d55 action=ask-user
F-10 finding_uid: 9931d0f4bac94e2ee6af action=auto-fix
F-11 finding_uid: 8fedcc305938336455ab action=ask-user
F-12 finding_uid: f8643b01d5621b0c2b96 action=no-op
F-13 finding_uid: ba451dba857ccf3e18c1 action=auto-fix
F-14 finding_uid: f2b9e78ca0587e27bda9 action=ask-user
F-15 finding_uid: 4c6ddf1f534dc73c2379 action=auto-fix
F-16 finding_uid: 376c9878711406b1b3b7 action=auto-fix
F-17 finding_uid: b4ccef57ff77f5c2eb6e action=no-op
F-18 finding_uid: c6f3e974f21a35e3a8e7 action=no-op
F-19 finding_uid: fe579e2325aad5267382 action=no-op
F-20 finding_uid: dc8c6adbe71cdc9e259e action=no-op
F-21 finding_uid: bdb9f69f3d29c0ef1050 action=no-op
F-22 finding_uid: c2c29009cdd62c779d74 action=no-op
F-23 finding_uid: 2cb006114d6939b8d6fb action=no-op
F-24 finding_uid: aeb85acad07c192df12d action=no-op
F-25 finding_uid: e895a9b8edc2fa3aea2e action=no-op

### Inline Comments per Finding

#### #1 「段的界」寫成規則,但程式沒保證,而且這個 PR 的測試自己就造得出反例

**File**: `copycat/book_replay.py`
**Line**: 64

**Comment**:
```
模組說明新加的這句把 trial 跟 auction 講成互斥:

  **段的界**:段 = 試撮中的那些則;撮出來的那一筆成交狀態已回正常盤,**不在段內**(它在 auction)。

但兩個判準彼此獨立 —— Frame.trial 讀「這一則自己」的 trade_status(:472),
_auction_match 讀「前一則」是不是試撮簿(:782-796)。一則成交同時滿足兩者完全合法。

實跑本 PR 新測試 test_a_late_delayed_match_trade_carries_the_trial_flag_itself 的那兩列:
第 1 則拿到 trial=True 且 auction=True,encode 吐 trial=[0,1] / auction=[1] —— 色帶會蓋到
那一筆「集合競價撮合」,跟這句話直接打架。

三天正式外掛檔實測 auction 共 1,169 筆、落在段內 0 筆,所以今天為真;但沒有任何東西擋它變假,
而 #271 的實作者正被上面 :58-62 指到這裡。同一份斷言也在 CONTEXT.md:282-283 與回看頁
「定義與規則」(使用者看得到的那句「所以它不在色帶裡」)。

兩條路擇一,三處要一起改:
(a) 降級成實測陳述 —— 「兩個旗標各自獨立;實測 09-16~18 共 1,169 筆 auction 無一在段內」;
(b) 真的當不變量 —— 在 _frames 或 _check_header 加一條守門 + 一條測試釘住。
```

#### #2 `docs/next-time.md` 的盤後手順還寫著 v3

**File**: `docs/next-time.md`
**Line**: 36

**Comment**:
```
第 1 步的註記還是「2026-09-18 起外掛檔 v3、回看頁讀 v2 / v3」,但這個 PR 已經升 v4、
CLAUDE.md:128 也改成「回看頁讀 v2 / v3 / v4」了。這行是你每個交易日盤後照著跑的 runbook,
掛的日期又剛好跟本 PR 同一天,讀的人分不出它已經過期。

改成「外掛檔 v4、回看頁讀 v2 / v3 / v4」就好。

另外 code-review-round-1.json 的處置寫 A-1「已 grep 確認全庫零殘留」—— 那次 grep 實際只掃了
copycat/,這行就是漏網的。之後這類自述把範圍寫清楚(掃了哪幾個目錄)。
```

#### #3 round-1 的「收修 8」把一條零動作的算進去了

**File**: `.claude/feat/book-replay-auction-segment/code-review-round-1.json`
**Line**: 84

**Comment**:
```
disposition 寫「收修 8 條,反駁 1 條,不動 2 條」,但【收修】區塊裡的 F-scope 內文是
「reviewer 自評不退回,同意」= 零動作,真正動手的是 A-1 / B-4 / F-1 / F-2 / F-3 / F-4 / F-5 共 7 條。
總數 11 沒錯,只是拆法不對(正確是 7 修 + 1 同意不動 + 1 反駁 + 2 不動),verification.md §4.5 也照抄了。

這份是已凍結的審查紀錄,我的建議是**不要回頭改**(改它等於竄改歷史),記在這裡就好,
下次寫 disposition 時注意「同意不退回」不算收修。
```

#### #4 AC4 的證明腳本,exit code 沒蓋住報告真正引用的那一行

**File**: `.claude/feat/book-replay-auction-segment/evidence/payload_diff.py`
**Line**: 41

**Comment**:
```
raise SystemExit(1 if diff else 0) 只反映 per-old-day 那個迴圈;上面算的
added / removed / changed 三條只 print 不進 exit code。而 verification.md §4 拿來當 AC4 證明的
正是印出來的那句「值變了的鍵: []」。

另外迴圈只走 before["d"],只在 after 出現的舊股票日永遠不會進 diff。

這次的結論沒問題(兩行都印出來、人眼判讀過),問題是這支日後當回歸 gate 重跑時,
d 被動到或 bookdir / bookdays 被刪鍵,它照樣 exit=0。

raise SystemExit(1 if (diff or removed or changed) else 0)

added 不進 gate 是對的 —— 新增鍵是這次刻意的。
```

#### #5 同一支的 docstring 說「逐位元組」,實際比的是語意

**File**: `.claude/feat/book-replay-auction-segment/evidence/payload_diff.py`
**Line**: 1

**Comment**:
```
docstring 寫「必須逐位元組相同」,但兩邊都先經 payload_dump.py 的
json.dumps(sort_keys=True, indent=0) 正規化再 json.loads 回來比 —— 比的是語意相等。

以 AC4(內外盤判定未被更動)來說語意相等才是對的尺,所以結論不受影響,只是用詞過強。
改成「語意逐鍵相同」。

順手:tot 跟 old_days 每次同步 +1、最後只用 old_days,tot 是死變數,刪掉。
```

#### #6 盤中段樣本截在 8 筆,存檔看不出被截掉多少

**File**: `.claude/feat/book-replay-auction-segment/evidence/check_trial.py`
**Line**: 50

**Comment**:
```
elif len(only) or len(intraday) < 8 —— 印出來的「盤中段樣本」上限 8 筆,而
trial-2026-09-16.txt 剛好列滿 8 筆。實際盤中段數是 311 / 260 / 445(09-16 / 17 / 18),
也就是截掉約 97%,單看存檔完全看不出來。

§3 的敘述本身沒被傷到(2305 那三段都在前 8 筆內、行首也寫著「樣本」),但補一句就不會有人誤讀:

  print("   盤中段樣本(前 8 筆,共 " + str(n) + " 筆):" + ...)

另外 :60 的 trial_msgs / total_msgs 在目錄空或日期打錯時會 ZeroDivisionError,前面早退一下。

(原本還提「close_start 是 set 會吃掉檔數」—— 那條查下來不成立,數檔的是另一個計數器
with_close,close_start 只餵「該段起點」那行,沒有任何地方拿它數檔。)
```

#### #7 這支只量收盤窗,但它撐的那句話說的是「段內」

**File**: `.claude/feat/book-replay-auction-segment/evidence/close_pile.py`
**Line**: 22

**Comment**:
```
腳本 gate 在 (tm.hour, tm.minute) < (13, 25) 且只讀 <日>-book.parquet,可是它產出的數字被寫進
book_replay.py:56-57 的永久模組說明時,措辭是「**段內**單格最大 5314 賣一 47,033 張」——
而「段」照本 PR 自己的定義含處置股整天分盤、盤中暫緩撮合,也含帶試撮狀態的**成交**列。
兩個窄化都在量測端,宣稱端沒有。

先講結論:**數字是對的,不要改**。我按完整段定義重量過(拿掉 13:25 閘、成交 parquet 也掃):
  09-16 47,033(5314 askq0 @13:29:43)/ 09-17 27,806 / 09-18 29,675 —— 與 docstring 逐字相同。

但 09-18 差點就錯了:13:25 **前**的段內最大是 29,300(2303),全段最大 29,675,只差 375 張。
所以缺的是證據涵蓋面,不是數字。修法是把腳本的兩個窄化拿掉重跑一次、把輸出歸檔,
順便把「13:25 前段內最大 37,845 / 8,140 / 29,300」記進去 —— 那個窄裕度值得留在紀錄裡。
```

#### #8 三支腳本的輸出沒歸檔,而數字已經進了永久文件

**File**: `.claude/feat/book-replay-auction-segment/evidence/close_pile.py`
**Line**: 29

**Comment**:
```
evidence/ 只歸檔了 check_trial.py 的三份 trial-*.txt。close_pile.py(47,033 / 27,806 / 29,675,
進了 book_replay.py 模組說明與回看頁「定義與規則」)、no_close.py(§3 那 5 個檔日)、
merged_run.py(§4.5 那 7 個檔日)都只有腳本沒有輸出。

要緊的是 close_pile.py 吃的簿 parquet **只留 120 交易日**,過期之後這幾個數字就永久不可重驗了。
三支的 stdout 各只有幾行,比照 trial-*.txt 一起存進去。
```

#### #9 簿存檔上線後、只是還沒跑 book-replay 的日子,會被講成「達錢歷史 TICKS 不含五檔」

**File**: `.claude/feat/book-replay-auction-segment/evidence/build_viewer_cdp.diff`
**Line**: 10

**Comment**:
```
bookdays 是「資料夾存在且至少有一支 .js」。F-3 的收修已經把「全部掃不到」三態化成 fail-loud,
但**單日**缺檔還是落回那句「這天沒有五檔簿(達錢歷史 TICKS 不含五檔)」——
對 09-16 之後、外掛檔被誤刪或還沒重產的日子,那是假陳述,而且零錯誤訊號。

觸發路徑不是假設性的:docs/next-time.md 記著每個交易日盤後要手動跑,book-replay 是第 1 步,
09-17 第一次實跑就漏過步。緩解是同一句尾端會印「目前 n 天」,自己看得出來。

要收的話:以 max(bookdays) 為界,界後卻不在 bookdays 的交易日印第三種文案
(「這天應該有簿但沒掃到,重跑 book-replay」),與既有的 rpNoBookDir 同形。

這是新行為、又在 #273 的 AC 之外,所以先問你要不要做。
```

#### #10 `p.trial` 不是陣列時會靜默當成「沒有段」

**File**: `.claude/feat/book-replay-auction-segment/evidence/viewer_cdp_template.273.html`
**Line**: 639

**Comment**:
```
const trialFlat = p.trial || [] 之後只驗 .length % 2。萬一 p.trial 是物件,
undefined % 2 = NaN(falsy)→ 過關,迴圈條件 0 < undefined 為 false → 直接得到
trial 全 0、trialRuns 空,畫面完全正常、只是沒有橘色帶。

同一個函式對 p.chg / p.eat / p.d[i] 都寫了 Array.isArray,p.anomalous / p.auction / p.stale 走
new Set(...) 對非 iterable 會 throw 被接成「簿重播檔解不開」—— 只有 trial 這個新欄位會無聲退化,
而無聲退化的後果正好是 #273 要防的那件事(把集合競價堆量讀成盤中墊單)。

實務觸發率約等於零(產生端恆吐 list,落檔前還有 Python decode 自檢),但修法只要一個 ||:

  if(!Array.isArray(trialFlat) || trialFlat.length % 2) bad(...)
```

#### #11 無簿的日子按 ← → 完全沒反應

**File**: `.claude/feat/book-replay-auction-segment/evidence/viewer_cdp_template.273.html`
**Line**: 906

**Comment**:
```
重播分頁開著時全域 keydown 會走 rpKey,而 rpKey 是先 e.preventDefault() 再 if(RP) rpGo(...)。
無簿日 renderReplay 早退前已經把 RP = null,所以左右鍵既不逐則步進、也不換日,零回饋。

2026-09-16 之前的每個交易日都是這個狀態 —— 這個 PR 之後它從「載入失敗的例外」變成「設計內的常態」。
(行為本身 PR 前就存在;新文案指的是上方 ◀ ▶ 與日期選單,那兩個都正常,所以不是文案的問題。)

兩種修法行為不同,你挑:
  (a) if(!RP) return;            → 不吃掉按鍵,讓瀏覽器 / 其他 handler 照常
  (b) 退回換日 stepDay(...)      → 無簿日的 ← → 直接變成換日
```

#### #12 五條限制有兩份,第②條已經開始分岐

**File**: `.claude/feat/book-replay-auction-segment/evidence/viewer_cdp_template.273.html`
**Line**: 845

**Comment**:
```
重播面板的 <details> 與「定義與規則」:221 各有一份五條限制,現在第②條已經不一樣了:
面板版是「五檔視野外完全看不到:被擠出第五檔之後,那個價位的掛單通常還在,只是這裡沒有數字」,
分頁版只剩前半句。

AC5 只要求頁面寫出五條,兩份都寫了,而且長短不同看得出是刻意(一份精簡一份展開),
所以我不建議動。留這條只是把「改文字時要改兩處」記下來 —— 分頁版結尾已經有交叉引用了。
```

#### #13 說明寫「右上」,實際不是;而且這是第 4 份字面

**File**: `.claude/feat/book-replay-auction-segment/evidence/viewer_cdp_template.273.html`
**Line**: 90

**Comment**:
```
兩件小事:

1. .rp-msg-h 是 display:flex 沒有 justify-content,所以 ::after 產生的內容是最後一個 flex item,
   緊接在「第 n 則 / HH:MM:SS 收到 / 成交 …」後面,不是貼齊右緣。但「定義與規則」:219 寫的是
   「中間欄每則**右上**的『集合競價』」。想讓文件為真就加 margin-left:auto,不然把「右上」改掉。

2. content:"集合競價" 是這個詞的第 4 份字面(另三處:頁頭 chip、色帶 title、說明列),
   而且藏在 CSS、JS 讀不到 —— 本家族驗收慣用的 DOM 腳本(dom_regression.mjs 那種)抓不到它,
   改稱呼時最容易漏掉這一份。
```

#### #14 這個 fixture 自稱是 7772 實錄,但形狀跟實錄不一樣,而且順手造出了 #1 的反例

**File**: `tests/test_book_replay.py`
**Line**: 1336

**Comment**:
```
docstring 引 7772 於 2026-09-16 當實錄,但正式外掛檔解出來是 kind="ttb"、trial=[0,0,2,2]、
auction=[] —— 第 0 則本身就是 trial 成交。fixture 則排成「試撮簿 → 試撮成交」,
這讓那一則同時滿足 _auction_match。

docstring 要證的核心事實(成交列自己可以帶試撮旗標)在真資料裡成立,被虛構的是前面那一則試撮簿。
而這一排正好構造出 #1 講的 trial ∧ auction,測試卻對 auction 零斷言 —— 等於把那個不變式的破口
寫進 fixture 又不記帳。

兩條路(跟 #1 一起決定):
(a) 忠於實錄:前一則改成成交則,trial 仍是 [True, True] 而 auction 為 False;
(b) 保留現況,加一行 assert frames[1].auction is True 並在 docstring 點明「兩個判準獨立」。
```

#### #15 同一份 diff 才剛拿掉版本字面,新測試又加回來

**File**: `tests/test_book_replay.py`
**Line**: 1378

**Comment**:
```
這個 diff 把 TestAuctionMatch 裡的 assert wire["v"] == 3 刪掉(對的 —— 版本字面只該留在 golden
字面測試),卻在新測試加了 assert wire["v"] == 4。
test_payload_layout_matches_the_documented_v4_literal 已經釘了 "v": 4。

刪掉這一行就好,這個測試的重點是 wire["trial"] == [1, 3] 跟 round-trip。
```

#### #16 「檔案大小完全相同」是假的,而且跟同一個 PR 的 CLAUDE.md 打架

**File**: `.claude/feat/book-replay-auction-segment/verification.md`
**Line**: 72

**Comment**:
```
§3 寫「則數與檔案大小與 v3 **完全相同**」,但 round-1 的 F-5 已經把 CLAUDE.md 改成
「則數不變、檔案大小在 0.1 MB 解析度下看不出差別(trial 陣列非零長)」—— 同一個 PR 的兩份文件
對同一件事給不同說法,而 verification.md 是後人重跑對帳的基準。

我逐檔加總量過:
  09-16  36,427,224 → 36,430,524 B(+3,300)
  09-17  49,219,248 → 49,222,292 B(+3,044)
  09-18  49,619,680 → 49,623,856 B(+4,176)

改成跟 CLAUDE.md 同口徑,順便把這三個數字寫進去 —— 現在有實測值了,
免得下次 bump 的人把 +3 KB 當成回歸去追。
```

#### #17 證據腳本把 sys.path 釘死在已經不存在的 worktree(不是 PR 缺陷)

**File**: `.claude/feat/book-replay-auction-segment/evidence/check_trial.py`
**Line**: 10

**Comment**:
```
這條複查下來**不建議改**。事實面都對:那個 worktree 已經不在、Python 對不存在的 sys.path 靜默略過、
repo 內確實有更好的寫法(.claude/bug/pr-275-review-followups/evidence/ 用
Path(__file__).resolve().parents[4],而且對這兩種版面深度都正確)。

但同款站點 repo 內另有 6 處(pr-279-review-followups/compare_v2_v3.py、discord-watchlist、
group-grid、signal-rules、stkfut-contracts × 2),全部釘著早就消失的 worktree、長年未爆;
而且 fallback 會 import 到主 tree 的同一份 v4 code,重跑結果不變。

沒有「為什麼這支會炸、那六支不會」的實質差異 —— 要收就整批收,不該只挑本 PR 這三支。
```

#### #18 blob 解碼區塊重複(不是 PR 缺陷)

**File**: `.claude/feat/book-replay-auction-segment/evidence/payload_dump.py`
**Line**: 14

**Comment**:
```
這條複查下來**不建議改**。payload_dump.py 與 make_empty_bookdays.py 確實是同一段
read + regex + b64decode + gunzip + json.loads(regex 字面一模一樣),但同一段解 blob 的碼
在本 repo 已經被抄了 14 份、橫跨 8 個 evidence 目錄,從來沒被要求收攏 ——
凍結的證據目錄各自自足是這裡明確的做法。

唯一順手的是 make_empty_bookdays.py:15 的裸 assert m 沒有訊息(姊妹那支有寫),
但兩者都會帶行號 traceback 大聲炸,實質影響為零。
```

#### #19 誤設狀態的分頁樣式跟良性狀態一樣(結論不成立)

**File**: `.claude/feat/book-replay-auction-segment/evidence/viewer_cdp_template.273.html`
**Line**: 799

**Comment**:
```
這條複查下來**不成立,不用改**。b.classList.toggle("dim", !on) 只吃 rpHasBook() 是事實,
兩種狀態的分頁鈕樣式確實一樣;但「fail-loud 被安靜退回」的結論不對:

- 大聲說的通道是面板文案 —— rpNoBookDir() 分支印的是「**一個簿重播外掛檔都沒掃到 —— 這是設定壞了,
  不是本來就沒有**」+ 可行動的診斷,跟良性態那句「不是故障」完全不同段,而且 round-1 F-3
  的真環境重驗測的正是這一句。
- 還有第二個區別訊號:設定壞掉時**每一天**都灰,正常時只有 09-16 之前的日子灰。
```

#### #20 `trial` 與 `trialRuns` 兩份表示(結論不成立)

**File**: `.claude/feat/book-replay-auction-segment/evidence/viewer_cdp_template.273.html`
**Line**: 920

**Comment**:
```
這條複查下來**不用改**。兩者是同一個迴圈由同一份 trialFlat 導出的,不是兩份可能不同步的狀態;
而且兩個讀者的需求本來就不同 —— rpChanges 要的是「這一則在不在段內」(O(1) 陣列剛好),
rpDraw 要的是段邊界(印「第 n / m 則」、算段名、畫色帶),非拿 run 不可。

R.trialRuns.length 那個守衛只是「整份沒有段就不用掃」的快門,而 rpTrialRun 本來就在不在段內時回 null,
語意等價;換成 R.trial[i] 只是微優化,零正確性差異。段數規模也有限(單檔最多 132 段)。
```

#### #21 `.rp-bands` 的 8px 魔術數字(不建議改)

**File**: `.claude/feat/book-replay-auction-segment/evidence/viewer_cdp_template.273.html`
**Line**: 86

**Comment**:
```
這條是純視覺、**不建議改**。left:8px;right:8px 確實是「假設 range thumb 寬 16px」的硬編,
色帶與拇指中心會有次像素級偏差(1200px 軌道上約 0.2%)。

但旁邊有兩個精確讀數兜底:色帶的 title 與頁頭的「收盤集合競價 第 n / m 則」。
極端值也沒問題:span <= 0 時 rpBands 直接回空字串不畫,單則段靠 min-width:2px 仍看得見。

(原 finding 說「Chromium UA stylesheet 另加 margin:2px、其他瀏覽器不同」—— 那是第三方平台行為,
本輪禁外部查詢、本機也驗不了,列為未證實。)

真要動,最小的是把 8px 的由來寫成一行註解,免得下一個人以為是隨手的 padding。
```

#### #22 `RP_QMAX_END` 的理由被這個 PR 自己的事實打穿(next-time 素材)

**File**: `.claude/feat/book-replay-auction-segment/evidence/viewer_cdp_template.273.html`
**Line**: 593

**Comment**:
```
這條**不是本 PR 的債**,記下來免得忘記。

RP_QMAX_END = 13:25 的用意是「別讓收盤集合競價的排隊量把盤中橫條壓扁」。但這個 PR 自己確立了
處置股整天都在分盤撮合(09-16 的 4979 全日 132 段)—— 對這幾檔,13:25 **之前**的 qmax 本身
就取自競價堆量,橫條整天被壓扁,正好是這顆常數想避免的失真。

(頁面說明沒有說錯 —— 它寫的「13:25 前最大單格量」就是實際算法。)

trial 進來之後,recv[i] < RP_QMAX_END 可以直接換成 !trial[i],定義從「時鐘窗」升級成
「不是集合競價的則」。明確在 #273 的 AC 之外,適合進 next-time。
```

#### #23 非整數 `trial` 丟裸 TypeError(已被原文豁免,不是缺陷)

**File**: `copycat/book_replay.py`
**Line**: 1354

**Comment**:
```
這條複查下來**被反駁,不用改**。型別洞是真的(實跑:["1",3] → TypeError、[None,3] → TypeError、
[1.0,3.0] 在 _check_trial_ranges 完全不報、到 decode 的切片才炸),姊妹欄位 anomalous /
auction / stale 同病 —— 這部分 round-1 的反駁成立。

決定性的反證是:decode 的 docstring 最後一行逐字寫著「**值的型別(例如該是整數的地方放了字串)
不在檢查範圍。**」,跟上面那句「不合格一律 PluginFormatError」相距 13 行、明確劃了範圍。
承諾與實作一致,沒有洞。
```

#### #24 `trial` 用區間而非索引清單(建議的動作原文已存在)

**File**: `copycat/book_replay.py`
**Line**: 870

**Comment**:
```
這條複查下來**被反駁,不用改**。原 finding 自己做完 deletion test 就判「留」(回看頁真的需要
「段」這個單位:rpBands 逐段畫色帶、rpTrialRun 算「第 n / m 則」),唯一的行動建議是
「補一行 docstring 說明為何用區間」——

而那句話原文已經有了:模組說明 :89-90 的 trial 條目寫著「回看頁靠它在時間軸上畫色帶、
在畫面上標『集合競價』」,_trial_ranges docstring 也寫了「每段極大化,所以相鄰兩段不會並存」,
prev_end = -2 哨兵的語意由錯誤訊息「相鄰或重疊的段要併成一段」說明。零殘留動作。
```

#### #25 `CONTEXT.md` 沒跟上 F-1 的兩條拆分(留的是較強的那側)

**File**: `CONTEXT.md`
**Line**: 287

**Comment**:
```
這條**不建議改**。CONTEXT.md 確實只寫「厚檔事件整段排除」、沒有 book_replay.py:58-62 的
「不產生 / 不污染結局」兩條拆分,但它留的是 round-1 F-1 判定中**較強**的那一側(整段排除),
不是被判不足的那側(只擋產生)。

glossary 條目本來就是摘要體 —— 相鄰的「集合競價撮合」條同樣是模組說明的縮寫版;
完整兩條另存在 book_replay.py:58-62、verification.md §5,以及已貼到 #271 的 issue 留言。

想更保險的話,在 CONTEXT.md 該句尾端加「(兩件都要做,詳見 book_replay.py 模組說明)」即可。
```

## CC 原始 findings(first-pass,context-aware,chunked ×3)

三個 `python-reviewer` 實例各自只看自己的 chunk,互不知道彼此存在。逐條原文與 search-proof 見上方
「Inline Comments per Finding」與下方「複查結果」表;此處記錄原始 severity 與來源:

- **chunk 1**(13 檔,evidence 腳本與審查紀錄)— 10 findings:MEDIUM ×2(C1-1 / C1-3)、LOW ×8。
  該實例額外逐項核對了可交叉驗證的數字(trial-*.txt 三組數字與 verification.md §3 逐字相符、
  截圖內字串與色帶百分比換算回時刻與 trial-2026-09-16.txt 的 2305 四段逐一對上),**未發現假證據**。
- **chunk 2**(1 檔,回看頁模板歸檔副本)— 8 findings:LOW ×6、參考用 ×2,**0 CRITICAL / 0 HIGH / 0 MEDIUM**。
  該實例主動追蹤後駁回了三項被指派的疑慮(rpTrialRun 非 hot path、esc() 無漏、color-mix 降級可接受)。
- **chunk 3**(6 檔,引擎 + 測試 + 文件)— 9 findings:MEDIUM ×1(C3-1)、LOW ×8。
  該實例以三天 246 個正式外掛檔重算了本 PR 文件裡的每一個數字,**全部逐字對上**;
  另實跑 ruff 與 `pytest -k "AuctionSegment or AuctionMatch or v4"`(18 passed)。

## Codex 原始 findings(first-pass,diff-only)

**N-A** —— 本機未安裝 `codex` CLI,中性軸與對抗軸皆未執行。

## CC 對 Codex 的複查結果(Step 4.1)

**N-A** —— 無非 CC 軸 finding 可複查。

## Codex 對 CC first-pass 的複查結果(Step 4.2,本輪以獨立 CC 稽核 agent 替代)

⚠️ **這是同軸複查,不是 cross-axis 證據。** 稽核 agent 未參與 first-pass、未看過其他 chunk 的輸出,
並套用了同一套四測(exploitation / impact / baseline-comparable / mitigation),因此擋得住 over-flag;
但它與 first-pass 同屬 CC 家族,擋不住「兩個同型 reviewer 犯同一種錯」。

批次驗收:輸入 25 條、輸出 25 條,ID 集合逐一相等、無缺漏 / 未知 / 重複,每列 `verdict` /
`corrected_severity` / `severity_reason` / `evidence` 四欄齊備 → 批次接受(非 INCONCLUSIVE)。

| # | 原 severity | Verdict | 原 → 校正 | 稽核證據摘要 |
|---|---|---|---|---|
| 1 (C3-1) | MED | CONFIRMED | MED→MED | 兩述詞逐行確認獨立(:472 vs :782-796);三天 246 檔實測 auction 1,169 筆、段內 0 筆 → 今天為真但未強制;PR 自己的 fixture 已測得同一則 trial ∧ auction |
| 2 (C1-1) | MED | CONFIRMED | MED→**LOW** | `git diff --stat` 確認 docs/next-time.md 不在 PR 內;全庫 grep 只剩該行(+ 一處凍結紀錄);契約 SoT 已正確、零執行路徑受影響 |
| 3 (C1-2) | LOW | CONFIRMED | LOW | 逐條核對:7 條有具體改動可在 diff 內對到,F-scope 純同意零動作 |
| 4 (C1-3) | MED | CONFIRMED | MED→**LOW** | :41 只吃 `diff`;:24 只走 before 側。緩解:verification.md:121-123 同時引了印出的兩行與 exit=0,該行被人眼判讀過 |
| 5 (C1-4) | LOW | CONFIRMED | LOW | dump 端 `sort_keys=True` 正規化 → 比語意;`tot` 於 :22 初始化、:30 自增、輸出從未讀 → 死碼 |
| 6 (C1-6) | LOW | PARTIAL | LOW | (a) 為真且比 finding 想的嚴重(實測盤中段 311/260/445,存檔各印 8 → 截掉約 97%),但行首自稱「樣本」、被引用那顆沒被截;(b) **反駁**:數檔的是 `with_close` 不是 `close_start`;(c) 為真 |
| 7 (C1-7) | LOW | PARTIAL | LOW | 涵蓋面窄於陳述成立;但主 session 以完整段定義重量得 47,033 / 27,806 / 29,675,與 docstring 逐字相同 → **陳述為真**;09-18 最高級只以 375 張成立,值得寫進證據 |
| 8 (C1-8) | LOW | CONFIRMED | LOW | `ls evidence/` 只有三份 trial-*.txt;數字進了 book_replay.py:56-57 與 verification.md;baseline 為「多數遵守」(同家族亦有未歸檔案例) |
| 9 (C1-10) | LOW | CONFIRMED | LOW | 觸發性比 finding 說的高(盤後手動四步、book-replay 是第 1 步、09-17 實跑漏過步);損失限於一句誤導文案,同段另印「目前 n 天」可自行察覺 |
| 10 (C2-1) | LOW | CONFIRMED | LOW | 機制逐行確認;姊妹欄確實 fail-loud(:630 / :632 / :636);產生端受 TypedDict 與落檔前 decode 自檢兩層保護 → 觸發率約等於零 |
| 11 (C2-3) | LOW | PARTIAL | LOW | 方向鍵無作用逐行追過為真;但「與新文案互動」那半**反駁** —— 文案指的是上方按鈕,兩者都正常可用 |
| 12 (C2-6) | LOW | CONFIRMED | LOW | 已分岐處鎖定在第②條(面板版多了「被擠出第五檔之後…」的解釋句);分頁版結尾自帶交叉引用 |
| 13 (C2-8) | LOW | CONFIRMED | LOW | 第 4 份字面且 ::after 不進 textContent → 本家族慣用的 DOM 驗收腳本抓不到;`.rp-msg-h` 無 justify-content → 確實不貼右緣 |
| 14 (C3-4) | LOW | CONFIRMED | LOW | 解出正式外掛檔:7772 09-16 為 kind="ttb"、trial=[0,0,2,2]、auction=[];fixture 形狀不同且對 auction 零斷言 |
| 15 (C3-5) | LOW | CONFIRMED | LOW | diff 內同時看得到 `- assert wire["v"] == 3` 與 `+ assert wire["v"] == 4`;正主是 golden 字面測試 |
| 16 (C3-8) | LOW | CONFIRMED | LOW | 兩份文件字面互斥;主 session 實測三天各 +3,300 / +3,044 / +4,176 B → 「完全相同」為假 |
| 17 (C1-5) | LOW | PARTIAL | LOW | 三項事實全為真、前例確實存在且 `parents[4]` 深度對;**但** repo 內另有 6 處同款釘死已消失 worktree、長年未爆 → baseline 無實質差異 |
| 18 (C1-9) | LOW | PARTIAL | LOW | 重複為真;**但** `grep -rln 'script id="blob"' .claude/` 共 14 檔橫跨 8 個 evidence 目錄 → 凍結證據各自自足是本 repo 明確做法 |
| 19 (C2-2) | LOW | PARTIAL | LOW | 樣式相同為真;**但**「fail-loud 被安靜退回」不成立 —— 面板文案才是大聲通道(F-3 真環境驗過),且誤設時每一天都灰 = 第二個區別訊號 |
| 20 (C2-4) | LOW | PARTIAL | LOW | 觀察為真;**但**同一迴圈導出、不會不同步,兩個讀者需求不同,換法零正確性差異 |
| 21 (C2-5) | LOW | PARTIAL | LOW | 硬編假設存在、純視覺為真;「UA stylesheet margin:2px」屬第三方平台行為,本輪禁外查、**標為未證實** |
| 22 (C2-7) | LOW | PARTIAL | LOW | 「常數理由被本 PR 自己的事實打穿」成立且是新資訊;**但**「畫面說明仍是誤述」不成立(文案與實際算法一致);明確在 AC 之外 |
| 23 (C3-2) | LOW | **REFUTED** | LOW | 決定性反證:decode docstring 同段最後一行明文「值的型別…不在檢查範圍」,與 13 行前的「一律 PluginFormatError」共同劃定範圍 |
| 24 (C3-3) | LOW | **REFUTED** | LOW | reviewer 唯一的行動建議(補 docstring 說明用區間的理由)原文 :89-90 已存在;需要 run 當單位的真實讀者也在 |
| 25 (C3-7) | LOW | PARTIAL | LOW | 沒跟上拆分為真;**但**留的是 F-1 判定中較強的那側,且 glossary 條目本就是摘要體 |

**Strict-liability findings**:本輪 0 條(無 hardcoded secret / SQL 串接 / eval / 未消毒 innerHTML 類)。
所有 25 條都實際走過複查,無任何條目以豁免跳過。

## Action Items

**校準套用**:無作者校準檔、本輪無套用。search-proof(Self-Verify R6 補證):
`ls -d docs/pr-review-calibration` → `No such file or directory`;
`ls docs/pr-review-calibration/loger-w.md` → `No such file or directory`。
作者 slug 由 PR 作者 `loger-w` 直接小寫化取得(無空白需轉 hyphen)。

**修法假設的第一手查證**(Self-Verify R8 補證 —— 下列 `auto-fix` 建議的路徑 / 字面 / 作用域已逐條實查,非推測):

| # | 修法假設 | 查證方式與結果 |
|---|---|---|
| #2 | `docs/next-time.md:36` 現況確為 v3 | `sed -n '36p'` 取回逐字:「…**2026-09-18 起外掛檔 v3、回看頁讀 v2 / v3**(純加欄位往下相容);v1 檔仍要重產。」→ 字面確認,改動點唯一 |
| #4 | `removed` / `changed` 在 `:41` 的作用域內 | `sed -n '13,18p'` 確認兩者是模組層變數(`:14` / `:15` 指派),`:41` 的 `SystemExit` 同層 → 建議的 `or removed or changed` 語法與作用域皆成立 |
| #10 | `bad()` 在該處可用、`trialFlat` 來源正確 | `sed -n '637,648p'` 確認 `const trialFlat = p.trial \|\| []` 後**下一行**即呼叫 `bad(...)` → `!Array.isArray(trialFlat) \|\|` 可直接前置,無作用域問題 |
| #13 | `.rp-msg-h` 真的沒有 `justify-content` | `grep -n "^.rp-msg-h{"` → `:128 .rp-msg-h{display:flex;flex-wrap:wrap;gap:0 10px;color:var(--muted);font-size:11px}`,確無 `justify-content` → `::after` 為最後一個 flex item、不貼右緣,`:219` 的「右上」確為不精確描述 |
| #15 | 刪掉 `assert wire["v"] == 4` 後版本仍有測試守護 | `grep -n '"v": 4'` → `:1880`(golden 字面測試內)確實釘著;`sed -n '1373,1381p'` 確認刪後該測試仍剩 `wire["trial"] == [1, 3]` 與 `decode(wire) == day` 兩條實質斷言 |
| #7 | 「不要改數字」的依據 | 主 session 以完整段定義(拿掉 13:25 閘、成交 parquet 也掃)重量:47,033 / 27,806 / 29,675,與 docstring 逐字相同;另得 13:25 前段內最大 37,845 / 8,140 / 29,300 |
| #16 | 要填進去的位元組數 | 主 session 逐檔加總兩個資料夾實測:+3,300 / +3,044 / +4,176 B |
| #1 / #14 | 「兩個述詞獨立、可同時成立」 | 主 session 以 PR 自己的 fixture 實跑:`[(True,False),(True,True)]`、`wire["trial"]==[0,1]`、`auction==[1]`、round-trip True |
| #6 / #8 / #9 / #11 | — | 這四條的修法是新增輸出、新增文案或二選一的行為決定,**未做原型驗證**;#9 / #11 已標 `ask-user`,#6 / #8 屬純增補(印一行 / 存一個檔),風險自明 |
| #3 / #5 / #12 | — | 純文字與死碼,無 API / 路徑假設 |

**Severity calibration**(SSOT = `~/.claude/references/finding-severity-rules.md`):

1. **6c Refactor Intent Gate** — **N-A**。本輪無任何 finding 主張「PR 移除 / 削弱既有防護、檢查、guard」;
   25 條的論證形狀都是「新加的東西有瑕疵」或「文件與實作不符」,無一觸發本閘。
2. **6d-1 hedge cap** — F-09 / F-10 / F-21 含假設性措辭(「萬一 p.trial 是物件」「日後若被誤刪」
   「其他瀏覽器不同」),依規則 cap 在 Should Fix;三者校正後本已是 LOW / Nice to Have 或參考用,cap 未實際咬到。
3. **6d-2 lone finding** — **本輪整體適用,故在此統一交代而非逐條重複**:本次只有一個 review 軸,
   所以 25 條**全部**在字面上都是 lone finding。規則明文要求不得機械降級,而在單軸情境下
   「其他軸沉默」承載的資訊量是**零**(沒有其他軸),連弱證據都算不上,因此**無一條因 lone 而降級**。
   唯一的例外方向:F-02(C1-1)由 **chunk 1 與 chunk 3 兩個互不知情、檔案集不相交的實例獨立命中**,
   這是軸內的真實佐證,但它已因 6d-3 降到 Nice to Have,佐證不改變結果。
4. **6d-3 Must Fix 雙半條件** — **本輪零條 Must Fix**。唯一的 MEDIUM(F-01)逐半檢驗:
   - 重現路徑半:要在畫面上看到矛盾,必須撞到一則同時 trial ∧ auction 的訊息 —— 三天正式資料
     1,169 筆 auction 中 **0 筆**符合,寫不出「打開頁面 → 做 X → 看到 Z」的使用者可見重現路徑。
   - Release-blocking 半:壞掉的是 docstring / glossary / 頁面說明文字三處的一句斷言,
     runtime 行為、資料正確性、build / CI 皆不受影響 —— 屬規則明列的「文件與 code 不符」類,
     **不阻擋發布**。
   兩半皆不成立 → **cap 在 Should Fix**。(而它確實值得 Should Fix:假保證已擴散到使用者可見文案,
   且 #271 的實作者正被同一段指到這裡。)
5. **Provenance cap** — **N-A**(base = master,無 inherited 檔)。

### Must Fix(合併前必修)

**無。** 本輪零 Must Fix。

### Should Fix(強烈建議)

- **#1 (`567969df50535eabb244`)** — `copycat/book_replay.py:64`「段的界」把 `trial` / `auction`
  互斥寫成不變量,程式沒保證,PR 自己的 fixture 就是反例;同一斷言另在 `CONTEXT.md:282-283`
  與回看頁使用者可見文案。CONFIRMED,兩條修法方向待拍板。

### Nice to Have(可選優化)

#2 #3 #4 #5 #6 #7 #8 #9 #10 #11 #12 #13 #14 #15 #16 —— 逐條見上方 inline block。
其中 `auto-fix` 11 條(#2 #4 #5 #6 #7 #8 #10 #13 #15 #16)、`ask-user` 3 條(#9 #11 #14)、
`no-op` 2 條(#3 #12)。

### 參考用(任一軸驗證為 REFUTED,或複查判定主要論點不成立)

- **#23 (`2cb006114d6939b8d6fb`)** REFUTED —— CC 擔心 `decode` 的「一律 PluginFormatError」有型別洞
  → 複查於 `copycat/book_replay.py:1064`(同段 docstring 最後一行)找到明文豁免「值的型別…不在檢查範圍」
  → 承諾與實作一致,使用者自行判斷是否仍要收。
- **#24 (`aeb85acad07c192df12d`)** REFUTED —— CC 建議補一行 docstring 說明為何用區間
  → 複查於 `copycat/book_replay.py:89-90` 找到該說明已存在 → 零殘留動作。
- **#17 #18 #19 #20 #21 #22 #25** PARTIAL —— 事實面多半成立,但主要論點被 baseline-comparable
  或 mitigation 反證(#17 #18 同 pattern 在本 repo 分別有 6 / 14 處長年未爆;#19 大聲通道另在面板文案
  且已真環境驗過;#20 兩份表示同源不會不同步;#21 影響為次像素且關鍵前提未證實;#22 明確在 AC 之外;
  #25 留的是較強那側)。**不當作「CC 錯了」呈現** —— 使用者看雙方證據自行判斷。

## 審查工具比較 (qualitative)

- **CC(context-aware,chunked ×3)視角**:善於跨檔對帳 —— 三個實例分別把截圖像素、外掛檔實際內容、
  三天 246 個正式檔重算,逐一核對本 PR 文件裡的每一個數字。本輪最有價值的一條(#1)正是由
  「讀模組說明 → 發現兩個述詞獨立 → 拿 PR 自己的 fixture 實跑」這條鏈抓出來的。
- **Codex 中性 / 對抗視角**:**本輪缺席**(CLI 未安裝)。代價是沒有任何 diff-only、無 context 的
  fresh-eyes 讀法 —— 歷史上該軸的獨有命中集中在「跨日邏輯」「fail-open」「dark mode 可見性」這類
  context-aware 軸容易視而不見的地方。本輪的盲區無法量化。
- **Gemini 軸**:**本輪缺席**(CLI 未安裝)。
- **兩者重疊率**:N/A(單軸)。軸內重疊:25 條中僅 1 條(#2)由兩個 chunk 實例獨立命中 = 4%。
- **CC 複查 CC first-pass 的結果分佈(Step 4.2 替代 pass)**:CONFIRMED 13、PARTIAL 9、REFUTED 2、
  OUT_OF_SCOPE 0、INCONCLUSIVE 0。
  - **REFUTED 率 8%(2/25)**,加計 PARTIAL 中主要論點被推翻者(#17 #18 #19 #20 #22 #25 共 6 條)
    後的「論點不成立率」約 **32%** —— 落在「first-pass 命中率尚可、但 baseline-comparable 測試
    確實咬到不少條」的區間。校正方向全部是**下修**(2 條 MED→LOW),無任何條目被上修。
  - 值得記錄的是複查的**增量價值**:它擋掉了兩條會造成負面後果的建議 ——
    #23 若照收會在已有明文豁免的地方加防禦碼;#7 原建議「docstring 加『收盤』兩字」
    **會把文件改成比事實更弱**(主 session 重量後確認 47,033 就是全段最大值)。
- **對抗式第三軸增益**:N/A(未執行)。

## 沒做的部分（結案對帳）

| 項目 | 狀態 | 理由 |
|---|---|---|
| Codex 中性軸 | **N-A** | 本機未安裝 `codex` CLI(`command -v codex` 無輸出)。缺 diff-only fresh-eyes 視角,盲區無法量化。 |
| Codex 對抗軸(紅隊) | **N-A** | 同上。preset 一律含對抗軸,但 CLI 不存在,無 retry / fallback 可執行。 |
| Gemini Flash 軸(永久軸) | **N-A** | 本機未安裝 `agy` CLI。 |
| Gemini Pro 軸(opt-in) | **N-A** | 同上;且本輪預設不加。 |
| Step 2.96 / 2.98 的 user 詢問 | **未執行** | 兩題的所有選項都需要未安裝的 CLI,任何答案都不可執行 → 依 Error Handling「proceed with available results and note the gap」處理,未佔用一個回合去問不可執行的問題。此為**刻意偏離**流程字面,在此揭露。 |
| Step 4.1(CC 驗非 CC 軸) | **N-A** | 無非 CC 軸 finding。 |
| Step 4.2(Codex 驗 CC first-pass) | **替代執行** | 改派獨立 `code-reviewer` 稽核 agent 跑同一套四測。**這是同軸複查、不是 cross-axis 證據**;擋得住 over-flag,擋不住兩個同型 reviewer 犯同一種錯。全報告已以此口徑標示。 |
| Step 4.3a consensus baseline check | **N-A** | 單軸,無 cross-axis consensus finding。 |
| Step 2.9 sem blast radius | **空輸出跳過** | `sem` 未安裝,`sem-pr-blast-radius.sh` 回空。實體級 blast radius(dependent 數 / 是否有測試守護)本輪無資料,風險排序僅依 reviewer 判斷。 |
| Step 2.97 React-doctor | **N-A** | F 內無 `.jsx` / `.tsx`。 |
| Step 2.65 C4 正式規格 trace | **SKIPPED** | `C4_NO_IMPLEMENTATION_BINDING_CLAUSE`,理由見「Spec 依據」。0 clauses / 0 findings / 0 observations / 0 invalidated。 |
| Step 2.2 作者校準 | **無檔案** | `docs/pr-review-calibration/` 目錄不存在;本輪無套用。 |
| Step 2.55 provenance | **N-A** | base = master,20 檔全 authored。 |
| Step 8 貼 PR 留言 | **未執行** | 非預設流程,需使用者明確指定 scope 並另行確認。 |
| C2-5(#21)的「Chromium UA stylesheet 另加 margin:2px」 | **未證實前提** | 第三方平台行為,本輪禁止外部查詢、本機無法驗證。該 finding 的其餘部分(硬編假設存在、純視覺影響)成立,其 severity 不依賴這個前提。 |
| 回看頁 repo 外現用檔 | **未改動** | 本輪只讀歸檔副本 `viewer_cdp_template.273.html`(chunk 3 已驗證它與 repo 外現用檔逐位元組相同)。任何 `auto-fix` 若執行,需同時改 repo 外現用檔並重產歸檔 diff。 |
| PR 狀態 | **已 MERGED** | 本輪為 closeout §4.5 的出貨後 review;findings 若要收,走收修 PR,不阻擋已完成的出貨。 |

### 正式報告 Self-Verify 結果與修正紀錄

稽核 agent(`skill-verify-auditor`,marker `skill-verify:pr-review`)回傳格式合規的逐條判定
(R1–R10 各一行、順序正確、FAIL 集合與 verdict 行一致),**`VERDICT: VIOLATIONS: R5, R6, R8`**。
逐條處置:

| 規則 | auditor 抓到的缺口 | 處置 |
|---|---|---|
| **R5**(finding UID / action) | 指多列「止於 action、缺 action_reason」 | **假陽性,但肇因於我自己的流程偏離** —— 送稽核的 prompt 內嵌的是草稿的**摘要**而非全文(流程明文要求「只內嵌完整證據草稿**全文**」)。實際草稿的「發現總覽」第 7 欄 `Action 理由` 25 列**逐列皆有值**(如 #5「用詞校正 + 刪死碼」、#15「刪一行」、#21「次像素級視覺偏差;旁邊有 title 與『第 n / m 則』兩個精確讀數兜底」)。未改內容;偏離本身在此揭露。 |
| **R6**(search-proof 與機制鏈) | `security-reviewer` N-A 與作者校準檔缺席兩個 absence 斷言無查詢佐證 | **真缺口,已補**:兩處都補上實跑的指令與逐字輸出(見「審查軸狀態」`security-reviewer` 條與 Action Items「校準套用」)。四項觸發條件各自 0 命中、`ls` 兩行 `No such file or directory` 均為本輪新跑。 |
| **R8**(修法假設與白話後果) | 除 #21 外,其餘建議修法的 API / 路徑 / 字面假設未證明經第一手驗證 | **真缺口,已補**:新增「修法假設的第一手查證」表,對 #2 / #4 / #10 / #13 / #15 逐條實查(`sed` 取逐字行、`grep` 確認作用域與 CSS 宣告、確認 golden 測試仍釘版本),對 #1 / #7 / #14 / #16 引主 session 的實跑數字,並**明列 #6 / #8 / #9 / #11 未做原型驗證**。 |

**本節限制**:依流程,修正後**不重派 auditor** —— 因此上述修正**未經第二次獨立稽查**。
R5 的假陽性也意味著 auditor 這一輪看到的不是完整草稿,它給的 R1–R4 / R7 / R9 / R10 的 PASS
同樣是在摘要上做出的,強度低於對全文稽核。
