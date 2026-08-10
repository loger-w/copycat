# change-spec:部位 store 鍵位改造 (stock_no, kind)(mod/capital-position-key-kind)

分流判定:user 帶已成形改法(next-time 查證註記指明範圍:store 鍵 + 移除 sec dedupe +
平倉帶 kind + REST/前端連動),但兩個子決策留給 spec 拍板(fut 合併語意 / backward
compat)→ grilling 確認 + 拍板記錄如下,無 counter-proposal。M 級(後端 4 檔 + 前端
2-3 檔 + wire 契約)。

## 拍板([auto-default],依據附理由)

1. **fut 淨額合併(merge_fut_positions)保留**:淨額 = 可平倉曝險(期交所同契約多空
   本就淨額);且 fut 列 kind 恆 "cash",複合鍵下同契約多列仍會互蓋 — 合併仍必要。
   不保留的話 B/S 兩列同鍵互蓋成後到列,回到 review A5 修掉的 bug。
2. **平倉 kind 為 optional + 歧義阻擋**:`PositionCloseRequest.kind: str | None = None`。
   sec:kind 有值 → 精確查 (key, kind);None → 同檔唯一列則用之,**多列 → 阻擋**
   (CapitalGateBlockedError,文案「多種庫存並存,請指定種類」)— fail-safe,絕不猜。
   fut:kind 忽略(fut 列恆 "cash",以 (key, "cash") 查)。
   前端一律帶 kind(單一 in-repo 消費者),optional 只為 wire 演進安全。

## 成功條件(可驗收)

- SC-1:sec 同檔資+集保並存 → store 兩列(qty/均價各自)、`GET /api/capital/positions`
  回兩列;不再有「留張數大者」的丟列。
- SC-2:平倉精確鍵到:req 帶 kind=margin → `build_close_order` 拿融資列(送融資賣);
  kind 未帶且同檔多列 → **403 `{detail:{error:"ORDER_BLOCKED", reason:"…請指定種類"}}`**
  (audit blocked 留痕)[amendment 2026-08-05: review P1-2 — 既有契約是 403 ORDER_BLOCKED
  (capital_api.py CapitalGateBlockedError handler + test_capital_api:429-430 已鎖),
  原寫 400 GATE_BLOCKED 與白名單 6 自相矛盾,更正];
  kind 未帶且唯一列 → 照舊成功(backward compat)。
- SC-3:fut 行為零改變:淨額合併、平倉路徑、A7 沿用上一輪 — 既有測試全綠不改。
- SC-4:損益回填按 (stock_no, kind) 各自回填 — 同檔資+集保兩列各拿自己種類的
  均價/pnl_base(client `_on_profit_complete` 與 store `apply_profit_rows` 兩處)。
- SC-5(畫面可指認):sec 部位列的種類小字標籤**置於代號 span 內**(`2330 台積電` 後接
  `<span className="ml-1 text-ink-dim">資</span>`;現股=現 / 融資=資 / 融券=券)—
  GRID 六欄與表頭**不動**[amendment 2026-08-05: review P2-1 — 獨立欄會讓六欄 grid 錯位,
  置於代號 span 內既有 regex 文字斷言不受影響]。可觀察描述:同檔資+集保並存時,
  畫面**同時**看到「2330 …現」與「2330 …資」兩列、各自平倉鈕可點且送出的 body kind
  不同(cash / margin 各一)。fut 列表外觀不變。React key 唯一性驗證走
  console.error spy(斷言無 duplicate key warning)或上述行為斷言
  [amendment 2026-08-05: review P2-3 — 「渲染不 crash」恆綠 vacuous,撤回]。
- SC-6:gate 全綠:pytest / ruff / pyright / validate + frontend npm test / tsc / eslint。
- SC-7(真實環境):下次自然重啟後 `GET /api/capital/positions` 形狀正常、面板部位列
  正常顯示(單一種類帳戶下畫面與現況一致)。注意 memory:群益夜間登入 fail 待白天觀察,
  真環境證據允許延至白天 session。

## 不能破壞的既有行為白名單

1. 委託聚合(store._orders / orders() / remaining_shares / market_of)完全不動。
2. fut 淨額合併語意(test_balance merge 測試)+ A7「OI 失敗沿用上一輪 fut」不變。
3. 查詢串行鏈(balance → profit → OI)節奏、collector flush、pending 逾時 watchdog 不變。
4. `_CLOSE_MAP` 平倉映射(融資→融資賣 / 融券→融券買回等)與 close 各 ValueError 文案不變。
5. close 防重送(10s inflight)與同向活躍委託 guard **語意保留**
   [amendment 2026-08-05: review P0-1 — 精確化:**inflight 的寫入/讀取/過期清理三端
   同用複合鍵**(讀取與清理住在 `_close_dup_reason` 內,client.py:776/:780 — 只改寫入端
   會讓 sec 10s 防重送整層失效);**活單掃描**仍以 (stock_no, side)。兩個鍵語意不同,
   顯式分離為兩個參數]。同檔兩種類同向平倉,第二筆會被「已有同向活躍委託」擋,
   為接受的保守行為(safety-first,spec 註記非 bug)。
   既有 `test_close_sec_builds_reverse_order_and_blocks_second_inflight`(test_client.py
   :764-768,同種類第二次含「在途」且只送一單)**不該紅 — 行為必須保住**。
6. API error shape `{detail: {error}}`;WS `capital_position` event 形狀(count)不變。
7. set_positions 全量替換語意 + 同鍵沿用均價/損益基底(現由 `prev.kind == p.kind` 防呆,
   複合鍵後由鍵天然保證 — 可觀察行為不變)。
8. profit row kind=None(未知標籤)略過的寧缺語意不變。
9. 前端 fut 列表顯示與 futures-ladder / FuturesPage 的部位消費不變(fut 無同契約多列,
   由拍板 1 保證)。

## Backward compat / migration

- 無持久化,store 純 in-memory — 無 migration。
- wire:positions rows 形狀不變(既有 kind 欄),語意 additive(同檔可多列);
  close body 加 optional `kind`(舊 body 不帶 → 唯一列 fallback,多列 fail-safe 阻擋)。
- `position_for` 簽名改 `(stock_no, kind=None)`(kind=None = 唯一匹配否則 None)—
  repo 內 caller 全列於 current-state,一次改完;無外部 caller。

## Out of scope

- 委託(orders)面的任何改動。
- dup guard 按 kind 細分(白名單 5 的保守行為維持)。
- fut kind 語意化(留 "cash" 預設)。
- 手續費/損益計算邏輯。

---

# Diff 級 spec(Phase 3)

## 🔴 行為改動(該紅測試先改)

### copycat/capital/store.py
- `_positions: dict[tuple[str, str], Position]`(鍵 = (stock_no, kind))。
- `set_positions`:carry-over 查 `old.get((p.stock_no, p.kind))`,`prev.kind == p.kind`
  條件移除(鍵已保證);發布 dict comprehension 改複合鍵。
- `apply_profit_rows`:`r.kind` None → skip;`self._positions.get((r.stock_no, r.kind))`
  回填。(註:此方法 prod 路徑無 caller — grep 僅測試使用;仍同步改,行為契約由
  test_store 鎖。)
- `position_for(stock_no: str, kind: str | None = None)`:kind 有值 → get((stock_no, kind));
  None → 掃描同 stock_no 列,恰一列回傳、否則 None。
- `positions()` 不變(list of values,插入序)。

### copycat/capital/balance.py
- **刪除 `dedupe_positions`**(補償層)。
- `merge_fut_positions` 邏輯保留,**docstring 更新**[amendment 2026-08-05: review P2-4 —
  「store 以 stock_no 為鍵,B/S 兩列同 key 互蓋」在複合鍵後變假事實,留著會誘導下一個
  讀者刪掉 merge(回到 review A5 bug);理由改寫為「fut 列 kind 恆 cash,複合鍵下同契約
  仍同鍵」]。store.set_positions 的「同種類才沿用」註解同步改(鍵已含 kind,天然同種類)。

### copycat/capital/client.py
- `_on_balance_complete`:`self._pending_sec = positions`(不再 dedupe;import 移除)。
- `_on_profit_complete` [amendment 2026-08-05: review P1-3 — 單次複合鍵 lookup 會把
  「查無股號(靜默,權威=即時庫存)」與「種類不符(warning)」合併,且 balance 側
  被丟的列(零股不足 1 張 / 未知種類)在 profit 報告仍有列 → 每 60s 洗版 warning。
  維持**兩段判別**]:先 `same_no = [p for p in pending if p.stock_no == r.stock_no]`
  (空 → **靜默** continue,原語意);非空再 `by_key.get((r.stock_no, r.kind))`,
  None 才 warning(文案保留「profit row 種類不符略過: %s 報告=%s 部位=%s」,
  部位欄填 same_no 的 kind 清單)。
- `close_position` sec 分支:`pos = self.store.position_for(req.key, req.kind)`;
  pos None 且 `req.kind is None` 且同檔多列 → 阻擋文案「{key} 多種庫存並存,請指定種類」
  (判別:`position_for` 回 None 時以 `positions()` 數同檔 sec 列數;兩次讀之間的
  競態後果只是文案差異,可接受)。
  fut 分支:`position_for(req.key)`(kind=None 唯一匹配 — 與現況行為逐字等價)
  [amendment 2026-08-05: review P2-5 — 原寫死 "cash" 依賴「parse_open_interest_line
  不設 kind」的隱形不變量,而 OnOpenInterest 欄序 prod 校正(next-time 既有條)可能
  順手動它 → 失效樣態是 fut 平倉靜默「無部位可平」;唯一匹配零新假定]。
- **inflight / 活單掃描兩鍵顯式分離**[amendment 2026-08-05: review P0-1]:
  - close_position 解析出 pos 後組 `inflight_key = f"{req.key}:{pos.kind}"`(sec)/
    `req.key`(fut)。
  - `_close_dup_reason(inflight_key, scan_key, side)`:inflight 的 get/del(:776/:780)
    用 inflight_key;orders 活單掃描(:783 `o.stock_no == scan_key`)用 scan_key=req.key。
  - `_submit_close_locked(req, inflight_key, submit)`:set/pop 同用 inflight_key。
  - 效果:同檔兩種類 inflight 互不阻擋;同一種類 10s 防重送**必須保住**(既有測試不紅)。
- `PositionCloseRequest`(models.py):加 `kind: str | None = None`(audit 走
  asdict(req) 自動入帳,無需另處理 — reviewer 已查證)。

### copycat/server/capital_api.py
- `PositionCloseBody` 加 `kind: str | None = None`;route 傳入 req。

### frontend(SC-5)
- `types.ts`:`CapitalCloseBody` 加 `kind?: string`(型別檔實際位置以 grep 為準)。
- `CapitalPositionsList.tsx`:
  - rowKey = `` `${p.stock_no}:${p.kind}` ``(React key + closingKey 皆用)。
  - `closing` 查找以 rowKey 比對。
  - `confirm()` body 加 `kind: closing.kind`。
  - sec 列(market === "sec")代號後加種類小字:`{現|資|券}`(kind → 現股 cash=現 /
    margin=資 / short=券;fut 不顯示)。確認彈窗 rows 亦補一列「種類」(sec only)。
- `CapitalPositionsList.test.tsx`:close body 斷言補 kind;新增同檔兩列案例。

## 既有測試標記

[amendment 2026-08-05: review P1-1/P1-4/P2-2 — 逐檔補標]

- 該紅/該改(🔴):
  - tests/capital/test_balance.py 的 dedupe_positions 測試群 → **刪除**(函式移除)。
  - tests/capital/test_store.py:`test_set_positions_carries_profit_same_kind_only`
    (position_for 單參呼叫 + 換 kind 語意)→ 改寫為複合鍵語意(換 kind = 不同列,
    可觀察結果同「不沿用」)。
  - tests/capital/test_store.py:`test_apply_profit_rows_fills_existing_only`(:277-295)
    → **必紅**:部位 kind="margin" 而 ProfitRow kind 走預設 None,新 skip 規則整列略過
    → 改為 ProfitRow 補 `kind="margin"`,另加一筆 kind=None 驗證 skip(P1-1)。
  - tests/capital/test_client.py:783 `assert "2330" not in client._close_inflight`
    (A8 解鎖回歸)→ 複合鍵下**恆真變 vacuous**(不紅但失去驗證力)→ 改斷言複合鍵
    `f"2330:cash" not in ...` 或行為斷言(P1-4;fut 對照 :799 不動)。
  - frontend CapitalPositionsList.test.tsx:close body 斷言在 **:156**(:142 是 mock
    route 註冊,原行號引用錯)且為 `toMatchObject`(容忍多欄,補 kind 不會先紅)→
    改 `toEqual({..., kind: "cash"})` 或補 sec 案例 `toHaveProperty("kind", "margin")`
    作為先紅測試(P2-2)。
- 不該紅(逐檔):
  - tests/capital/test_balance.py merge_fut_positions 測試群(邏輯不動)。
  - tests/capital/test_close.py 全部(build_close_order 吃 pos,不碰 store)。
  - tests/capital/test_client.py sec close 測試群(:752/:764-768/:802/:813)—
    單一 kind 情境,kind=None 唯一匹配 fallback 行為等價;**:764-768 的同種類
    10s 防重送尤其必須綠**(P0-1 行為保證)。**:771 排除在外**:不紅但斷言恆真,
    見上方該改清單(:783 複合鍵斷言)[amendment 2026-08-05: round 2 P2-R2-1 —
    同一測試不得同列兩清單]。fut close(:791-799)、串行鏈、orders 全部。
  - tests/server/test_capital_api.py(:224/:438 單列 set_positions;close 路由透傳)。
  - frontend RightRail.test.tsx / useCapital.test.tsx / FuturesPage.test.tsx —
    消費端只讀 stock_no/qty/market(reviewer grep 確認),單列 fixture 下渲染不變。
    [amendment 2026-08-05: round 2 P2-R2-3;code review F-3 再更正]RightRail.test.tsx
    :283/292/300 實為**委託列**(CapitalOrdersList)測試,與本輪無關;RightRail 部位
    測試走 role 查詢對代號文字零斷言。**硬性要求不變:種類標籤必須是代號 span 的獨立
    子元素**(`<span>2330 台積電<span>資</span></span>`),但真正的守門是
    **CapitalPositionsList.test.tsx:185** `getAllByText("2330 台積電").length == 2`
    (標籤併入文字節點 → getNodeText 變「2330 台積電資」→ 該斷言紅)。

## 新測試清單(🟢)

- test_store:同檔兩 kind 並存兩列;position_for 精確/唯一/歧義三態;
  set_positions 複合鍵 carry-over(同鍵沿用、異鍵不沿用);apply_profit_rows 複合鍵回填
  + kind None skip。
- test_balance:(dedupe 測試刪除後)無新增 — sec 直通行為由 client 測試鎖。
- test_client:資+集保並存全鏈(balance → profit 各自回填 → finalize 兩列);
  close 帶 kind 精確鍵到(融資列送融資賣);close 無 kind + 多列 → GateBlocked(文案含
  「請指定種類」);close 無 kind + 唯一列 → 成功;**同檔兩種類 inflight 互不阻擋 +
  同一種類第二次仍被「在途」擋**(P0-1 兩面都鎖);profit 報告含 balance 側被丟的股號
  → 靜默不 warning(P1-3 兩段判別)。
- test_capital_api:close body 帶 kind 透傳;positions 回兩列;歧義 → **403 ORDER_BLOCKED
  + reason 含「請指定種類」**(P1-2)。
- frontend:同檔兩列渲染(各自種類標籤可見)+ 各自平倉鈕;close body 含 kind;
  React key 唯一:console.error spy 斷言無「Encountered two children with the same
  key」,或行為斷言(兩列平倉鈕各自送出 kind=cash / kind=margin)
  [amendment 2026-08-05: round 2 P2-R2-2 — 與 SC-5 撤回 vacuous 測試對齊]。

## Commit 計畫(三類分離)

- 🔴 backend 一包:該紅測試先改(dedupe 刪 / store 簽名 / profit-rows kind / inflight
  vacuous 斷言)→ store/balance/client/api 實作(含註解更新)→ 綠。
- 🔴 frontend 一包:close body + rowKey + 種類標籤(test 先紅:toEqual body 斷言 +
  兩列案例)。
- 🟢 防回歸新測試(上列 🟢 清單中非 🔴 必要者)。
- chore:勾銷 docs/next-time.md:111(review P2-6;註明 dedupe 補償層已移除、
  平倉可指定種類)。
  (無 🔵)。順序:🔴 backend → 🔴 frontend → 🟢 → chore。

self_review_head: 4b7a011894a46c4d896736ddd24466ef896f3e5b
