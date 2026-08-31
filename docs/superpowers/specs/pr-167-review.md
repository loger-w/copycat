# PR #167 Code Review 比較報告 · SHA 3b863774
**Report projection schema**: 1

**PR**: [loger-w/copycat#167](https://github.com/loger-w/copycat/pull/167)
**標題**: feat(server,frontend): 看盤 UX 批四支 —— 緩撮第二段 / 成交點精確版 / 盤前前一交易日+TXO 自動日 / 斷線徽章分態(L75–L78)
**作者**: loger-w
**分支**: `mod/chart-ux-batch-0831` → `master`(PR 已 MERGED,rebase merge)
**變更**: 45 檔案, +924 / -489
**審查日期**: 2026-08-31
**Review input basis**: source repo = loger-w/copycat;source SHA `3b863774564f63af4eac8d9b757957d99f16f74a`;destination SHA `81ab5d054c799af9baf808dd8594389101bdff12`(= merge-base);`input_binding: verified`(worktree HEAD 實測 == source SHA)
**Review continuity**: `source_continuity=CURRENT`(已 MERGED,head 不可變);`base_changed=true`(master 已前進,合併後正常演進);`review_context_changed=false`
**審查工具**: CC(claude-fable-5 orchestrator)+ CC reviewer agents(code-reviewer ×3 chunked first-pass + code-reviewer 同軸複查)。**Codex 中性 / Codex 對抗 / Gemini Flash / Gemini Pro 四軸本機不可用**(`codex` / `agy` CLI 不存在)—— CC 單軸 chunked + 同軸 fresh-context 複查,非 cross-axis,判讀請計入此限制。
**Reviewer model 記錄規則**: 上一行只描述工具組合;實際身分以下一行為準。
**Reviewer models**: orchestrator=claude-fable-5;code-reviewer chunk1/2/3 requested=opus / observed=UNAVAILABLE(Agent dispatch 通道不回傳 runtime model 名 —— 觀測面失敗原因,非軸失敗;軸 PASS 依據 = 各自提交的實跑證據);code-reviewer(複查)requested=opus / observed=UNAVAILABLE(同上);Codex=N-A;Gemini=N-A
**覆蓋 (ENH-A)**: |F|=45 → covered 24(有 finding 落點之檔)/ no-issues 21 / skipped 0 / **missed 0**;24+21+0+0=45=|F|(chunked: **是**,3 塊 × 15 檔,門檻 15 檔 or 800 行雙雙超標;chunk 聯集 = F 逐檔核過)
**定位 (ENH-B)**: anchored exact 21 / ambiguous 2(#5、#6 各兩命中,取首)/ **FAILED 0**
**React-doctor (2.97)**: PASS — 未引入新問題(命中 1 條 only-export-components @GroupGridView.tsx:70,該行未被本 PR 觸及且與 master 逐字同 = 既有,依 2.97 分類不計)
**Formal spec traceability (2.65)**: SKIPPED (C4_NO_SPEC_DETECTED)
**審查軸狀態**: primary(code-reviewer ×3 chunks)PASS(chunk1:probe+凍時鐘實測;chunk3:pytest 451+150 實跑;chunk2:靜態追讀,前端 vitest 因 worktree 無 node_modules 未實跑 —— 已列沒做的部分)/ 同軸複查(code-reviewer)PASS(3 支探針 + 2 個 mutation 全套 3240 實跑 + 凍時鐘 24h 求值表)/ Codex 中性 FAIL(CLI 不存在)/ Codex 對抗 FAIL(CLI 不存在)/ Gemini Flash FAIL(agy CLI 不存在)/ Gemini Pro N-A(未啟用)/ cross-axis verification N-A(單軸,同軸複查代位)
**blast radius (2.9)**: N-A — script 空輸出跳過(有跑,無結果)
**worktree**: `C:/side-project/copycat/.worktrees/review-pr-167`
**worktree HEAD**: `3b863774564f63af4eac8d9b757957d99f16f74a`
**特別揭露**: 本 PR 由本 session(orchestrator)實作;三個 chunk reviewer 與複查均為 fresh-context subagent,orchestrator 同人,分級依 SSOT 機械套用、全證據揭露。

**Report generation**: sha256:4d6c56006a4e267b6bae40e476c9e74acb0c2f03aed66cdccc22212bb147c595

---
## [完整證據副檔](pr-167-review.audit.md)
### finding_uid 索引
[30e6348e17453804d2da](pr-167-review.audit.md#發現總覽) · [309ee52382bd1c8c4d2f](pr-167-review.audit.md#發現總覽) · [7f0a1f07f111b2f0d5d7](pr-167-review.audit.md#發現總覽) · [cc8d5828844482a333e3](pr-167-review.audit.md#發現總覽) · [b8f21098ca7dd7c1eec4](pr-167-review.audit.md#發現總覽) · [5a56b4a20c29a531be8d](pr-167-review.audit.md#發現總覽) · [09b1ae2d1a7d3b0bab03](pr-167-review.audit.md#發現總覽) · [6e3febe74500e02bb253](pr-167-review.audit.md#發現總覽) · [9c161d8f69fabcf22cc1](pr-167-review.audit.md#發現總覽) · [6a4d14cc8fd6c849863e](pr-167-review.audit.md#發現總覽) · [7d0e192b5d1dcb79f54d](pr-167-review.audit.md#發現總覽) · [8f92179eb92ba4a2ea1f](pr-167-review.audit.md#發現總覽) · [5a745b2bbf893c510929](pr-167-review.audit.md#發現總覽) · [7963ccecd8cf9e0e919a](pr-167-review.audit.md#發現總覽) · [9175a06be32a991bd5b9](pr-167-review.audit.md#發現總覽) · [9c3b850b8880757b447c](pr-167-review.audit.md#發現總覽) · [419d1e8745333b42c12b](pr-167-review.audit.md#發現總覽) · [6a15fdf9558f1b428b46](pr-167-review.audit.md#發現總覽) · [21a5c404c060bae928e8](pr-167-review.audit.md#發現總覽) · [ef1a84f63c3330543045](pr-167-review.audit.md#發現總覽) · [b260ef753a6f537f44c7](pr-167-review.audit.md#發現總覽) · [850ac70aad577c2bd2ff](pr-167-review.audit.md#發現總覽) · [e0c73b4aa3737003af86](pr-167-review.audit.md#發現總覽)
## 發現總覽
| # | 問題 | CC(chunk) | 同軸複查 | 最終建議 | Action | Action 理由 |
|---|---|---|---|---|---|---|
| 1 | per-code TradeStatus 翻轉零推播點:「(緩)/(處置)」在單檔頁與側欄整段 episode 不亮,群組 60s 輪詢 payload 也無 trial 鍵 —— L75 招牌交付項在兩個主畫面是死路徑(探針實證 _publish 捕獲 0 則) | HIGH(c1) | CONFIRMED HIGH(三條探針:0→1 無成交零推播 / 恢復那則 trial=False / group_snapshot 無 trial 鍵;推播點七處逐一核無一由 TradeStatus 驅動;前端無輪詢可補;定性 = 新功能不生效非回退,但零訊號) | Must Fix | `auto-fix` | 修法方向明確:_observe_trade_status 轉態且改變 _trial_now 答案時入 dirty / 直 publish(沿 _trial_flip_targets 收件人),補一條 WS 級測試 |
| 2 | fills 只留「到達本機日」而期貨近全軸跨午夜(D−1 15:01→D 13:45):夜盤成交三角 00:00 起靜默消失 —— 相對近似版(orders 不 prune)是真回退 | HIGH(c1+c3 同根因互證) | PARTIAL → MEDIUM(機制屬實且注入 today 重現;「fixture 不可達」子宣稱 REFUTED —— 15:01–23:59 段可達,失真起點是 00:00 非整天;「重播蓋日」目前不可達(clear 零 caller);**修法校正:「今+昨」不夠 —— 週五夜盤錨定週一,保留窗要以錨定交易日為鍵**) | Should Fix | `ask-user` | 保留窗設計(錨定交易日 vs 今+昨+週末特判)要拍板 |
| 3 | `_fill_code` 的 unit=="口" 反查分支(L444 全部意義)前後端零覆蓋:拿掉 if 全套 3240 綠(mutation 實證) | MED(c3) | CONFIRMED MEDIUM(mutation:`return stock_no` → test_capital_api+capital 500 passed、全套 3240 passed;前端 L444 案是手寫 code fixture 測分組不測反查) | Should Fix | `auto-fix` | 補一例期貨成交測試,口徑對齊既有 test_positions_carry_code |
| 4 | window ident 用代理值 (session_key, auto) ≠ 實際回補窗:每交易日 08:00 / 13:46 各一次冗餘全鏈重交接(13:46 那發本 PR 新增;凍時鐘 24h 求值表實證) | MED(c1) | CONFIRMED → LOW(兩發都在安靜時段、資料不錯;08:00 那發改前即存在只是變冗餘) | Nice to Have | `auto-fix` | ident 改用 _backfill_window 抽出的純函式,「ident 變 ⇔ 窗變」成定義 |
| 5 | market→(div,unit) 判定逐字複製兩份(store.py 220-225 vs 516-521)且除不盡處理已分岔;unit 是 §4 跨語言契約字面值 | MED(c1) | CONFIRMED → LOW(分岔 fallback 在整股撮合下不可達;但若踩到,unit="股" 正好是前端排除鍵 → 成交靜默消失,值得記) | Nice to Have | `auto-fix` | 抽 _lot_unit(market) 兩處共用 |
| 6 | useCapitalFills 每 observer 各帶 30s refetchInterval,違反同檔 N068 明文收斂;FuturesChart(hidden 保留)與 StockChart 可並存 | MED(c2) | CONFIRMED → LOW(量化校正:改前三處吃 capital-orders 同型輪詢,總發數大致持平非憑空 ×3) | Nice to Have | `auto-fix` | 照 positionsQueryOptions 樣板收斂到 provider |
| 7 | GroupGridView 呼叫點註解宣稱「反查留給精確版/只認現股」與本 PR 剛啟用的 L444 行為相反;fill-marks.ts 寫著相反的話 | MED(c2) | CONFIRMED → LOW(純文件;但本 repo 把註解當契約,兩份互矛盾零訊號) | Nice to Have | `auto-fix` | 重寫 312-318 六行 |
| 8 | useStockStream 的 disposition 三條新分支(解碼/pendingTrial 攜帶/accum 守門)零測試;失效方向 = 靜默降級 | MED(c2) | PARTIAL → LOW(原宣稱四條,engine 缺欄預設那條實有 App.test 覆蓋 —— 高估一條;其餘三條 grep 實證零命中) | Nice to Have | `auto-fix` | 比照緊鄰 trial 測試補三條 |
| 9 | breadth disposition_codes() 不看 _disposition_ok:FinMind 掛時拿昨日名單標(處置) | LOW(c1) | CONFIRMED LOW(既有消費者 assemble_universe 同樣不看;「保前值」是明文政策,新鮮度由 _stale() 表態 —— 缺的是本 accessor 的政策表態) | Nice to Have | `ask-user` | 空集合降級 vs 明文沿用前值,二選一表態 |
| 10 | trading_calendar __all__ 漏列 resolve_trade_date_before | LOW(c1) | CONFIRMED LOW | Nice to Have | `auto-fix` | 一行 |
| 11 | app.py _session_date docstring「唯一呼叫者是 _heal_gate」已假(新增 _txo_auto_backfill_date 呼叫) | LOW(c1) | CONFIRMED LOW(docstring 自己寫過「逐個列呼叫點就會漏」—— 又漏了) | Nice to Have | `auto-fix` | 改判準式一句 |
| 12 | CLAUDE.md §4 OrderRecord.unit 契約條缺新產生點(_append_fill_locked)與兩個新讀者(fill-marks excludeUnit / capital_api unit=="口") | LOW(c1) | CONFIRMED LOW | Nice to Have | `auto-fix` | 更新契約條或另立 fills wire 條 |
| 13 | _fill_code 以顯示單位「口」當期貨判準,positions 用 market —— 同檔兩把尺;改 unit 字面值會讓 L444 靜默失效 | LOW(c1) | CONFIRMED LOW(今日等值:unit=="口" ⟺ market∈_FUT_MARKETS) | Nice to Have | `ask-user` | FillRecord 補 market vs docstring 明寫代理,二選一 |
| 14 | useCapital.ts:17 import 破格(CapitalFill 塞左大括號同行、非字母序) | LOW(c2) | CONFIRMED LOW(absence 佐證:chunk2 Read frontend/eslint.config.js → 僅 extends js.configs.recommended + tseslint.configs.recommended + react-you-might-not-need-an-effect,無 sort-imports/perfectionist/import-order;定稿時重核 grep(sort-imports / perfectionist / import-order 三 pattern)於 eslint.config.js = 0 命中、ls .prettierrc* = 0 → 無自動化會攔或會修) | Nice to Have | `auto-fix` | 移一行 |
| 15 | 四份測試檔殘留 orders/委託/avg_fill_price/filled_qty 敘述(GroupGridView.test 92-94/744/764、toggle 75/98-99、memo 182、StockChart.test 485) | LOW(c2) | CONFIRMED LOW(逐點命中核實;92-94 那句指名兩個已不存在的欄位最誤導) | Nice to Have | `auto-fix` | 掃一輪改口 |
| 16 | stock-accum fromSnapshot 的 disposition 對映零測試(兄弟欄 trial/tape_omitted 各有帶入+缺欄兩條) | LOW(c3) | CONFIRMED LOW(grep:disposition 在該檔僅 trialBadgeText 純函式四行) | Nice to Have | `auto-fix` | 照兄弟欄形狀補兩行 |
| 17 | test_fills_prune_on_day_change 名為 prune 實鎖讀時過濾:刪 prune 兩行 72 passed(mutation 實證);長跑記憶體不變量無觀測點 | LOW(c3) | CONFIRMED LOW | Nice to Have | `auto-fix` | 斷言 len(s._fills) 或改名明寫 |
| 18 | CapitalOrder.code 前端零讀者(群組卡已改吃 fills;orders 唯一比對路徑 aggregateLots 用 stock_no) | LOW(c3) | CONFIRMED LOW(grep 四個 orders 消費者零讀者) | Nice to Have | `ask-user` | 收掉 vs 註明保留理由(L435 契約完整性) |
| 19 | fill-marks.ts:111 `Map<string, FillPoint & { qty: number }>` 冗餘交集(FillPoint 已含 qty;量加權版殘留) | LOW(c3) | CONFIRMED LOW | Nice to Have | `auto-fix` | 改 Map<string, FillPoint> |
| 20 | 排版三處(stock-accum.test import 同行破格 / test_trading_calendar import 群 / test_engine 三空行)—— tooling 抓不到(ruff 無 E303/I,eslint 無排序) | LOW(c3) | CONFIRMED LOW(ruff/pyright 實跑全綠核實「抓不到」) | Nice to Have | `auto-fix` | 三處手修 |
| 21 | 個股期成交落現股卡 vs 單檔頁現貨態不撿:視圖不對稱是 L444 明示決定但未記進 docstring;卡上兩商品三角同形無區辨 | LOW(c3) | CONFIRMED LOW(readout 的 !card 閘已排除口/張混報 —— 這點查證後排除) | Nice to Have | `auto-fix` | fill-marks docstring 補一句代價 |
| 22 | TestTxoAutoBackfillDate 缺夜盤跨午夜例(_session_date→now.date() mutant 61 passed 全綠,mutation 實證);TestPreOpenPrevTradingDay 未斷 stock.trade_dates(同檔既有兩條有斷) | LOW(c3) | CONFIRMED LOW(mutant 的 prod 樣態:週六 02:00 活著的夜盤被改用固定日盤窗) | Nice to Have | `auto-fix` | 補週六 02:00 → None 一例 + 一行斷言 |
| 23 | fillOf 測試工廠兩份逐位元組相同(GroupGridView.test vs StockChart.test;另兩近親變體) | LOW(c3) | CONFIRMED LOW(diff 逐位核實;test-utils 抽取先例同理由) | Nice to Have | `auto-fix` | 抽共用 fixture(變體留各自) |

auto-fix 只是處置建議；沒有使用者另行下令，不修改 code、commit、push 或 PR。

F-01 finding_uid: 30e6348e17453804d2da action=auto-fix
F-02 finding_uid: 309ee52382bd1c8c4d2f action=ask-user
F-03 finding_uid: 7f0a1f07f111b2f0d5d7 action=auto-fix
F-04 finding_uid: cc8d5828844482a333e3 action=auto-fix
F-05 finding_uid: b8f21098ca7dd7c1eec4 action=auto-fix
F-06 finding_uid: 5a56b4a20c29a531be8d action=auto-fix
F-07 finding_uid: 09b1ae2d1a7d3b0bab03 action=auto-fix
F-08 finding_uid: 6e3febe74500e02bb253 action=auto-fix
F-09 finding_uid: 9c161d8f69fabcf22cc1 action=ask-user
F-10 finding_uid: 6a4d14cc8fd6c849863e action=auto-fix
F-11 finding_uid: 7d0e192b5d1dcb79f54d action=auto-fix
F-12 finding_uid: 8f92179eb92ba4a2ea1f action=auto-fix
F-13 finding_uid: 5a745b2bbf893c510929 action=ask-user
F-14 finding_uid: 7963ccecd8cf9e0e919a action=auto-fix
F-15 finding_uid: 9175a06be32a991bd5b9 action=auto-fix
F-16 finding_uid: 9c3b850b8880757b447c action=auto-fix
F-17 finding_uid: 419d1e8745333b42c12b action=auto-fix
F-18 finding_uid: 6a15fdf9558f1b428b46 action=ask-user
F-19 finding_uid: 21a5c404c060bae928e8 action=auto-fix
F-20 finding_uid: ef1a84f63c3330543045 action=auto-fix
F-21 finding_uid: b260ef753a6f537f44c7 action=auto-fix
F-22 finding_uid: 850ac70aad577c2bd2ff action=auto-fix
F-23 finding_uid: e0c73b4aa3737003af86 action=auto-fix
### Inline Comments per Finding
#### #1 延緩撮合亮不了(緩):值算對了,但沒有任何東西會把它推出去
**File**: `copycat/server/stock_engine.py`
**Line**: 668

**Comment**:
```
_trial_now 第二段的值是對的,但推播端沒跟上:_dirty_watchlist.add 只在
state.ingest(tick) 成立時發生,而延緩撮合的定義就是期間沒有成交 tick ——
探針實證:TradeStatus 0→1 後 _publish 捕獲 0 則;恢復那筆成交到達時
TradeStatus 已回 "0",唯一那則 quote 帶 trial=False。群組 60s 輪詢的
group_snapshot payload 也沒有 trial/disposition 鍵(accumFromGroupSnapshot
硬寫 false)。整段 episode 兩個主畫面都不亮,(處置) 同死。
修法:_observe_trade_status 偵測到「轉態且改變 _trial_now(code) 答案」時,
自選碼入 _dirty_watchlist、主圖沿 1655 的繞過式 publish(收件人規則 =
_trial_flip_targets 既有那套);補一條「status 0→1 → WS 收到 trial=True 的
watchlist_quote」測試 —— 現有三條新測全是直呼內部方法,鎖不住這件事。
```
#### #2 昨晚的成交三角,過了午夜就從期貨圖上消失
**File**: `copycat/capital/store.py`
**Line**: 247

**Comment**:
```
fills() 與 prune 都只留「到達本機日 == 今天」,但期貨近全軸一張圖跨兩個日曆日
(D−1 15:01 → D 13:45)。00:00 一過,昨晚 22:00 的成交就不再回傳,圖上那顆三角
靜默消失(軸還在、圖照畫、零訊號)。近似版吃 orders(_orders 不 prune)沒這條界,
所以是本 PR 的真回退;失真起點是 00:00,日盤段照畫。
注意修法:「留今+昨」不夠 —— 週五夜盤錨定到週一,date 是週五/週六,「今+昨」
在週一濾不到 → 週一整段夜盤三角仍空。保留窗要以錨定交易日(或上一交易日往前
含週末)為鍵,怎麼切要拍板。前端不會因後端多回幾天而多畫(fillPoints/fillsByCode
有今日閘、alldayFillPoints 有錨定日閘 —— 已驗)。
```
#### #3 L444 的反查分支,拿掉 if 全套照樣綠
**File**: `tests/server/test_capital_api.py`
**Line**: 1302

**Comment**:
```
新的兩條測試只斷 code == stock_no(現股恆等分支);把 _fill_code 的
unit=="口" 反查整段拿掉改 return stock_no,全套 3240 條照綠(mutation 實測)。
而那正是「個股期成交落到該股的卡」的全部意義 —— 改掉 unit 字面值或反查壞掉,
圖牆一個三角都不長、零訊號。前端 fill-marks 那條 L444 案是手寫 code fixture,
測分組不測反查。補一例期貨成交(市場欄 TF)斷言 code 是反查後股號、未知契約碼
回 None,口徑對齊同檔上面的 test_positions_carry_code(那條就是正確做法)。
```
#### #4 ident 是代理值,每天兩次白做全鏈重交接
**File**: `copycat/server/app.py`
**Line**: 633

**Comment**:
```
rollover 判準比 (session_key(), auto()),真正決定回補窗的是 tc4._backfill_window()。
凍時鐘 24h 求值:08:00(session_key ymd 翻)與 13:46(auto None→今日)ident 變了
但實際窗一模一樣 → 各觸發一次 agg reset + 280 檔 SubHistory。13:46 那發是本 PR
新增;兩發都在安靜時段、資料不會錯,所以只是浪費。
修法:把 _backfill_window 的選擇邏輯抽成純函式(吃 env/auto/session_key 回窗),
tc4 與 window_ident_fn 共用 —— 「ident 變 ⇔ 窗變」變成定義,順帶消掉同一決策
寫兩個檔的漂移風險。
```
#### #5 market→(div,unit) 這張表現在有兩份
**File**: `copycat/capital/store.py`
**Line**: 221

**Comment**:
```
_append_fill_locked(220-225)與 _to_record(516-521)逐字同一張五行表,
且除不盡的處理已經分岔(新的退回股、舊的靜默捨)。unit 是 §4 列管的跨語言
契約字面值,讀者含前端兩個排除鍵 —— 兩份各自維護,漂掉的樣態是同一筆成交
在梯與圖上單位判定不同,零訊號。抽個 _lot_unit(market) 放 _SEC_LOT_MARKETS
旁邊,兩處共用,除不盡的處理選一種寫進去。
```
#### #6 useCapitalFills 又走回 N068 修掉的那條路
**File**: `frontend/src/hooks/useCapital.ts`
**Line**: 169

**Comment**:
```
同檔 184-192 行為 positions 寫的 N068 結論(讀取端不帶 refetchInterval、
節奏收斂 provider)就在旁邊,新 hook 卻是 per-observer 30s。三掛載點裡
FuturesChart(hidden 保留 DOM)與 StockChart 會並存 → 相位不定的雙發。
量級校正過:改前三處吃 capital-orders 同型輪詢,總發數大致持平,
所以是「形狀違規」不是流量暴增。照 positionsQueryOptions 樣板抽
fillsQueryOptions(false) + provider 掛一份即可。
```
#### #7 呼叫點註解說「反查留給精確版」,但精確版就是這次
**File**: `frontend/src/components/stock/GroupGridView.tsx`
**Line**: 318

**Comment**:
```
312-318 還寫著「群組卡只認現股(契約碼→股號反查留給精確版)」「同一份 orders」——
本 PR 剛好把這兩件事都改掉了(fillsByCode 分組鍵 = wire code、資料源 = fills),
fill-marks.ts:202-203 寫著正好相反的話。這 repo 把註解當契約用,兩份互相矛盾
零訊號。重寫這六行:orders→fills、「反查已到位(L444),excludeUnit 只排零股」。
```
#### #8 disposition 三條新分支沒有測試釘
**File**: `frontend/src/hooks/useStockStream.ts`
**Line**: 394

**Comment**:
```
useStockStream.test 對 trial 有六條專屬案,disposition 零命中:解碼(394)、
pendingTrial 攜帶(425)、accum 守門(428)三條都能被靜默拔掉 —— 拔掉 428 的
|| acc.disposition !== q.disposition,處置股 header 會一直印(緩)而側欄是對的,
同畫面兩處對同一檔給不同答案。(status.engine 缺欄預設那條 App.test 有蓋,
不在此列。)比照緊鄰的 trial 測試補三條即可。
```
#### #9 FinMind 掛掉那天,(處置) 標的是昨天的名單
**File**: `copycat/server/breadth_engine.py`
**Line**: 475

**Comment**:
```
disposition_codes() 直回 self._disposition,不看 _disposition_ok(取數失敗時
名單保前值、ok 打 False)。既有消費者 assemble_universe 同樣不看,「保前值」
是這引擎的明文政策 —— 但新 accessor 的 docstring 兩種都沒說。二選一表個態:
(a) not ok 時回空集合(降級 = 全部照標(緩));(b) 明寫「刻意沿用前值 ——
處置期本來就跨多日,舊名單比空集合準」。順手把回傳型別收 AbstractSet
(已核:消費端 stock_engine.py:256 的參數型別正是 Callable[[], AbstractSet[str]],
同檔 :18 已 from collections.abc import Set as AbstractSet —— 收斂方向與既有型別一致)。
```
#### #10 __all__ 漏了新函式
**File**: `copycat/trading_calendar.py`
**Line**: 34

**Comment**:
```
resolve_trade_date 在 __all__ 裡、姊妹函式 resolve_trade_date_before 沒進去。
加一行,清單才繼續可信。
```
#### #11 「唯一呼叫者」又多了一個
**File**: `copycat/server/app.py`
**Line**: 467

**Comment**:
```
_session_date docstring 說「目前唯一這樣問的是 _heal_gate」—— _txo_auto_backfill_date
(369)是第二個。這段 docstring 自己就寫過「逐個列呼叫點,新增一處就漏一處」,
這次正好示範了。改成判準式(「呼叫點 grep _session_date」)一勞永逸。
```
#### #12 §4 的 unit 契約條少登了一個產生點兩個讀者
**File**: `CLAUDE.md`
**Line**: 161

**Comment**:
```
OrderRecord.unit 條還只寫產生點 _to_record + 讀者 ladder-lots.ts;本 PR 加了
產生點 _append_fill_locked、讀者 fill-marks.ts excludeUnit 與 capital_api.py
unit=="口"(後者還是行為分支,見 #13)。§4 是唯一的跨檔契約登錄簿,
下一個改 unit 字面值的人現在拿到的是缺頁清單。
```
#### #13 用「口」這個顯示字串當期貨判準
**File**: `copycat/server/capital_api.py`
**Line**: 245

**Comment**:
```
positions 判期貨用 p.market,orders/fills 的 _fill_code 用 unit=="口" ——
同檔兩把尺(今天等值)。unit 本來是純顯示/前端過濾字面值,現在多了一個後端
行為分支:改掉「口」→ 反查靜默不觸發 → L444 整個死、零訊號。
FillRecord 補個 market 欄同 positions 那把尺,或 docstring 明寫
「本支以 unit 當代理,改 unit 字面值 = 改後端行為」。哪條要拍。
```
#### #14 import 一行破格
**File**: `frontend/src/hooks/useCapital.ts`
**Line**: 17

**Comment**:
```
CapitalFill 塞在 import type { 同一行、也不在字母序 —— editor auto-import
沒收好的指紋。移到自己一行、放 CapitalDecreaseBody 之後(已核:該名列於
useCapital.ts:21,次行即 CapitalFutureOrderBody,字母序位置正確)。
```
#### #15 四份測試檔還在講 orders 的故事
**File**: `frontend/src/components/stock/GroupGridView.test.tsx`
**Line**: 92

**Comment**:
```
fixture 已改 CapitalFill(price/qty),docstring 還教人 avg_fill_price 是元、
filled_qty 是張 —— 兩個欄位都不存在了。toggle 測試的註解指名 useCapitalOrders,
正下方那行已是 /api/capital/fills。四檔掃 orders|委託|avg_fill_price|filled_qty
一輪改口(StockChart.test:485 的 test name 也含「同一份 orders」)。
```
#### #16 fromSnapshot 的 disposition 沒測
**File**: `frontend/src/lib/stock-accum.test.ts`
**Line**: 678

**Comment**:
```
trial 有帶入+缺欄兩條、tape_omitted 有一條,disposition 只有 trialBadgeText
純函式四行 —— snap.disposition ?? false 改成 false 是綠的。照兄弟欄形狀補兩行。
```
#### #17 prune 測試其實測不到 prune
**File**: `tests/capital/test_store.py`
**Line**: 974

**Comment**:
```
fills() 讀時再濾一次日期,所以把 _append_fill_locked 的 prune 兩行刪掉,
這條與姊妹條都綠(mutation 實測 72 passed)。prune 守的是長跑記憶體不累積
(119-120 註解寫的),現在沒有觀測點。斷言 len(s._fills) == 1(同檔有讀私有態
先例),或改名明寫「prune 只是記憶體最佳化」。
```
#### #18 orders 的 code 欄沒人讀
**File**: `frontend/src/types.ts`
**Line**: 102

**Comment**:
```
群組卡已改吃 fills,orders 唯一比對路徑 aggregateLots 用 stock_no ——
CapitalOrder.code 前端零讀者,後端多算一次反查、wire 多一欄。
收掉等有消費者再加,或註明「目前無讀者,為 L435 契約完整性保留」。要拍。
```
#### #19 量加權版退役的殘留交集型別
**File**: `frontend/src/lib/fill-marks.ts`
**Line**: 111

**Comment**:
```
Map<string, FillPoint & { qty: number }> —— FillPoint 本來就有 qty,交集恆等。
舊版 Bucket 有 amount 才需要獨立型別。改 Map<string, FillPoint>,
免得讀者去找「哪裡的 FillPoint 沒有 qty」。
```
#### #20 三處排版指紋(工具抓不到)
**File**: `tests/server/test_engine.py`
**Line**: 969

**Comment**:
```
stock-accum.test:3 import 同行破格、test_trading_calendar:13 datetime import
插錯群、test_engine 這裡 class 前三空行。ruff 沒開 E303/isort、eslint 沒有
import 排序 —— gate 不會紅,只能人工收。三處手修。
```
#### #21 圖牆看得到、點進去看不到:這個不對稱沒寫下來
**File**: `frontend/src/lib/fill-marks.ts`
**Line**: 203

**Comment**:
```
個股期成交靠 code 反查落到現股卡(L444 明示決定),但單檔頁現貨態走 stock_no
比對撿不到同一筆 —— 使用者在圖牆看到三角、點進去就沒了;卡上期貨價與現貨價
的三角同形無區辨。這是接受了的設計代價,但沒寫在任何 docstring。
fillsByCode 的註解補一句:「單檔頁現貨態刻意不撿(比對鍵 stock_no);
卡上不區辨商品」。(口/張混報那條查證後排除:卡片不渲染 readout。)
```
#### #22 TXO 自動日的夜盤跨午夜段沒測到
**File**: `tests/server/test_calendar_wiring.py`
**Line**: 523

**Comment**:
```
把 _session_date() 換成 now.date() 這個 mutant,現有五案全綠(61 passed 實測)——
prod 樣態是週六 02:00(週五夜盤活著)auto 回 20260814,live 夜盤被改用固定日盤窗。
補一例凍在週六 02:00 → 斷言 None。另外 TestPreOpenPrevTradingDay 用了
RecordingStockSource 卻沒斷 stock.trade_dates(同檔 199/216 有斷)—— 加一行。
```
#### #23 兩份逐位相同的測試工廠
**File**: `frontend/src/components/stock/StockChart.test.tsx`
**Line**: 37

**Comment**:
```
GroupGridView.test 與 StockChart.test 的 fillOf 逐位元組相同(連 docstring 差異
都沒有),另兩檔有近親變體。CapitalFill 加欄時四份要一起改 —— test-utils 抽 wrap
時寫過同一個理由。逐字同的兩份抽到共用 fixture,變體留各自。
```
