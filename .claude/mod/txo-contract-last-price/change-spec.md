# change-spec:TXO snapshot 補推 per-contract last_price(mod/txo-contract-last-price)

分流判定:user 帶已成形改法(next-time 查證註記指明 aggregator 逐 tick 記最近成交價 +
snapshot additive 加欄;前端已預留)→ grilling 縮成確認,無 counter-proposal。S 級。

## 成功條件(可驗收)

- SC-1:合約有成交後,snapshot `contracts[i].last_price` = 該合約**時序最後**一筆成交價
  (單位:點,float,= 內部毫點 /1000;對齊 `spot.price` 慣例與前端 ContractRow 註解)。
- SC-2 [amendment 2026-08-05: review P1-1 — 原「零成交 → null 欄位」情境在 code 上不存在
  (`_pos` 只在 `_ingest` 建 row,零成交合約不出現在 contracts),改寫為事實]:
  零成交合約**不出現在 contracts**(既有行為,不變);前端
  `contracts.find(...)?.last_price ?? null` 因此取到 null → 市價鈕維持鎖定。
  `_contract_rows` 的 `else None` 分支為防禦性死碼(型別 `int | None`),保留不另補測試。
  [amendment 2026-08-05: review S-2 落地後過時 — 0 價閘(`> 0` 才記價)使 `else None`
  變**可達路徑**(整檔只收過 0 價 tick → last_price: null),已補測試
  test_zero_price_only_contract_reports_null_last_price 涵蓋]
- SC-3:未分類 tick(價格不貼 bid/ask)也更新 last_price(成交價與內外盤分類無關);
  stale-drop(cum 序)的 tick **不**更新。
- SC-4:backfill 路徑(ingest_backfill)同樣產出 last_price(排序後最後一筆);
  `reset()` 後歸零(隨 _pos 清空)。
- SC-5:gate 全綠(pytest / ruff / pyright / validate);前端 `npm test` + `npx tsc -b` +
  `npx eslint src` 不動也綠(本輪不動 frontend/,但 wire 契約連動需確認無前端紅)。
- SC-6 [amendment 2026-08-05: review P1-3 — 動機(OrderPanel 市價解鎖)補驗收條件]:
  前端不改 code 的前提下,有 last_price 的合約:市價選項可選、送單鈕不再因估價缺值
  disabled、確認框預估權利金 = last_price × 口數 × 50(TXO_MULTIPLIER);
  **不在 snapshot.contracts 的合約(當日零成交)仍鎖 — 為預期行為**,驗收時不得誤判為
  「沒修好」。此為行為改動(市價鈕從恆 disabled → 可用),不是 out of scope。

## 不能破壞的既有行為白名單

1. 內外盤分類 / net_qty / volume / cum stale-drop 語意完全不變(test_contracts_invariants)。
2. contracts 排序(strike 升冪、同 strike C 前)不變。
3. snapshot 其餘欄位(curve/beps/totals/spot…)零改動;golden 除 contracts 加欄外
   其餘部分 byte-level 不變(regen.py 的非 contracts 比對必須 0 diff)。
4. 前端 OrderPanel 缺值鎖市價行為不變(OrderPanel.test.tsx:214/:231 不動)。
5. `route` 的 spot 分流與 foreign 丟棄計數不變。

## Backward compat / migration

wire 契約 additive:前端 `ContractRow.last_price?: number | null` 已預留(「契約只加不改」
已預告),舊消費端不讀新欄零影響。無持久化、無 migration;golden fixture 以 regen.py 重生
(該工具自檢非 contracts 部分 0 diff 才覆寫)。

## Out of scope

- 前端 **code** 任何改動(行為連動見 SC-6,屬本輪行為改動的一部分;改的只有後端)。
  [amendment 2026-08-05: review P1-3 — 原「前端任何改動」措辭撤回]
- last_price 的時效標記(如成交時刻)。[amendment 2026-08-05: review P2-2 — 理由更正:
  送單價走市價 literal M(capital/mapping.py:161,market+ROD 另升 IOC),last_price 僅供
  安全閘(safety.py `_check_qty_amount` 名目估算)與確認框顯示,stale 價不會被送出交易所;
  「確認框金額為估算、冷門履約價可能為舊價」記 next-time]
- 其他 snapshot 欄位擴充。

---

## Known Risks

1. [amendment 2026-08-05: code review S-1 裁決]市價估價來源(snapshot last_price)掛在
   會被 `reset()` 清空的累積狀態上:序列切換 / self-heal / 盤別 rollover 後 contracts 空
   到回補完成(可達分鐘級),期間市價鈕鎖回、**已開的確認框因 `premium != null` render
   gate 靜默卸載**、handleConfirm 靜默 return。失效方向 fail-safe(鎖回 = 回到本輪前狀態;
   送單走市價 literal M,不會送錯價),但 UX 無訊息。修法((2) 前端沿用上一份估價標示
   「回補中」/(3) dialog gate 拆分 + setSubmitError)屬前端獨立輪 — 記 next-time。
   後端「last_price 跨 reset 存活」經評估無效:rows 隨 `_pos` 消失,單保價值不恢復 row。

---

# Diff 級 spec(Phase 3)

## 🔴 行為改動(該紅測試先改)

- `tests/live/test_aggregate.py::test_snapshot_contracts_detail`:期望 rows 各補
  `"last_price"`(C44000 = 99.5 — 未分類 3 @99.5pt 是時序最後一筆,同時鎖 SC-3;
  P44000 = 50.0)。
- `tests/live/test_replay_golden.py`:golden 全等 → 以 `tests/fixtures/txo_golden/regen.py`
  重生 `expected_snapshot.json`。
  [amendment 2026-08-05: review P1-2 — regen.py 的自檢是把兩側 contracts **整段 pop 掉**
  再比對(contracts 區塊無條件覆寫),重生後的 golden 對 last_price 值零約束
  (self-fulfilling)。補兩道驗證力:
  (1) 覆寫後以 `git diff tests/fixtures/txo_golden/expected_snapshot.json` 為證據,
  要求 diff **只有新增的 `"last_price": …` 行、零修改行**(檔案 indent=1 每 key 一行,
  可機械判)— 讓白名單 3 從宣稱變可驗;
  (2) 新增一條**不吃 golden 的真實資料斷言**(tests/live/test_replay_golden.py 內新測試):
  直接讀 ticks.jsonl,按 (PreciseTime, QryIndex) 排序取每 symbol 最後一筆 TradingPrice,
  逐檔與 snapshot 的 last_price 比對 — golden 被覆寫後仍獨立成立]

## 實作內容(隨 🔴 commit)

[amendment 2026-08-05: review P1-4 — 本輪唯一的行為改動 = snapshot contracts 加
last_price(含前端市價鈕連動,SC-6),實作整包歸 🔴;原「🟢 新功能」標記撤回,
🟢 commit 只放事後補的防回歸新測試]

- `copycat/live/aggregate.py`:
  - `_PosState` 加 `last_price_millipts: int | None = None`。
  - `_ingest`:過 stale-drop 後 `pos.last_price_millipts = tick.price_millipts`
    (放分類 if/elif/else 之前 — 三分支皆更新)。
  - `_contract_rows`:加
    `"last_price": st.last_price_millipts / 1000 if st.last_price_millipts is not None else None`。
- 新測試(tests/live/test_aggregate.py):
  1. 零成交合約 row `last_price is None`(SC-2;構造:有 book 更新無成交?— 注意 `_pos`
     只在 `_ingest` 建 row,零成交合約不會出現在 contracts;實際斷言 = **有成交的合約**
     之外不會有 row,SC-2 的 null 路徑由既有「_pos 無該檔 → 無 row」與前端 `?.last_price
     ?? null` 涵蓋 — 測試改為:單一合約兩筆成交後 last_price = 第二筆價(時序最後)。
  2. stale-drop tick 不更新 last_price(SC-3)。[amendment 2026-08-05: review P2-1 —
     構造寫死:tick helper 預設 cum=None 不會登記 `_last_cum`,必須顯式帶 cum:
     第一筆 `cum=10, price=100_000`、第二筆 `cum=10, price=99_000`、第三筆 `cum=9`
     (倒退情境);斷言 `last_price == 100.0` **且 `totals.ticks == 1`**(後者確保 drop
     真的發生,而非價格碰巧相同)]
  3. 未分類 tick 更新 last_price(已併入 test_snapshot_contracts_detail 的 99.5 期望)。
  4. `reset()` 後 contracts 空(既有測試已鎖)— 不另補。
  5. backfill 路徑:ingest_backfill 兩筆(precise_time 亂序輸入)→ last_price =
     時序較後那筆(SC-4)。

## 既有測試標記

- 該紅(🔴):`test_snapshot_contracts_detail`、`test_replay_golden_snapshot_locked`
  (皆為精確相等斷言,加欄即紅;契約「只加不改」已預告,屬事前標為該變)。
- 不該紅:其餘全部(test_contracts_invariants / reset / test_app.py 按鍵取值;
  前端測試不在本輪跑動範圍但 SC-5 要求確認)。

## Commit 計畫(三類分離)

[amendment 2026-08-05: review P1-4 — 標記統一,消除「同一份實作標兩類」]

- 🔴 行為改動一包:該紅測試先改紅(test_snapshot_contracts_detail 期望 + golden regen +
  ticks.jsonl 獨立斷言新測試)→ 實作(aggregate.py 三處)→ 綠。
- 🟢 防回歸新測試(stale-drop 不更新 / 時序最後 / backfill 亂序)— 🔴 之後補,
  commit 邊界全綠。
  (無 🔵)。順序:🔴 → 🟢。

self_review_head: 486e09e13bdb94b5be7a510d11406a3b68d4b930
