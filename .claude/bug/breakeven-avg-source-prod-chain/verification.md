# fix/breakeven-avg-source-prod-chain — verification

主 tree 直做(HITL 預設);branch 自 master `51b93006` 開。working tree 另有他 session 未提交的
`.claude/skills/ops-discipline/SKILL.md`(+7)與 repo root 六份 `pr-11N-review*.md`,本分支不碰、不 commit。

## 0. 入口證據(2026-08-27 11:2x,prod 8721 = `51b93006`,08:14 起)

```
curl -s localhost:8721/api/capital/positions
2484 cash   qty=1 avg=78.42  avg_source=None today_qty=1
3026 margin qty=1 avg=646.17 avg_source=None today_qty=1
6715 margin qty=1 avg=364.59 avg_source=None today_qty=0
```
`grep -rn apply_profit_rows copycat/` → 只有定義,零 caller;`client.py:560` 就地 `p.avg_price = r.avg_price` 無 `avg_source`。

## 1. Phase 1 feedback loop(紅先行,commit 8228aea3)

兩條指令、各一紅、秒級、確定性:

```
.venv\Scripts\python -m pytest -q tests/capital/test_client.py -k avg_source_broker
→ FAILED test_balance_chain_marks_avg_source_broker
  where None = Position(... avg_price=150.55, kind='margin', ..., avg_source=None, today_qty=0).avg_source
  1 failed, 103 deselected in 0.23s

cd frontend && npx vitest run src/lib/ladder-position.test.ts
→ × payload 兩欄同缺(avg_source 也 undefined,舊後端)→ 與 null 同口徑,不印 NaN
  AssertionError: expected false to be true   (Number.isFinite(econ.pnl))
  1 failed | 37 passed (38)
```
- 後端紅在 user 症狀本體:真鏈(balance → profit → OI → finalize)落地的列 `avg_source=None` = wire 上 null。
- 前端紅在 F-02 症狀:`avgSource` undefined → `cost` 未賦值 → pnl NaN。

## 2. Phase 2 最小重現

- 後端:一列 balance + 一列同 kind 的 profit + 空 OI;每個元素 load-bearing(拿掉 profit 列 → avg_price 也 None,
  紅在別的地方;拿掉 OI `##` → 鏈不 finalize,positions 空)。
- 前端:單次 `positionEcon(2, 100, 102_000, 1.8, "cash", {avgSource: undefined, todayQty: undefined})`。

## 3. Phase 3 假說(單一,loop 在 seam 上直接證實,未另列 3–5 條)

| # | 假說 | 預測 | 結果 |
|---|---|---|---|
| A | `_on_profit_complete` 只寫 `avg_price` 不寫 `avg_source`;`apply_profit_rows` 零 caller | 補一行 `p.avg_source = "broker"` 真鏈測試轉綠 | 成立 |
| B | `positionEcon` switch 無 default,undefined 落空 | 先歸一成 null 再進 exhaustive switch(**無 default**;`0375f3aa` 曾用 default,`5ff89742` 拿掉改 `?? null`,pr-119 F-02 後最終為白名單歸一)→ 與 null 同值 | 成立 |

## 4. 修法與 commit

| commit | 類 | 內容 |
|---|---|---|
| `8228aea3` | test | 兩條紅先行 |
| `0375f3aa` | 🔴 | `client.py::_on_profit_complete` 補 `p.avg_source = "broker"`;`ladder-position.ts` switch `default` 併 null 分支(**後被 `5ff89742` 拿掉**,出貨形態無 default) |
| `b27ab8a9` | 🔵 | 刪零 caller 的 `store.apply_profit_rows`(+ 未用 `ProfitRow` import);store 四條測試:兩條刪(語意由 test_client 真鏈測試覆蓋)、兩條 setup 改吃真鏈產物、carry 測試補「同種類沿用 / 異種類不沿用」斷言 |
| `f3fca9cc` | chore | CLAUDE.md §4 產生點改正(F-03)、next-time 留尾 + #116 F-01 錯位順修、spec.md |
| `7b7c284f` | test | round 1 收修:真鏈 kind=None 整列略過不蓋 broker 均價(Spec P2,mutation 紅);store carry 測試去重折行 |
| `5ff89742` | 🔵 | round 1 收修:`positionEcon` 先歸一 undefined→null 再進 exhaustive switch(拿掉 default);`positions()` docstring 回補不可就地改的不變式 |
| `c28541f9` | chore | round 1 收修:CLAUDE.md §4 讀者改為 wire 映射點、next-time 期貨列 avg_source 語意缺口、spec 措辭 |

pr-119 F-07 校正(2026-08-27 晚):上表原只列到 `f3fca9cc` 且 §3 B / `0375f3aa` 列寫「default」與出貨 code 相反;三列收修補齊。
最終形態再經 `fix/breakeven-review-followups`(pr-119 F-02)改為白名單歸一 `raw === "broker" || raw === "fill" ? raw : null`。

## 5. 反向驗證(PASS)

```
git stash push copycat/capital/client.py frontend/src/lib/ladder-position.ts
  → pytest: 1 failed(紅回來) / vitest: 1 failed | 37 passed(紅回來)
git stash pop
  → pytest: 1 passed / vitest: 38 passed(綠回去)
```

## 9. Blast radius

- `_on_profit_complete` caller:只有 `client.py:224` collector `on_complete`。
- `avg_source` 寫入點(修後):`client.py::_on_profit_complete`(broker)、`store.py::_apply_fill_locked`(fill / 沿用)、
  `store.py::set_positions`(沿用 prev)。
- `positionEcon` caller:`PriceLadder.tsx:146`、`position-summary.ts:147` —— 合法三值行為不變,只有 undefined 從 NaN 變 null 口徑。
- 期貨列(`_on_oi_complete` / `merge_fut_positions`)不經損益回填,avg_source 本來就 None,前端對 fut 走 null 口徑,不變。

## 6. 真實環境

- 入口證據(§0)本身就是真環境紅燈:prod `51b93006` 三檔 `avg_source=None`。
- 本鏈需群益 COM 登入;盤中不起第二台登同一帳號(ops-discipline:capital 面不走側車),**真環境綠燈 = prod 收盤後重啟
  (含本 PR)後**:
  1. `curl -s localhost:8721/api/capital/positions` 每列 `avg_source == "broker"`(期貨列 null 是既知語意,見 next-time)。
  2. 次一交易日首筆成交:打平線在快照落地(1–2 s)時**不跳格**;損益與群益 APP 對 `today_qty=0` 的部位一致。
  3. 前端走 dev 5173 不用重 build;若切 preview 4173 要 `npm run build`(dist 停在 08-25)。
- 未改功能抽查(自動化代):`tests/capital` 402 全綠含 `_apply_fill_locked` 樂觀套用 / `today_qty` / close 映射;
  `position-summary.test.ts` + `PriceLadder.test.tsx` 153 全綠。

## 7. 自動化 gate(最終 HEAD c28541f9,主 tree)

| gate | 指令 | 結果 | exit |
|---|---|---|---|
| pytest | `.venv\Scripts\python -m pytest -q` | 3106 passed, 1 warning in 191.85s | 0 |
| ruff | `.venv\Scripts\python -m ruff check copycat tests` | All checks passed! | 0 |
| pyright | `.venv\Scripts\python -m pyright` | 0 errors, 0 warnings, 0 informations | 0 |
| validate | `.venv\Scripts\python -m copycat validate` | 42/42 PASS | 0 |
| vitest | `npm test`(frontend) | 151 files / 2829 passed | 0 |
| tsc | `npx tsc -b` | 無輸出 | 0 |
| eslint | `npx eslint src` | 無輸出 | 0 |
| react-doctor | `npx react-doctor@latest --scope changed --no-telemetry` | ✔ Scanned 2 files in 113ms ✔ No issues found! | 0 |

exhaustiveness 實證(§7a S4):`types.ts` 暫加 `"probe"` → `tsc -b` → `ladder-position.ts(113,28)/(121,12): error TS2454: Variable 'cost' is used before being assigned.` → 還原。
mutation(§7a P1):`client.py` 暫改 kind=None 也回填 → `test_profit_row_unknown_kind_skipped_keeps_previous_broker_avg` 紅 → 還原(grep MUTANT 0)。

## 7a. two-axis review round 1(`code-review-round-1.json`)

Standards 6 條(P2 hard:CLAUDE.md 讀者指錯 / P2 judgement:不變式 docstring 消失 / 4 P3)全接受;
Spec 4 條:P2 kind=None 真鏈零覆蓋 → 補測試(mutation 紅)、P3 next-time 空行、P2 期貨列 avg_source 後果反駁但語意缺口入
next-time、P3 exhaustiveness 同 Standards。收修 commit `7b7c284f`(test)/ `5ff89742`(🔵)/ `c28541f9`(chore)。

## 8. 需 user 過目 / 拍板

- prod 收盤後重啟(§6 判準 1–2)。
- 無:本輪零 UI 變更(前端只動算式的缺欄防禦,合法輸入結果逐 bit 不變)。

## 10. 留尾(已入 `docs/next-time.md` 2026-08-27 節)

- 流程教訓:blast radius grep「鄰欄就地寫入點」;期貨列 `avg_source` 語意缺口;F-05 fill_date;三份 pr-review 報告未 commit。
