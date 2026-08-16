# current-state — mod/flash-arm-lock(R5 閃電下單「鎖定武裝」)

來源:`docs/superpowers/specs/2026-08-15-user-feedback-batch2-rounds.md` §2 R5(user 撰寫,/auto 預核准)。
分支基底 master `6a31af57`(2026-08-17 重 grep,行號以此為準;spec 內行號為 08-15 快照,已對齊)。
Worktree `.claude/worktrees/flash-arm-lock`,artifact 落主 tree `.claude/mod/flash-arm-lock/`。
Baseline:worktree `npx tsc -b` PASS + `vitest run` 1872 passed(01:16)。

## 1. 現況(武裝狀態機與三座梯)

### 狀態機 `frontend/src/lib/flash-arm.ts`(純函式,零 IO)
- `ArmState { armed, failStreak }`(:6-9);事件 `toggle | disarm | symbol_changed | conn_lost |
  idle_timeout | send_ok | send_fail`(:11-18);`reduceArm`(:24-41):toggle 翻轉且 failStreak 歸零;
  disarm/symbol_changed/conn_lost/idle_timeout → `armed=false`(failStreak 保留);send_fail 第 3 次
  (`FAIL_LIMIT=3`,:4)→ `{armed:false, failStreak:0}`;`ARM_IDLE_MS=5min`(:3)。
- 測試 `lib/flash-arm.test.ts` 6 案(預設未武裝 / toggle / 三事件解除 / 連 3 敗 / disarm 冪等 / 5 分)。

### 三梯**各自** `useReducer(reduceArm)`(非共用 hook)— caller map
| 面向 | PriceLadder.tsx | StkfutLadder.tsx | FuturesLadder.tsx |
|---|---|---|---|
| reducer | :168 | :87 | :62 |
| touchIdle(閒置計時,ref) | :210-216 | :137-143 | :130-136 |
| clickPrice 未武裝守門 | :222-225 | (:145 起) | :145-149 |
| send_ok/send_fail(mutateAsync 自接) | :256-270 | :182-196 | :174-188 |
| 換標的 symbol_changed | :280-282 依 `code` | :206-208 依 `instrumentKey` | :232-234 依 `product` |
| 合約失解析 → disarm | — | — | :237-239(`contract===null`) |
| conn_lost(`useCapitalWsStatus()==="closed"`) | :285-287 | :211-213 | :241-244 |
| Esc(window keydown,只在 armed 期間掛) | :290-297 | :216-223 | :246-254 |
| unmount 清 timer + aliveRef | :300-307 | :226-233 | :256-263 |
| 武裝鈕 | LadderView `armed/onToggleArm/armDisabled/armTitle`(props :77-83,JSX :184-201) | 同左 + `armDisabled={blocked}`(:248-251) | 自帶第三份 JSX :304-325(`disabled={contract===null}`) |
| 商品別控制項 | `armControls`= 交易別 select(:378-393) | 當沖 checkbox | 當沖 checkbox(:326-) |
- `useCapitalWsStatus`(hooks/useCapital.ts:79)= `useSyncExternalStore` 全域 store,任何層級可讀。
- **「離開畫面即解除」靠 unmount**:RightRail(components/rail/RightRail.tsx)閃電 tab 的 ladder
  一律**條件 render**(檔頭 D-13 註解 :17-25、:349),三分支 `flashContent()`(:133-185):
  個股+合約 → StkfutLadder / 個股 → PriceLadder / 期貨 → FuturesLadder / 其餘 EmptyFlash。
  切右欄 tab(:76-83 `selectTab`)或切主 tab(App.tsx:315 `<RightRail ctx={railCtx}/>`,ctx 依 tab
  :185-205)都會 unmount ladder → arm 消失。RightRail 本身**常駐全部 tab**(App.tsx:315),
  已持有 tradeKind / stockQty / futQty / stkfutQty(:69-77,R2-10「不隨 tab 重置」先例)。
- 後端 `copycat/capital/safety.py` 完全不感知武裝;`models.py:53 source="flash"` 只稽核 → 本輪後端不動。

### 既有測試(行為合約)
- flash-arm.test.ts ×6(全部「不該紅」;新增 lock/unlock/locked 下事件案例)。
- PriceLadder.test.tsx:290(武裝點價)/317(未武裝)/353(換 code 解除)/362(Esc)/370(conn_lost)/
  380(idle 5 分)/437(連 3 敗)— 全部不該紅。
- StkfutLadder.test.tsx:219/243/257/266 — 不該紅;**缺 Esc / idle / 連 3 敗三條**(spec:本輪補齊,🟢 測試)。
- FuturesLadder.test.tsx:136/183/198/234/243/255/267/623 — 不該紅。
- RightRail.test.tsx:197(個股武裝→切期貨→切回 → 回「武裝」)/210(切右欄 tab 再回 → 回「武裝」)/
  371(現貨→合約 → 未武裝)— **未鎖定時不該紅**;鎖定時是新語意(新增案例,不改舊 assertion)。
- next-time.md:190「確認窗開著時 Esc 不解除武裝」既有語意保留(窗內 stopPropagation,本輪不動)。

## 2. 現況 vs 目標

| 項目 | 現況 | 目標 |
|---|---|---|
| arm state 位置 | 三梯各自 useReducer(unmount 即消) | 單一共用 hook `useFlashArm` 在 RightRail 持有;三梯經 props 接(無 props 時退回本地,獨立使用 / 既有測試路徑不變) |
| 換標的 / 換合約 / 換商品 | 一律解除 | 未鎖定:解除(同現況);鎖定:no-op |
| 換梯(現股↔個股期↔期貨)/ 切右欄 tab / 切主 tab | unmount 消滅 = 解除 | 未鎖定:ladder 卸載時 dispatch `left_view` → 解除(等價現況);鎖定:保留 |
| 閒置 5 分 | 解除 | 未鎖定:解除;鎖定:no-op |
| WS 斷線 / 連 3 敗 / Esc / 手動解除 | 解除 | 一律解除 **且清 locked**;Esc 與 conn_lost 監聽移到共用 hook(RightRail 層)→ 鎖定時停在 TXO 頁(無 ladder)也收得到 |
| reload | 未武裝 | 未武裝未鎖定(in-memory,D2 不持久化) |
| 武裝列 UI | 單顆 武裝/解除 | 武裝鈕 + **鎖定鈕**並列(LadderView 一處 + FuturesLadder 自帶 JSX 一處);鎖定態畫面可指認 |
| 合約失解析(期貨) | disarm | disarm(仍清 locked;安全優先) |
| 個股期 blocked 契約 | armDisabled + 點價擋 | 不變(鎖定態換到 blocked 合約:armed 保留但 priceLocked 擋點價,鎖定鈕同樣 disabled) |
| 後端 | 不感知 | 不動(source 不擴 "flash-locked",寫 next-time) |

## 3. Caller / 影響面
- 直接 caller:PriceLadder / StkfutLadder / FuturesLadder(import flash-arm)、LadderView(武裝鈕 props)、
  RightRail(三梯掛載點,唯一 caller;App.tsx:315 唯一掛 RightRail)。
- 動態用法:grep `dispatchArm|reduceArm|initialArm|ARM_IDLE_MS` 只在上述檔;無字串型事件名散落。
- Backward compat:純前端 in-memory state,無 API / 資料格式 / localStorage 變更 → 無 migration。
- 分級:≥5 檔 + 安全敏感(繞過確認彈窗的唯一路徑)→ **L 級**;spec review 1 輪(+P0 限縮 1 輪),
  實作 dispatch opus。
