# PR #152 Code Review 比較報告 · SHA d1950f5e
**Report projection schema**: 1

**PR**: [loger-w/copycat#152](https://github.com/loger-w/copycat/pull/152)
**標題**: fix(capital,frontend): 無券空單校準 —— 負現股列歸 daytrade_sell、today_qty 當沖稅減半、平倉解鎖、現股買先沖空單、損益列跨 kind 配對
**作者**: loger-w(commits 署名 Loger)
**分支**: `fix/borrowless-short-calibration` → `master`(PR 狀態 MERGED 2026-08-30T14:55:58Z,merge commit f5fa90b4;遠端分支已刪、回溯 review)
**變更**: 22 檔案, +424 / -46
**審查日期**: 2026-08-30
**Review input basis**: source repo R_kgDOTsITBg + d1950f5e6fabf4f19dd394244e3f4d058f5882e7;destination repo R_kgDOTsITBg + 25312d793cae1d30b391e2fa7cc5ffddea9b9e81;`input_binding: verified`(遠端分支已刪,改 `git fetch origin refs/pull/152/head` → FETCH_HEAD 與 headRefOid 逐字相等;`git worktree add --detach` 於該 SHA,worktree HEAD = source SHA;destination SHA `git cat-file -t` = commit 且 `git merge-base --is-ancestor 25312d79 d1950f5e` 成立 —— 分支於 merge 前已 rebase 到該 base)
**Review continuity**: `source_continuity=CURRENT`;`base_changed=false`;`review_context_changed=false`(產報告前 `gh pr view 152` 重抓 headRefOid / baseRefOid 與 reviewed 完全相同;origin/master 因本 PR 自身 rebase merge 前進到 f5fa90b4,不影響 PR 的 destination 綁定)
**worktree**: `C:/side-project/copycat/.worktrees/review-pr-152`(detached)
**worktree HEAD**: d1950f5e6fabf4f19dd394244e3f4d058f5882e7
**審查工具**: CC (claude-fable-5)(context-aware reviewer agents;實際 reviewer 模型以下一行與 dispatch receipt 為準)+ Codex 中性 FAIL(本機無 codex CLI、無 `~/.codex/config.toml`、無 codex plugin)+ Codex 對抗式 FAIL(同上)+ Cross-axis verification(4.1 N-A 無非 CC 軸 finding;4.2 FAIL→INCONCLUSIVE 無 codex,全部 CC finding 由 4.3b 主 agent 逐條實查)+ Gemini 軸 FAIL(本機無 agy;Flash 永久軸未啟動、Pro 未啟用)
**Reviewer model 記錄規則**: 上一行只描述工具組合;固定模型 reviewer 不套用「繼承 main session 模型」,實際身分以下一行與 dispatch receipt 為準。
**Reviewer models**: orchestrator=claude-fable-5;primary reviewers=python-reviewer × 2 chunk instances(chunk 1 = 21 檔:5 後端 + 5 前端 + 5 測試 + 6 docs/artifacts、chunk 2 = `tests/server/test_capital_api.py` 1 檔;dispatch 顯式 model=opus、effort 依 agent frontmatter;observed=UNAVAILABLE —— Agent tool 回傳無 runtime model 欄位);domain reviewers=security-reviewer × 1(觸發:request body model `PositionCloseBody.kind` 放寬 + 真錢平倉映射改動;dispatch model=opus;observed=UNAVAILABLE);spec-compliance-reviewer requested=opus / observed=UNAVAILABLE / effort=xhigh / tools=0(未 dispatch);Codex=N-A(未裝);Gemini=N-A(未裝)
**覆蓋 (ENH-A)**: |F|=22 → covered 11 / no-issues 11 / skipped 0 / **missed 0**(chunked: 是;FILE_COUNT=16 源檔 > 15 → 排序後切兩塊:chunk 1 前 21 檔(15 源檔 + 6 docs/artifacts)/ chunk 2 = `tests/server/test_capital_api.py`;兩塊 accounting 聯集 = F,零 repair 輪;security-reviewer 不計入覆蓋算術)
**定位 (ENH-B)**: anchored exact 16 / ambiguous 0 / **FAILED 0**(16 個 anchor 以 `git show d1950f5e:<path>` 逐字比中且唯一;line 以比中結果為準 —— P1-02 289→290、P1-10 216→218、S-05 124→126 三處校正 reviewer 自報行號;F-01 兩支 reviewer 同 anchor)
**React-doctor (2.97)**: N-A(非 React PR:F 無 `.jsx` / `.tsx`;frontend 改動只有 `.ts` 五檔)
**Formal spec traceability (2.65)**: SKIPPED (C4_AUTHORITY_PATH_NOT_ALLOWED)
**Blast radius (2.9)**: 空輸出跳過(本機無 `sem`;`sem-pr-blast-radius.sh <worktree> 25312d79` exit 0 零輸出)
**Gemini 軸**: 按預設只跑 Flash —— 但本機無 `agy`,Flash 軸實際未啟動(FAIL:工具缺);因工具缺席 Step 2.96 未向 user 提問(選項無效)
**Codex preset**: 按預設 default —— 但本機無 `codex`,中性 / 對抗兩軸實際未啟動(FAIL:工具缺);因工具缺席 Step 2.98 未向 user 提問;config 前置 mutation / restore 皆 N-A(無 `~/.codex/config.toml`)
**校準套用**: 無作者校準檔(loger-w.md 不存在;`docs/pr-review-calibration/` 目錄亦不存在)、本輪無套用
**Provenance (2.55)**: N-A(base = master,22 檔全部 authored)
**審查軸狀態**: primary(python-reviewer chunk 1)PASS(11 findings、21/21 accounting、追鏈 + 三條 mutation 對照);primary(python-reviewer chunk 2)PASS(1 finding、1/1 accounting、COM 欄位編碼逐項核);domain(security-reviewer)PASS(5 findings 全 LOW + 四格矩陣;「加倉不可能」三防線 / 審計完整 / 舊前端 fail-safe 負向證據);spec-compliance-reviewer N-A(gate SKIPPED);Codex 中性 FAIL(無 CLI);Codex 對抗 FAIL(無 CLI);Gemini Flash FAIL(無 agy);Gemini Pro N-A(未啟用);cross-axis verification:4.1 N-A / 4.2 FAIL→INCONCLUSIVE(無 codex)/ 4.3a N-A(零 consensus)/ 4.3b PASS(主 agent 以 `git show` 乾淨內容 + prod log 逐條實查:CONFIRMED 13 / PARTIAL 2 / REFUTED 1)
**Self-Verify**: auditor(skill-verify-auditor,dispatch model=opus,tools=Read×2 只讀本草稿)回 R1–R10 全 PASS、`VERDICT: COMPLIANT`(格式核:十行序正確、無 FAIL、verdict 一致);零修正、未重派。稽核輸入 = 草稿檔路徑(50 KB 超出 prompt 可內嵌上限,auditor 以 Read 讀全檔、禁讀其他產物),非 prompt 內嵌逐字,記「沒做的部分」

**Report generation**: sha256:f5cb5cf10e53f2ace33ca10cc11abdc589ec8debcac9961dda78724a689f4791

---
## [完整證據副檔](pr-152-review.audit.md)
### finding_uid 索引
[0ad33737575438fbd8f7](pr-152-review.audit.md#發現總覽) · [679a1cc2ad6d2b34cc42](pr-152-review.audit.md#發現總覽) · [70e3400200c933012764](pr-152-review.audit.md#發現總覽) · [5e387465b387902ef481](pr-152-review.audit.md#發現總覽) · [4d967a30405fae4aeb93](pr-152-review.audit.md#發現總覽) · [73c7866508f8149f6e69](pr-152-review.audit.md#發現總覽) · [953718d210df03d2415b](pr-152-review.audit.md#發現總覽) · [333ee9061ec1e3bb2b4e](pr-152-review.audit.md#發現總覽) · [e6a7b0a003eab74aca81](pr-152-review.audit.md#發現總覽) · [b48e99b2d6d5cbab019f](pr-152-review.audit.md#發現總覽) · [ec452b983040672bcefc](pr-152-review.audit.md#發現總覽) · [ca55a2c999a3c2a4acf4](pr-152-review.audit.md#發現總覽) · [6733605be3ad4ca48b5c](pr-152-review.audit.md#發現總覽) · [9f9e8a0e2942519e47e6](pr-152-review.audit.md#發現總覽) · [9e18ee79f6127bc90b1e](pr-152-review.audit.md#發現總覽) · [9d13371366b38a4a7d54](pr-152-review.audit.md#發現總覽)
## 發現總覽
| # | 問題 | Opus | Cdx-N | Cdx-A | Gem-F | Opus 複查(非 Opus 軸) | 最終建議 | Action | Action 理由 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| F-01 | `PositionKind` 的定義註解三個子句在本 PR 後全為假:「沒有任何回報路徑會產生它」(`_FILL_KIND["無券"]` 與 `parse_balance_line` 兩條新路徑都產生)、「使用者也點不到」(部位面板可點平倉)、「不進 wire」(`PositionCloseBody.kind` / `PositionCloseRequest.kind` 本 PR 就是放寬成 `TradeKind`);151–153 行 `Position.kind` 的「雖無回報路徑產生」同樣過期。這裡是兩個型別的定義處、CLAUDE.md §4 新契約條的錨點,下一個讀者照註解收窄值域 = 契約條自述的「前端送 daytrade_sell 吃 422」(`copycat/capital/models.py`) | MEDIUM [python-reviewer chunk 1 + security-reviewer] | — | — | — | 4.2 INCONCLUSIVE(無 codex);4.3b CONFIRMED(同軸兩 reviewer 同 anchor,非 cross-axis) | Nice to Have | `auto-fix` | 主 agent `git show d1950f5e:copycat/capital/models.py` :18-21 / :151-153 逐字讀到三子句;grep `PositionKind` 後端剩 `balance.py` 四個 T/C/L 中繼用途、前端 `types.ts` 已四值 —— 註解改寫成「群益即時庫存 T/C/L 中繼;對外值域 TradeKind」即可,純文字 |
| F-02 | 現股買先沖無券空單**只做買向**;持現股多單時從閃電梯選「無券」送賣單(`PriceLadder.tsx` 269 / 322 只鎖買側、賣側照送)→ 回報 idx6 `S08` → `_FILL_KIND` → `signed<0`、抵銷條件 `kind == "cash"` 不成立 → **新開** `(股號, daytrade_sell) −1` 列與 `(股號, cash) +n` 並存;修前無券不套用不會多長一列,修後不但多列、且該列平倉鈕本 PR 才解鎖 —— 快照落地前(~2 s)點下去 = `build_close_order` 組「現股買 n 張」真送單。註解把「群益對有庫存的賣出回報標『現股』不標『無券』」寫成事實但無實錄(`copycat/capital/store.py`) | MEDIUM [python-reviewer chunk 1] | — | — | — | 4.2 INCONCLUSIVE(無 codex);4.3b CONFIRMED(前提逐項核過:賣側無閘 / 回報 flag 隨單種回 / 該列平倉已解鎖;窗口 ~2 s 內要點兩下 + 確認窗,hedge 明寫) | Nice to Have | `ask-user` | 對稱補「`kind == "daytrade_sell" and signed < 0` 先減同股號 cash 正張數列」約 8 行,是真錢送單路徑的行為改動且 08-30 user 拍板只做買向 —— 要不要補反向、或只把註解斷言降成假設並點名 PriceLadder 反例,由 user 決定;security 軸同鏈追過判「快照落後於成交」競態非本 PR 引入(見 F-02 備註) |
| F-03 | `docs/next-time.md` 08-28 第 2 條的 prod 判準**首句**仍寫 `log \`balance line 現股負股數 → 無券空單\`(INFO,不再是「平倉暫鎖」WARNING)`,但 `balance.py:80` 是 `logger.debug`,prod 跑 INFO 永遠 grep 不到;三行後「review 收修」段已改口,判準句本身沒編輯 —— 兩段打架,下一筆對帳照首句 grep 會得 0 筆把修好的鏈判成 FAIL(`docs/next-time.md`) | MEDIUM [python-reviewer chunk 1](security-reviewer S-02 亦點名同句) | — | — | — | 4.2 INCONCLUSIVE(無 codex);4.3b CONFIRMED | Nice to Have | `auto-fix` | 主 agent `sed -n 33p docs/next-time.md` 讀到「(INFO,不再是…」原句、`balance.py:80` 為 `logger.debug`;修法 = 刪該括號或改「(DEBUG,prod 看不到;判準見下段兩行)」,純文字 |
| F-04 | `test_parse_cash_negative_shares_keeps_short_direction` 以 `at_level("DEBUG")` 捕捉、只斷言「訊息含負股數」+「無 WARNING」;`logger.debug → logger.info` 突變完全存活,而 round 1 F-03 的整個處置(prod 不洗版、grep 判準成立)靠的正是 DEBUG 這一格(`tests/capital/test_balance.py`) | LOW [python-reviewer chunk 1] | — | — | — | 4.2 INCONCLUSIVE(無 codex);4.3b CONFIRMED | Nice to Have | `auto-fix` | 主 agent 讀 :114-119:`any("負股數" in r.message …)` 對 INFO 記錄同樣為真、第二句只擋 WARNING;補一句 `levelno == logging.DEBUG` 斷言即可 |
| F-05 | `types.ts` 119 行註解仍寫「後端 Position.kind 值域是 TradeKind(另含 daytrade_sell),比 PositionKind 寬」,但本 PR 已把 `PositionKind` 加到四值 = `TradeKind`;`kind: string` 保留裸 string 的理由已由 103–104 行新 JSDoc 說完(`frontend/src/types.ts`) | LOW [python-reviewer chunk 1] | — | — | — | 4.2 INCONCLUSIVE(無 codex);4.3b CONFIRMED | Nice to Have | `auto-fix` | 主 agent `git show` :103-105 / :118-119 兩段相鄰互斥;純註解 |
| F-06 | `verification.md` blast radius 段寫「正向 daytrade_sell 列(不可達)仍 **400** 不猜單種」,實鏈是 `build_close_order` raise `ValueError` → `client._close_blocked` → `CapitalGateBlockedError` → `capital_api.py:415-419` 回 **403 `ORDER_BLOCKED`**;400 `INVALID_ORDER` 是另一組閘,close route 走不到(`.claude/bug/borrowless-short-calibration/verification.md`) | LOW [python-reviewer chunk 1] | — | — | — | 4.2 INCONCLUSIVE(無 codex);4.3b CONFIRMED | Nice to Have | `auto-fix` | 主 agent grep `CapitalGateBlockedError` → `capital_api.py:415-419` status_code=403;`client.py:1121 _close_blocked` 回該例外;artifact 一字改 403 |
| F-07 | 新測在函式體內 import `RAW_T_BORROWLESS_SHORT` / `RAW_PNL_ROW`,同檔 47 / 49 行已從同兩個模組做模組級 import;`test_store.py:856-857` 同形(`parse_balance_line` 完全可模組級)。治具檔自述「唯一定義處」,import 面散成兩層讓下一個人不知該加哪(`tests/capital/test_client.py`) | LOW [python-reviewer chunk 1] | — | — | — | 4.2 INCONCLUSIVE(無 codex);4.3b CONFIRMED | Nice to Have | `auto-fix` | reviewer grep `balance_rows\|profit_rows` 四處(47 / 49 模組級、2235 / 2236 局部);併進既有 import 列,零行為 |
| F-08 | `_apply_fill_locked` 守門明講「無券**買向**沒有對應部位狀態」拒套,但同檔 `_today_net_lots_locked` 用同一張 `_FILL_KIND` 反查,B08 成交會被算成 `daytrade_sell` 桶的 +lots(淨買進);同一檔案兩處對「B08 有沒有部位語意」答案相反。方向保守(net 變小 → today_qty 變小 → 打平線往不利側),但是隱形不變量(`copycat/capital/store.py`) | LOW [python-reviewer chunk 1] | — | — | — | 4.2 INCONCLUSIVE(無 codex);4.3b CONFIRMED | Nice to Have | `ask-user` | 主 agent 讀 :212-222:`_FILL_KIND.get(flag) != kind` 對 B08 / daytrade_sell 為 False → `net += lots`;修法動到 today_qty 算式(對 daytrade_sell 只計 `buy_sell == "S"`),雖然 B08 在 prod 不可達、仍是真錢稅算式,請 user 拍板要不要順手收 |
| F-09 | CLAUDE.md §4 新契約條「漂掉的症狀」把兩種漂移併成一句:後端改成**別的字串** → `kindOf` 回 null → 不送 kind → 確實「退回同檔唯一列」;但改回 **`cash`** 時 `kindOf` 認得、照送 `kind:"cash"` → `position_for` 命中負向 cash 列 → `_CLOSE_MAP` 無 `(cash, False)` → `ValueError` → **403 硬擋**,標籤印「現股」不是原字串 / 空白(`CLAUDE.md`) | LOW [python-reviewer chunk 1] | — | — | — | 4.2 INCONCLUSIVE(無 codex);4.3b CONFIRMED | Nice to Have | `auto-fix` | 主 agent 沿 `kindOf`(KIND_TEXT 含 cash)→ `position_for((no,"cash"))` → `_CLOSE_MAP` 鍵集追一遍,與 `test_cash_short_direction_is_data_contradiction_and_rejected` 釘的語意一致;拆兩句,純文字 |
| F-10 | `test_close_body_kind_daytrade_sell_sends_cash_buy` 只種一列,`position_for` 的 `kind=None` 唯一列 fallback 會取到同一列組同一張單 → 拿掉 route 的 `kind=body.kind` 透傳、或讓精確鍵對 daytrade_sell 失效,測試仍全綠;822–823 行註解卻寫「精確鍵到空單列」—— 測的比註解說的少。抓得到:wire 收窄(422)/ `_CLOSE_MAP` 值改 / 刪鍵(403)/ `abs` 改;抓不到:route 掉 kind(`tests/server/test_capital_api.py`) | LOW [python-reviewer chunk 2] | — | — | — | 4.2 INCONCLUSIVE(無 codex);4.3b CONFIRMED | Nice to Have | `auto-fix` | 主 agent 讀 `store.py:579-586` fallback 分支確認單列時 `kind=None` 與精確鍵同結果;修法一行:多種 `Position(market="sec", stock_no="8358", qty=5, kind="margin")`(真實可達的「融資多 + 現股無券空」共存態),route 掉 kind → 兩列歧義 403 即紅 |
| F-11 | 本 PR 同時把負 T 列從 fail-closed(平倉鎖)改成可送「現股買」,又把原 WARNING 降成 DEBUG;替代判準兩條覆蓋面不完整:`client.py:429`「成交樂觀套用部位」**不印 kind**,`client.py:578`「損益列回填 … 部位=」要損益段真回同股號現股列且 avg 有變才印 —— 只有快照、沒有成交事件的 session(重啟後帶著空單開機)裡,「這列被歸成可一鍵送現股買的無券空單」零 INFO 線索;分類依據只有 08-28 一筆實錄(`copycat/capital/balance.py`) | LOW [security-reviewer] | — | — | — | 4.2 INCONCLUSIVE(無 codex);4.3b PARTIAL(現況描述屬實;「另一種負 T 列」為假設、repo 無樣本 —— hedge,≤ Should) | Nice to Have | `ask-user` | 主 agent 核 `client.py:429` 格式 `seq=%s stock=%s (%.1f ms)` 無 kind、:578 外層守 `_avg_logged` 值變;與 round 1 F-03(每輪洗版 → DEBUG)是同一格的兩種取捨,建議「每 (股號, 交易日) 只印一次 INFO」是第三種 —— log 政策由 user 拍板 |
| F-12 | `client.py:436` INFO「成交未樂觀套用(零股 / **無券** / 選擇權 / 契約碼不明 / 未滿張)」的列舉仍寫「無券」,但賣向無券自本 PR 起會套用(`store.py:256-262` 只有買向回 False);這行正是 prod 判準 1 的對照組(「修前是『不在樂觀套用表』」),留著會讓下一次 grep 得到相反結論(`copycat/capital/client.py`) | LOW [security-reviewer] | — | — | — | 4.2 INCONCLUSIVE(無 codex);4.3b CONFIRMED | Nice to Have | `auto-fix` | 主 agent 讀 `_apply_fill_locked` :253-262:`k == "daytrade_sell" and a.buy_sell == "B"` 才 return False;列舉改「無券買向」,純文字 |
| F-13 | CLAUDE.md 新契約條宣稱「與 wire 同為 TradeKind 四值 —— 標得出來就送得出去」並列三支測試,但三支都只驗自己那一側(前端鍵集字面 / 後端收得下 daytrade_sell),沒有一支比較兩個集合;後端單邊拿掉 daytrade_sell → 真錢空單平倉 422 且兩側測試全綠。repo 已有現成姿態 `tests/capital/test_models.py::test_avg_source_parity_with_frontend`(`read_frontend_source("types.ts")` + `get_args`)(`frontend/src/types.ts`) | LOW [security-reviewer] | — | — | — | 4.2 INCONCLUSIVE(無 codex);4.3b CONFIRMED | Nice to Have | `auto-fix` | 主 agent grep `test_avg_source_parity_with_frontend` 確認先例存在(`test_models.py`);新測斷言 `set(前端 PositionKind) ⊆ set(get_args(TradeKind))`(子集不相等:TradeKind 同時是下單交易別值域),純測試新增 |
| F-14 | 平倉確認窗(§7 gate 2)印「種類:無券」+「反向單:買回 1 張」;在 daytrade_sell 之前部位種類恆等於送出單的 `trade_kind`,這是第一個不相等的情形,而「無券 + 買回」在畫面上讀起來像 `safety.py:65`「daytrade_sell 不可買進」明文禁止的組合 —— 方向與送單都對(`_CLOSE_MAP` 同源),只是最後一道人工閘的文字讓人停手或誤按(`frontend/src/components/capital/CapitalPositionsList.tsx`,**不在本 PR diff 內、因本 PR 首次可達**) | LOW [security-reviewer] | — | — | — | 4.2 INCONCLUSIVE(無 codex);4.3b CONFIRMED(檔案不在 F、不計覆蓋;可達性由本 PR 解鎖) | Nice to Have | `ask-user` | 主 agent 讀 :110-128 rows 組法:反向單列只有方向 + 張數 + 單位、無交易別;修法「買回 1 張(現股)」一行,但確認窗文案是 UI 措辭、且檔案不在 PR 範圍 —— user 決定是否併下一支 /mod |
| F-15 | `ladder-position.ts` 的 `KIND_ORDER` 仍三值,`daytrade_sell` 走 `?? 3` 與未知字串同一桶;CLAUDE.md 契約條讀者清單也沒點名它 —— 第四份未同步的 kind 白名單,正是 next-time F-09 記的坑(`frontend/src/lib/ladder-position.ts`) | LOW [python-reviewer chunk 1] | — | — | — | 4.2 INCONCLUSIVE(無 codex);4.3b PARTIAL(`git diff 25312d79 d1950f5e` 對 `KIND_ORDER` 零命中 = 本 PR 未動;該行註解自述「含 daytrade_sell … 殿後」是刻意;F-09 已在 next-time) | 參考用 | `no-op` | 既有、刻意、已記留尾;不是本 PR 缺陷,排序落最後可接受 |
| F-16 | `RAW_T_BORROWLESS_SHORT` 註解自述「08-28 prod 實錄、去敏」,但整列除 [0]/[1]/[11]/[14] 外全 0(含 [10] 今日賣出成交 = 0,而該列成因正是賣出 1000 股),疑為合成列卻沒照該檔「實錄 / 合成」分類慣例標(`tests/capital/balance_rows.py`) | LOW [python-reviewer chunk 1](自標參考用) | — | — | — | 4.2 INCONCLUSIVE(無 codex);4.3b **REFUTED**:主 agent 取 gitignored `logs/server-20260828-0814.log` :2425 原文 `'8358,T,0,0,0,0,0,0,0,0,0,-1000,0,0,-1000,0,,<ID>,<帳號>'`,與治具除末兩欄去敏外**逐字相同** —— 群益即時庫存段對無券空單就是這樣回([10] 為 0 是實錄) | 參考用 | `no-op` | reviewer 看不到 gitignored log,疑慮方向合理但已被實錄反證;註解可選擇補一句「[10] 為 0 是群益原樣」,非必要 |

auto-fix 只是處置建議；沒有使用者另行下令，不修改 code、commit、push 或 PR。

F-01 finding_uid: 0ad33737575438fbd8f7 action=auto-fix
F-02 finding_uid: 679a1cc2ad6d2b34cc42 action=ask-user
F-03 finding_uid: 70e3400200c933012764 action=auto-fix
F-04 finding_uid: 5e387465b387902ef481 action=auto-fix
F-05 finding_uid: 4d967a30405fae4aeb93 action=auto-fix
F-06 finding_uid: 73c7866508f8149f6e69 action=auto-fix
F-07 finding_uid: 953718d210df03d2415b action=auto-fix
F-08 finding_uid: 333ee9061ec1e3bb2b4e action=ask-user
F-09 finding_uid: e6a7b0a003eab74aca81 action=auto-fix
F-10 finding_uid: b48e99b2d6d5cbab019f action=auto-fix
F-11 finding_uid: ec452b983040672bcefc action=ask-user
F-12 finding_uid: ca55a2c999a3c2a4acf4 action=auto-fix
F-13 finding_uid: 6733605be3ad4ca48b5c action=auto-fix
F-14 finding_uid: 9f9e8a0e2942519e47e6 action=ask-user
F-15 finding_uid: 9e18ee79f6127bc90b1e action=no-op
F-16 finding_uid: 9d13371366b38a4a7d54 action=no-op
### Inline Comments per Finding（直接複製貼到 PR review）
#### F-01 這兩段註解現在跟 code 反著講,下個人會照它把 wire 收窄回去
**File**: `copycat/capital/models.py`
**Line**: 19-20

**Comment**:
```
PositionKind 這段說 daytrade_sell「沒有任何回報路徑會產生它、使用者也點不到、不進 wire」——
本 PR 三句全推翻了:_FILL_KIND["無券"] 跟 parse_balance_line 都會產出這個 kind,部位面板點得到平倉,
PositionCloseBody.kind / PositionCloseRequest.kind 也已經是 TradeKind。151-153 行 Position.kind 的
「雖無回報路徑產生」同樣過期。

改成:PositionKind = 群益即時庫存段的三種原始代碼(T/C/L)解析中繼,只給 balance._KIND / _PNL_KIND 用;
部位對外值域(store 鍵、wire、平倉查找)是 TradeKind,含 daytrade_sell。
```
#### F-02 持多單時從閃電梯送「無券」賣,會多長一列可按平倉的空單
**File**: `copycat/capital/store.py`
**Line**: 290-291

**Comment**:
```
抵銷只做「現股買沖無券空單」這一向。反向會發生:閃電梯交易別選「無券」對任何標的送賣單
(PriceLadder.tsx 269 / 322 只鎖買側),回報 idx6 = S08 → _FILL_KIND → kind=daytrade_sell、signed<0,
這裡的 kind == "cash" 條件不成立 → 新開 (股號, daytrade_sell) -1 列,跟既有 (股號, cash) +n 並存。
修前無券不套用、不會多這一列;修後多了,而且這列的平倉鈕本 PR 才解鎖 —— 快照落地前(~2 s)點下去
= build_close_order 組「現股買」真送單、多一筆非預期多單。

註解寫「群益對有庫存的賣出回報會標現股不標無券」是猜的,沒有實錄。二選一:
(a) 對稱補 kind == "daytrade_sell" and signed < 0 時先減同股號 cash 正張數列,餘量才開空單列;
(b) 維持只做買向,但把這句斷言改成假設、點名 PriceLadder 賣側是反例。
```
#### F-03 prod 判準第一句還在叫人 grep 一行已經降成 DEBUG 的 log
**File**: `docs/next-time.md`
**Line**: 33

**Comment**:
```
這句「log `balance line 現股負股數 → 無券空單`(INFO,不再是「平倉暫鎖」WARNING)」——
balance.py:80 現在是 logger.debug,prod 跑 INFO 永遠 grep 不到 0 筆。三行後的「review 收修」段已經改口,
但判準句本身沒動,下一筆對帳照第一句 grep 會把修好的鏈判成 FAIL。

把括號整句拿掉,或改成「(DEBUG,prod 看不到;判準見下段兩行)」。
```
#### F-04 這條測試釘不住「DEBUG」這一格,改回 info 照樣綠
**File**: `tests/capital/test_balance.py`
**Line**: 118-119

**Comment**:
```
at_level("DEBUG") 捕到的記錄不分等級,第一句只看訊息含「負股數」、第二句只擋 WARNING —— 把 balance.py:80
的 logger.debug 改回 logger.info 這條照樣過。而 round 1 F-03「每輪不洗版」整個處置就靠 DEBUG 這格。

補一句:
    assert [r for r in caplog.records if "現股負股數" in r.message and r.levelno == logging.DEBUG]
```
#### F-05 這行註解還說 PositionKind 比 TradeKind 窄,上面剛把它加到四值
**File**: `frontend/src/types.ts`
**Line**: 119

**Comment**:
```
103-105 行剛把 PositionKind 加成四值 = 後端 TradeKind,119 行卻還寫「值域是 TradeKind(另含 daytrade_sell),
比 PositionKind 寬」。兩者現在等寬;kind 保留裸 string 的理由(舊後端 / 未來新值)已經在 JSDoc 講過了。

改成:「保留裸 string 是為了舊後端 / 未來新值;kindOf 的白名單負責歸一」。
```
#### F-06 verification.md 寫 400,實際走的是 403 ORDER_BLOCKED
**File**: `.claude/bug/borrowless-short-calibration/verification.md`
**Line**: 56

**Comment**:
```
「正向 daytrade_sell 列(不可達)仍 400 不猜單種」—— 實鏈是 build_close_order raise ValueError →
client._close_blocked → CapitalGateBlockedError → capital_api.py:415-419 回 403 {"error":"ORDER_BLOCKED"}。
400 INVALID_ORDER 是另一組閘(_invalid_order),close route 走不到。同檔 PositionCloseBody 的註解寫的就是 403。

400 → 403 ORDER_BLOCKED。
```
#### F-07 治具 import 散成模組級 + 函式內兩層
**File**: `tests/capital/test_client.py`
**Line**: 2235-2236

**Comment**:
```
同檔 47 / 49 行已經從 balance_rows / profit_rows 做模組級 import,這裡再在函式體內 import 同兩個模組的另外兩個名字;
test_store.py:856-857 同形(parse_balance_line 也可以模組級)。治具檔自述「唯一定義處」,import 面分兩層下一個人不知道該加哪。

併進 47 / 49 行的既有 import 列就好。
```
#### F-08 同一檔案裡兩處對「無券買向」給了相反答案
**File**: `copycat/capital/store.py`
**Line**: 218

**Comment**:
```
_apply_fill_locked 剛加的守門說「無券買向沒有對應部位狀態」不套;但 _today_net_lots_locked 這行用同一張
_FILL_KIND 反查,B08 成交會被算成 daytrade_sell 桶的 +lots(淨買進)→ net 變小 → today_qty 變小 →
打平線往不利側。方向保守、prod 也沒有 B08,所以只是隱形不變量 —— 下次有人把守門拿掉,兩邊會一起漂。

對 kind == "daytrade_sell" 只計 a.buy_sell == "S",守門處註一行「買向兩處一致排除」。
```
#### F-09 契約條把「改回 cash」跟「改成別的字串」兩種漂移寫成同一個症狀
**File**: `CLAUDE.md`
**Line**: 258

**Comment**:
```
「後端把負現股列改回 cash 或改別的字串 → …平倉退回同檔唯一列」—— 只有「別的字串」是這樣(kindOf 回 null → 不送 kind)。
改回 cash 時 kindOf 認得、照送 kind:"cash" → position_for 命中負向 cash 列 → _CLOSE_MAP 沒 (cash, False)
→ ValueError → 403 硬擋;標籤印「現股」,不是原字串也不是空白。

拆兩句,cash 那條寫「平倉直接 403(資料矛盾,test_cash_short_direction_is_data_contradiction_and_rejected 釘的就是這個)」。
```
#### F-10 只種一列,route 把 kind 丟掉這條測試還是綠的
**File**: `tests/server/test_capital_api.py`
**Line**: 827-829

**Comment**:
```
store 只有一列 8358,position_for 的 kind=None 唯一列 fallback(store.py:581-586)會取到同一列組出同一張單 ——
capital_api.py:348 的 kind=body.kind 拿掉、或精確鍵對 daytrade_sell 失效,這條照樣全綠;
但 822-823 行註解寫的是「精確鍵到空單列」。抓得到 wire 收窄(422)/ _CLOSE_MAP 改值 / 刪鍵(403)/ abs 改,
抓不到 route 掉 kind。

多種一列讓 fallback 不成立:
    Position(market="sec", stock_no="8358", qty=5, kind="margin"),
選 margin 不選 cash:「融資多 + 現股無券空」是真實可達的共存態,「現股多 + 現股無券空」上游不會並存。
```
#### F-11 重啟後帶著空單開機的 session,看不到「這列被歸成可送現股買」這件事
**File**: `copycat/capital/balance.py`
**Line**: 80

**Comment**:
```
本 PR 把負 T 列從「平倉鎖住」改成「可送現股買」,同時把這行從 WARNING 降到 DEBUG。替代判準兩條都要有成交事件:
client.py:429「成交樂觀套用部位」不印 kind,client.py:578「損益列回填 … 部位=」要 avg 有變才印。
只有快照、沒成交的 session(重啟後帶空單)零 INFO 線索;分類依據目前只有 08-28 一筆實錄。

跟 round 1 F-03(每輪洗版 → DEBUG)是同一格的取捨。第三個選項:每 (股號, 交易日) 只印一次 INFO,
回歸斷言同一列連餵兩輪只出現 1 筆。要不要走這條,看你對「零線索」的容忍度。
```
#### F-12 這行 INFO 的列舉還把「無券」列為不套用,賣向無券現在會套
**File**: `copycat/capital/client.py`
**Line**: 436

**Comment**:
```
「成交未樂觀套用(零股 / 無券 / 選擇權 / 契約碼不明 / 未滿張)」—— store.py:256-262 現在只有無券**買向**回 False,
賣向走成功分支。這行正是 prod 判準 1 的對照組(「修前是『不在樂觀套用表』」),留著「無券」下次 grep 會得到相反結論。

列舉改成「零股 / 無券買向 / 選擇權 / 契約碼不明 / 未滿張」。
```
#### F-13 「標得出來就送得出去」沒有機械鎖,後端單邊收窄兩側測試都綠
**File**: `frontend/src/types.ts`
**Line**: 105

**Comment**:
```
CLAUDE.md 契約條列的三支測試都只驗自己那側:close-order.test 斷前端鍵集字面、test_capital_api 斷後端收得下
daytrade_sell —— 沒有一支比兩個集合。後端拿掉 daytrade_sell → 真錢空單平倉 422,兩側測試全綠。
repo 已有同姿態:tests/capital/test_models.py::test_avg_source_parity_with_frontend(read_frontend_source + get_args)。

照抄一支:assert set(前端 PositionKind 字面) <= set(get_args(TradeKind))。
用子集不用相等 —— TradeKind 同時是下單交易別值域,日後加值不該逼前端跟。
```
#### F-14 確認窗印「種類:無券 / 反向單:買回」,第一次跟實際送的交易別分家
**File**: `frontend/src/components/capital/CapitalPositionsList.tsx`
**Line**: 126

**Comment**:
```
這檔不在本 PR diff 內,但這條路徑是本 PR 才解鎖的。daytrade_sell 之前,部位種類恆等於送出單的 trade_kind
(現股→現股賣、融資→融資賣、融券→融券買);現在確認窗印「種類:無券」+「買回 1 張」,而 safety.py:65 明文
「daytrade_sell 不可買進」—— 送的其實是現股買(_CLOSE_MAP 同源、方向對),只是最後一道人工閘的文字會讓人停手或誤會。

反向單列補交易別:`買回 1 張(現股)`;回歸斷言 render 一列 kind="daytrade_sell" qty=-1,確認窗文字含「現股」。
```
