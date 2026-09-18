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
## [完整證據副檔](pr-281-review.audit.md)
### finding_uid 索引
[567969df50535eabb244](pr-281-review.audit.md#發現總覽) · [4c16567868297a5fb156](pr-281-review.audit.md#發現總覽) · [fd7be86f5642e3def16c](pr-281-review.audit.md#發現總覽) · [592be6d7ff00a4581dd5](pr-281-review.audit.md#發現總覽) · [a3d5bb2b5458c6c81788](pr-281-review.audit.md#發現總覽) · [5ba21972c41ffec0668f](pr-281-review.audit.md#發現總覽) · [ebc19ce34ced3e3dfd8f](pr-281-review.audit.md#發現總覽) · [b0c236b5b88a6ce586bd](pr-281-review.audit.md#發現總覽) · [b7d72fa711fd19532d55](pr-281-review.audit.md#發現總覽) · [9931d0f4bac94e2ee6af](pr-281-review.audit.md#發現總覽) · [8fedcc305938336455ab](pr-281-review.audit.md#發現總覽) · [f8643b01d5621b0c2b96](pr-281-review.audit.md#發現總覽) · [ba451dba857ccf3e18c1](pr-281-review.audit.md#發現總覽) · [f2b9e78ca0587e27bda9](pr-281-review.audit.md#發現總覽) · [4c6ddf1f534dc73c2379](pr-281-review.audit.md#發現總覽) · [376c9878711406b1b3b7](pr-281-review.audit.md#發現總覽) · [b4ccef57ff77f5c2eb6e](pr-281-review.audit.md#發現總覽) · [c6f3e974f21a35e3a8e7](pr-281-review.audit.md#發現總覽) · [fe579e2325aad5267382](pr-281-review.audit.md#發現總覽) · [dc8c6adbe71cdc9e259e](pr-281-review.audit.md#發現總覽) · [bdb9f69f3d29c0ef1050](pr-281-review.audit.md#發現總覽) · [c2c29009cdd62c779d74](pr-281-review.audit.md#發現總覽) · [2cb006114d6939b8d6fb](pr-281-review.audit.md#發現總覽) · [aeb85acad07c192df12d](pr-281-review.audit.md#發現總覽) · [e895a9b8edc2fa3aea2e](pr-281-review.audit.md#發現總覽)
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
