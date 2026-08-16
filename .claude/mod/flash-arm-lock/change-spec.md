# change-spec — mod/flash-arm-lock(R5 閃電下單「鎖定武裝」)

來源:`docs/superpowers/specs/2026-08-15-user-feedback-batch2-rounds.md` §2 R5(user 撰寫 → /auto 預核准;
D1 default a:仍受 WS 斷線 / 連 3 敗 / Esc / 手動解除 / reload 解除;D2 default 不持久化)。
現況:`current-state.md`。規模:**L**(≥ 5 檔 + 安全敏感面:武裝是唯一繞過確認彈窗的路徑)。
分流判定:已成形方案(spec 指名 hook 上提 / `locked` 旗標 / 落點檔案 / UI 形式)+ 有可追問決策點
→ grilling 姿態,逐題 `[auto-default]`;無方向性抉擇(SC 集合 / out of scope / 對外契約皆不受
候選互換影響)→ 不停等。

## 1. 成功條件(SC;UI 條目為畫面可指認表述)

| # | 成功條件 | 驗證方式 |
|---|---|---|
| SC-1 | 武裝列出現「鎖定」鈕(武裝鈕右側、商品別控制項左側,三座梯皆有);未鎖定 = 灰框灰字「鎖定」;按下 → 梯立即武裝(武裝鈕轉「解除」青底)且鎖定鈕轉「鎖定中」桃紅底(`bg-accent`)、`aria-pressed=true`。**288px 右欄下三控制項同列不換行、武裝鈕「解除」文字完整、武裝列高度不變(價格列 y 不位移)**(`[amendment 2026-08-17: review R10]`) | vitest:PriceLadder / StkfutLadder / FuturesLadder 各一案(getByRole button name 鎖定 → click → 解除 + 鎖定中);截圖 `evidence/SC-1_stock_288.png`(現股梯,交易別 select 同列)+ 加鈕前後武裝列高度對照 |
| SC-2 | 鎖定後**換自選股**(PriceLadder `code` 變)→ 仍武裝可點價(1 次 API call) | vitest PriceLadder:鎖定 → rerender 新 code → 鈕仍「解除」→ 點價 1 call |
| SC-3 | 鎖定後**換梯**:現股 → 選個股期合約(PriceLadder → StkfutLadder)、個股 → 期貨主 tab(→ FuturesLadder)、期貨 → 個股,新梯掛載即武裝 | vitest RightRail:鎖定 → rerender ctx 換 contract / kind → 新梯鈕「解除」+「鎖定中」;截圖 `evidence/SC-3_*.png` |
| SC-4 | 鎖定後**切右欄 tab**(閃電 → 委託 → 閃電)→ 仍武裝 | vitest RightRail |
| SC-5 | 鎖定後**閒置 6 分鐘**仍武裝(未鎖定 5 分自動解除不變) | vitest useFlashArm(fake timers advance 6 min) |
| SC-6 | 鎖定中 **capital WS 轉 closed** → 解除且鎖定清除(鈕回「武裝」/「鎖定」);**即使當下停在無梯頁(TXO / 指數)**也生效 | vitest RightRail:鎖定 → ctx none → setCapitalWsStatus("closed") → ctx stock → 鈕「武裝」 |
| SC-7 | 鎖定中 **Esc** → 解除且鎖定清除;停在無梯頁按 Esc 同樣清除 | vitest RightRail(keyDown window Escape) |
| SC-8 | 鎖定中 **連 3 次送單失敗** → 解除且鎖定清除 | vitest flash-arm reducer + PriceLadder(mock 3 次 reject) |
| SC-9 | 鎖定中按武裝鈕「解除」→ 解除且鎖定清除;按「鎖定中」→ 解鎖但**保持武裝**(回到一般武裝語意,閒置計時重新起算) | vitest flash-arm reducer + LadderView 互動 |
| SC-10 | reload → 未武裝未鎖定(state 純 in-memory,不寫任何持久層、不放 module scope) | vitest 行為斷言(`[amendment 2026-08-17: review R11]`):RightRail 鎖定 → `unmount()` → 重新 render → 鈕「武裝」+「鎖定」;useFlashArm.test:兩個獨立 render 的 hook 實例互不共享 state;真實環境:鎖定 → F5 → 鈕「武裝」 |
| SC-11 | 未鎖定時三梯行為與現在逐條相同(白名單 §3) | 既有測試全綠(不改 assertion,型別形狀例外見 §5) |
| SC-12 | (a) **未武裝**時期貨梯 `resolved_contract` 失解析 / 個股期 blocked 契約:鎖定鈕與武裝鈕同 disabled;(b) **鎖定中**切到 blocked 個股期契約:兩鈕**仍可按**(解除 / 解鎖恆可用),點價仍被 priceLocked 擋;期貨合約失解析仍 disarm(清鎖定)(`[amendment 2026-08-17: review R2]`) | vitest FuturesLadder(state null → 兩鈕 disabled)、StkfutLadder(ETF unit 未武裝 → 兩鈕 disabled;鎖定後 rerender 成 ETF 契約 → 「解除」「鎖定中」皆非 disabled、點價零請求) |
| SC-13 | capital WS 非 `open`(connecting / closed)時鎖定鈕 disabled(title「連線未就緒,無法鎖定」);鎖定中若 WS 已是 closed(含鎖定瞬間即 closed)→ 立即解除並清鎖定(level 觸發,非只邊沿)(`[amendment 2026-08-17: review R1]`) | vitest:PriceLadder(store connecting → 鎖定鈕 disabled;open → 可按);useFlashArm.test(closed 下 dispatch lock → state 回 armed:false locked:false) |

**驗證窗口**:全部可離線驗(vitest + vite dev 對 8721 或 fake server);真實環境以
`CAPITAL_ORDER_ENABLED=false`(或後端未登入)確保點價被總開關擋,只驗武裝態機 + UI,不真送單。

## 2. 設計(diff 級)

### 2.1 狀態機 `lib/flash-arm.ts`(🟢)
- `ArmState { armed: boolean; locked: boolean; failStreak: number }`;`initialArm()` 加 `locked:false`。
- 事件新增 `lock` / `unlock` / `left_view`;`reduceArm`:
  - `toggle`:`s.armed ? {armed:false, locked:false, failStreak:0} : {armed:true, locked:false, failStreak:0}`
  - `lock`:`{armed:true, locked:true, failStreak:0}`(一鍵 = 武裝 + 鎖定)
  - `unlock`:`{...s, locked:false}`(armed 不動)
  - `disarm` / `conn_lost`:`{...s, armed:false, locked:false}`
  - `symbol_changed` / `idle_timeout`:`s.locked ? s : {...s, armed:false}`
  - `left_view`(ladder 卸載):`s.locked ? s : initialArm()`(等價於現況 unmount 消滅 state)
  - `send_fail` 第 3 次:`{armed:false, locked:false, failStreak:0}`;`send_ok` 不變
- `[auto-default: lock 事件 failStreak 歸零(同 toggle 武裝) | reason: 鎖定是一次新的武裝意圖,沿 toggle 語意]`
- `[auto-default: unlock 保持武裝、不解除 | reason: 解鎖只是收回「免解除」特權;要解除有 解除鈕 / Esc,兩鈕語意各自單一]`

### 2.2 新 hook `hooks/useFlashArm.ts`(🔵 上提 + 🟢)
```ts
export interface FlashArmControl { state: ArmState; dispatch: (e: ArmEvent) => void; touch: () => void; wsStatus: WsStatus }
export function useFlashArm(active = true): FlashArmControl
```
- 內含:`useReducer(reduceArm)`、閒置計時 ref(`touch()` = clearTimeout + setTimeout(idle_timeout, ARM_IDLE_MS))、
  Esc window listener(`active && state.armed` 才掛,行為同三梯現況)、conn_lost effect
  (`active && useCapitalWsStatus()==="closed"`)、unmount 清 timer。
- `active=false`(ladder 收到外部 armCtl 時的本地備援)→ 不掛 Esc / conn_lost 監聽、`touch` 不排計時;reducer 仍建但閒置。
- **回傳契約(`[amendment 2026-08-17: review R4]`)**:`dispatch` **就是** useReducer 原始 dispatch(恆定 identity,不包裝、不因 active 換函式);`touch` 以 `useCallback([])` + timer ref 實作,identity 恆定;`state` 為當前 ArmState。回歸測試:武裝後以新 last/book props rerender 兩次仍為「解除」態。
- **conn_lost level 觸發(`[amendment 2026-08-17: review R1]`)**:effect deps `[wsStatus, state.locked]`(active 時)—— 鎖定旗標一升起就重評;WS 為 `closed` 即 dispatch conn_lost。未鎖定的既有邊沿語意不變(deps 含 wsStatus 即涵蓋)。另回傳 `wsStatus`(供鎖定鈕 disabled 判定)。
- `[auto-default: 注入方式 = props `armCtl?: FlashArmControl` + 無 props 時本地 useFlashArm 備援(同 qtyState/onQtyState 先例) | reason: 三梯既有測試皆裸 render,備援讓它們零改動;Context 需在每個測試包 Provider 或另設 default,反而擴散]`
- `[auto-default: hook 落在 RightRail(非 App) | reason: RightRail 常駐全部 tab、已持有 tradeKind/qty 等「不隨 tab 重置」state;App 不碰下單面]`

### 2.3 三座梯(🔵 接 hook,行為零變;🟢 加鎖定鈕 + left_view)
共同:
- Props 加 `armCtl?: FlashArmControl`;`const local = useFlashArm(armCtl === undefined); const arm = armCtl ?? local;`
  → 讀 `arm.state.armed`、`arm.dispatch(...)`、`touchIdle = arm.touch`。
- **刪除**各自的 `useReducer` / `idleTimer` ref + `touchIdle` / Esc effect / conn_lost effect(移入 hook);
  unmount effect 保留 `aliveRef` + `hintTimer` 清理。
- **保留** symbol_changed effect(PriceLadder 依 `code`、Stkfut 依 `instrumentKey`、Futures 依 `product`)
  與 Futures `contract===null → disarm`。
- **新增** 卸載 effect:`useEffect(() => () => dispatch({type:"left_view"}), [dispatch])`(`dispatch` = 原始 useReducer dispatch,identity 恆定 → cleanup 只在真卸載觸發;StrictMode 初掛 cleanup 於未武裝態為 no-op)。
- **arm 事件 dispatch 移出 `aliveRef` 守門(`[amendment 2026-08-17: review R3]`)**:送單 then/catch 內 `dispatch(send_ok/send_fail)` 無條件執行(卸載後 dispatch 到父層 reducer 合法),只保留 `showHint` 在守門內 → 鎖定中「送出後切走、回應才到的失敗」仍計入 failStreak。測試:鎖定 → 點價 pending → 切 rail tab 卸載 → reject → 重複到第 3 次 → 解除且清鎖定。
- 鎖定鈕 `disabled = (armDisabled && !locked) || wsStatus !== "open"`;武裝鈕 `disabled = armDisabled && !armed`(`[amendment 2026-08-17: review R1/R2]`:disabled 只擋**進入**方向,已武裝 / 已鎖定時解除、解鎖恆可按)。
- 鎖定鈕:`locked={arm.state.locked}`、`onToggleLock={() => { arm.touch(); arm.dispatch({type: arm.state.locked ? "unlock" : "lock"}); }}`。
- PriceLadder / StkfutLadder 經 LadderView 新 props;FuturesLadder 自帶 JSX 同款加一顆(disabled 同 `contract===null`)。

### 2.4 `LadderView.tsx`(🟢)
- Props 加 `locked?: boolean`(預設 false)、`onToggleLock?: () => void`、`lockDisabled?: boolean`、`lockTitle?: string`;**`onToggleLock` 未給時不渲染鎖定鈕**(既有 LadderView.test 兩處裸 render 零改動;`[amendment 2026-08-17: review R5]`)。武裝鈕 `disabled={armDisabled && !armed}`(R2)。
- 武裝列第一行:`[武裝/解除 flex-1] [鎖定 / 鎖定中 shrink-0] {armControls}`(R10:鎖定鈕 `shrink-0` + 不換行,武裝鈕 `min-w-0`,select 不變;加鈕不改列高)。鎖定鈕:`aria-pressed={locked}`、
  文字 `locked ? "鎖定中" : "鎖定"`、class:未鎖 `border-line text-ink-dim hover:border-accent hover:text-ink`;
  鎖定中 `border-accent bg-accent text-bg font-bold`;`title="鎖定:換標的 / 換梯 / 閒置不解除;斷線 / 連 3 敗 / Esc / 解除仍會解除"`。
- `[auto-default: 視覺案 A(兩顆獨立鈕:解除=青底 + 鎖定中=桃紅底並列)而非案 B(武裝鈕自身變「鎖定中·解除」單顆) | reason: 兩個 state 兩顆鈕各自可讀、aria-pressed 各自對應,誤觸半徑最小;accent 為既有 token 且與 loss 青色一眼可辨,不新增色]`

### 2.5 `RightRail.tsx`(🔵/🟢)
- `const armCtl = useFlashArm();`(active)→ 三分支各傳 `armCtl={armCtl}`。
- 檔頭 D-13 註解改寫:「條件 render 仍是未鎖定時『離開畫面即解除』的實現手段之一,但 arm state 已上提到本元件;
  離開畫面的解除由 ladder 卸載 dispatch `left_view` 完成,鎖定時保留」。**條件 render 不改成 hidden**(仍不改)。

### 2.6 不動
- 後端(safety.py / models.py source="flash");交易別 select、當沖 checkbox、QTY_PRESETS、無券鎖買側、
  CapitalConfirmDialog Esc stopPropagation(next-time:190 語意)。

## 3. 不能破壞的既有行為白名單(reviewer / 自評 finder 對照本節)
- W-1 未鎖定:換標的 / 換合約 / 換商品 → 解除(PriceLadder.test:353、StkfutLadder.test:257/266、FuturesLadder.test:234)。
- W-2 未鎖定:切右欄 tab / 切主 tab / 現貨→合約 → 回到「武裝」(RightRail.test:197/210/371)。
- W-3 Esc / conn_lost / idle 5 分 / 連 3 敗 → 解除(PriceLadder.test:362/370/380/437、FuturesLadder.test:243/255/267、StkfutLadder.test:243)。
- W-4 未武裝點價零請求 + hint 3s;武裝點價 1 call + payload(source="flash"、trade_kind / day_trade)不變。
- W-5 個股期 blocked 契約:武裝鈕 disabled + BLOCKED_TEXT + 點價零請求(StkfutLadder.test:424/456);期貨 resolved_contract null:disabled + 「合約未解析」(FuturesLadder.test:198)。
- W-6 平倉失敗不動武裝(FuturesLadder.test:623);確認窗開著 Esc 不解武裝(next-time:190)。
- W-7 tradeKind / qty 不隨 tab 重置(RightRail.test:225/233/402/414/421)、置中請求語意(RightRail.test:244-282/450/459)。
- W-8 flash-arm 六案語意(預設未武裝 / toggle / 三事件解除 / 連 3 敗 / disarm 冪等 / 5 分)不變。

## 4. Edge cases
- E-1 鎖定中停在 TXO / 指數頁(無 ladder)時 WS 斷線 / Esc → hook 在 RightRail 層仍收到 → 回到個股頁是未武裝(SC-6/7)。
- E-2 鎖定中換到 blocked 個股期契約:armed 保留但 `priceLocked` 擋點價、兩鈕 disabled;換回可交易合約 → 仍武裝可點(不額外解除;安全閘在 priceLocked + 後端 PRODUCT_NOT_ALLOWED)。
- E-3 鎖定中切到期貨頁而 `state.resolved_contract` 尚未解析 → `contract===null` effect disarm(清鎖定):安全優先,合約一解析要重新武裝。
- E-4 StrictMode 雙掛載:初掛 cleanup 發 `left_view` 於 `{armed:false}` → 回 initialArm(),無可觀察差異。
- E-5 鎖定 → 解鎖(仍武裝)→ 閒置 5 分 → 解除(回一般語意)。
- E-6 未鎖定、武裝、failStreak=2、切 tab 再回 → failStreak 歸零(left_view 重置,等價舊 unmount)。
- E-7 **鎖定態 failStreak 跨梯累積,刻意不歸零**(安全方向;`[amendment 2026-08-17: review R9]`):鎖定 → 梯 A 失敗 2 次 → 換梯 → 梯 B 失敗 1 次 → 解除且清鎖定(測試鎖住,實作不得順手歸零)。
- E-8 鎖定中換標的 / 換梯的掛載瞬間即武裝態,點價區與前一梯座標重疊、量單位可能張↔口(`[amendment 2026-08-17: review R8]`):`[auto-default: 接受風險 + 收尾回報明講,不加掛載後短暫禁送窗 | reason: user spec 的核心訴求就是換標的 / 換梯不必重按;禁送窗需新 SC 與新狀態,屬方向性追加,留 next-time 供 user 拍板]`。

## 5. 既有測試標記
- **不該紅**:§3 白名單所列全部 + RightRail 其餘案例 + LadderView 相關快照式斷言(無 snapshot 檔)。
- **該變(型別形狀,非行為;`[amendment 2026-08-17: review R6]` 行號重核)**:`lib/flash-arm.test.ts` `:9`(字面值)、`:10`(`toEqual` 加 `locked:false`,runtime 斷言)、`:16`、`:23`、`:37`、`:39` 共 6 處 `ArmState` 字面值補 `locked:false`(tsc strict 必要;語意不變)。`LadderView.test.tsx:24-31 / :75-82` **不該紅**(新 props 皆 optional,R5)。
  `[auto-default: 接受這四處字面值更新而非把 locked 設成 optional | reason: optional 旗標會讓「locked===undefined」成為第三態,狀態機可讀性下降;user 白名單意圖是六案語意不變,不是字面不動]`
- **新增測試**:
  - `lib/flash-arm.test.ts`:lock 武裝+鎖定;locked 下 symbol_changed / idle_timeout / left_view no-op;locked 下 disarm / conn_lost / toggle / send_fail×3 清兩旗;unlock 保持 armed;left_view 未鎖定重置。
  - `hooks/useFlashArm.test.tsx`:active:touch 後 5 分 idle_timeout / Esc / conn_lost;inactive:三者皆不觸發;closed 下 lock → 立即清(SC-13);兩個獨立實例不共享 state(SC-10);dispatch / touch identity 跨 rerender 恆定(R4)。
  - `PriceLadder.test.tsx`:SC-1 鎖定鈕(需先 `setCapitalWsStatus("open")`);SC-2 鎖定後換 code 仍武裝可點價;SC-8 鎖定中連 3 敗清鎖定;SC-13 store connecting → 鎖定鈕 disabled;武裝後 rerender 兩次仍「解除」(R4)。
  - `StkfutLadder.test.tsx`:SC-1;鎖定後換合約仍武裝;**補齊 Esc / idle / 連 3 敗三案(🟢 測試,spec 明列)**;blocked 契約兩鈕 disabled。
  - `FuturesLadder.test.tsx`:SC-1;鎖定後換 product 仍武裝;state null 兩鈕 disabled。
  - `RightRail.test.tsx`:SC-3(現股→合約 / 個股→期貨→個股)、SC-4、SC-6、SC-7、SC-10(unmount + 重 render 歸零)、E-7(跨梯 failStreak 累積)、R3(卸載後回應的失敗仍計數)、SC-12(b)(鎖定中切 blocked 契約兩鈕可按);舊三案不動。

## 6. 三類 commit 順序
1. 🔵 `refactor(frontend): 閃電武裝狀態上提為 useFlashArm 共用 hook(RightRail 持有,三梯 props 接)`
   — 行為零變:三梯測試 + RightRail 測試全綠;此時 left_view 等價 unmount。
   `[auto-default: 🔵 階段即引入 left_view 事件(無 locked 時恆等於 reset) | reason: 沒有它上提後 W-2 立刻破,無法做到「先重構後零變」]`
2. 🟢 `test: add failing test for SC-N [red]` → `feat: implement [green]`(lock/unlock/locked 分支 + 鎖定鈕 + RightRail 新語意測試 + Stkfut 三案補齊)。
3. 🔴 無(RightRail 舊三案語意在未鎖定時保留;鎖定語意以新案例表達,不改舊 assertion)。

## 7. 「鎖定下誤觸」風險節(spec 要求;reviewer 帶 security lens)
- R-1 鎖定放大了武裝的時間 × 空間範圍:任何時刻回到任何梯都是直送態。緩解:(a) 鎖定態畫面可指認(桃紅「鎖定中」+ 青底「解除」兩顆同列);(b) 全域 Esc / 斷線 / 連敗仍解除且清鎖定;(c) reload 歸零;(d) 後端總開關 / max_qty / max_amount 不變。
- R-2 換梯後量單位不同(張 ↔ 口):qty 各梯各自持有(RightRail R2-10 / A5)不共用,鎖定不改變 qty 語意;但 user 需知「鎖定中切到期貨梯 = 口數直送」。緩解:鎖定鈕 title 文案 + 收尾回報明列。
- R-3 鎖定中停在無梯頁(TXO)看不到武裝狀態:回到個股頁才看得到「鎖定中」。緩解:E-1 全域 Esc/斷線仍作用;可選(next-time):RightRail tablist 旁掛小型鎖定徽章。`[auto-default: 本輪不加全域徽章 | reason: spec 未列;先出貨核心語意,徽章需 UI 拍板]`
- R-4 鎖定中換到 blocked 合約 → armed 保留(E-2):點價由 priceLocked + 後端擋;不會送出。
- R-5 conn_lost 判定只看 capital WS `closed`;`connecting` 不解除(現況同);鎖定鈕在非 `open` 時 disabled、鎖定中遇 closed level 觸發清除(SC-13)。
- R-6 **殘留風險(`[amendment 2026-08-17: review R7]`)**:CapitalConfirmDialog 開著時 Esc 被窗 stopPropagation(next-time:190 既有語意)→ 鎖定中 + 部位 tab 平倉確認窗開著時 Esc 不解除鎖定;要解除需先關窗再 Esc,或按解除鈕。本輪不動 dialog(改 capture 監聽屬 🔴,另案);收尾回報告知 user。
- R-7 掛載瞬間誤觸窗見 E-8(接受 + 回報)。
- R-8(`[amendment 2026-08-17: code review S5]`)主圖五檔 `stock-price-click` 會把右欄切回閃電 tab 並置中該價:鎖定態下眼前直接是「已武裝且置中」的梯(舊語意是剛掛載的未武裝梯)。接受 + 回報;禁送窗同 E-8 留 next-time。
- R-9(`[amendment 2026-08-17: code review S2]`)鎖定態換自選股 / 換期貨商品時,共用的張數 / 口數若沿用會失去「重按武裝」檢查點(20 元標的 50 張 → 1000 元標的 50 張,名目 ×50 零訊號)→ `[auto-default: 鎖定態 instrument 變更該梯 qty 回 initialQtyState();未鎖定不動(W-7)| reason: 往小的方向靜默重置無風險;tradeKind 不動(不適用時券商拒單)]`。收尾回報明講。
- R-10(`[amendment 2026-08-17: code review S4]`)真實環境切期貨頁若 `resolved_contract` 尚未到齊(冷啟動 / stream 重連)→ E-3 disarm 清鎖定,需重按;方向安全,回報告知。
- R-3 補述(code review p2):鎖定態在右欄「委託 / 部位」tab 同樣零指示器(不只 TXO / 指數頁)。

## 8. Out of scope
- 後端 source="flash-locked" 稽核(next-time)、鎖定態持久化、全域鎖定徽章(R-3)、CapitalConfirmDialog Esc 語意、
  三梯武裝鈕 JSX 三份合一(FuturesLadder 仍自帶;可 /refactor)、掛載後短暫禁送窗(E-8)、確認窗 Esc capture(R-6)、未鎖定時「WS closed 期間仍可武裝」的既有邊沿語意(R1 衍生,next-time)。

## 9. 執行約束(沿前輪慣例)
- 前端規範讀 `frontend-conventions` / `frontend-testing` skill;測試用 `vi.spyOn`、無 jest-dom;
  wsStatus 注入用 `setCapitalWsStatus`;fake timers 用 `vi.useFakeTimers()`。
- 實作 dispatch opus(L 級);main session 不直接改源檔;commit tag 依 core-flow §4。
- react-doctor 只有新增 finding 算 FAIL。

## 10. Review round 1 處置(2026-08-17;JSON `change-spec-review-round-1.json`;無 P0 → 不加輪)
| id | sev | 處置 | resolution |
|---|---|---|---|
| R1 | P1 | accepted | SC-13 + §2.2 level 觸發 + 鎖定鈕非 open disabled;未鎖定既有邊沿語意不動(next-time) |
| R2 | P1 | accepted | SC-12 拆 (a)/(b);disabled 只擋進入方向 |
| R3 | P1 | accepted | §2.3 dispatch 移出 aliveRef 守門 + 測試 |
| R4 | P1 | accepted | §2.2 回傳契約 identity 恆定 + rerender 回歸測試 |
| R5 | P1 | accepted(a) | LadderView 新 props optional,未給不渲染 |
| R6 | P2 | accepted | §5 行號重核 6 處 |
| R7 | P2 | accepted | §7 R-6 殘留風險 + 收尾回報 |
| R8 | P2 | accepted(a) | E-8 接受風險 + 回報;禁送窗留 next-time |
| R9 | P2 | accepted | E-7 + 測試 |
| R10 | P2 | accepted | SC-1 288px 條件 + shrink-0 |
| R11 | P2 | accepted | SC-10 行為斷言 |

## self_review_head
fe2c8e33(code review round 1:2 lens,P1×5 / P2×10 全處置;fix 波 5 commits)
