# Change spec — CapitalConfirmDialog 換原生 dialog

分流判定:**已成形方案**(來源 = user 拍板文件 `docs/research/2026-08-11-react-doctor-triage.md`
§一「中價值,單獨拍板」+ /auto 指令內文指名做法與樣板)→ 預核准,免 grilling 停等。

## 成功條件

- **SC-1 元件改以原生 `<dialog>` 呈現**:`getByRole("dialog")` 的元素 `tagName === "DIALOG"`;
  真瀏覽器走 `showModal()`(effect 內 feature-detect),jsdom fallback 設 `open` attribute。
  驗證:新測試「以原生 dialog 開啟」+ `npm test`。
- **SC-2 Esc = 取消**:Esc 觸發 `onCancel` **恰一次**,`onConfirm` 不可能被 Esc 觸發;
  原生 cancel/close 與 onKeyDown 雙路徑去重。驗證:新測試「Esc → onCancel 恰一次」+
  「Esc 後補發 close 事件仍恰一次」。
- **SC-3 初始 focus 落在「取消」鈕**:開窗後 `document.activeElement` = 取消鈕。
  驗證:新測試(jsdom focus 可測)+ 真瀏覽器層 user 過目。
  `[auto-default: 初始 focus 給取消鈕(非確認鈕) | reason: 真錢確認窗,Enter 直接送單
  太危險;取消是 fail-safe 預設,鍵盤流 = Tab 一下到確認 or Esc 離開]`
- **SC-4 背景 inert(不可點、不可 Tab 到)+ 關窗後復原**:`showModal()` 原生提供
  top-layer + inert。[amendment 2026-08-11: review R2 — 驗證升四元組] 真瀏覽器層驗:
  (a) 開窗後背景不可點 (b) 不可 Tab 到背景 (c) **關窗後背景恢復可點可捲**
  (d) **關窗後 focus 回到觸發鈕**(focus 歸還走 cleanup 還原,見拍板節)。
  jsdom 可測 (d)(新測試 9);(a)(b)(c) 真瀏覽器層(devtools 截圖或
  `browser_unavailable + user 過目` 降級;驗法 = 開確認窗後點背景「平倉」鈕應無反應)。
- **SC-8 視覺契約可回歸**:[amendment 2026-08-11: review R4] dialog 元素 classList 含
  `m-auto` / `backdrop:bg-bg/85` / `max-w-sm`(jsdom 斷言,新測試 8);真瀏覽器層補
  遮罩/置中/danger 紅底截圖對照(browser 不可用時降級 user 過目)。
- **SC-5 白名單全保留**(見下節)。驗證:既有 2 測試**不改動且綠** + 4 caller 檔 `git diff` 零改動。
- **SC-6 react-doctor 對照**:`npx react-doctor@latest --scope changed --no-telemetry`
  prefer-html-dialog(CapitalConfirmDialog.tsx:27)消失、無新增 finding。
- **SC-7 gates**:`npm test` 全綠(baseline 1710)+ `npx tsc -b` + `npx eslint src` 過。

## 不能破壞的既有行為白名單

1. **callback 契約**:props `{ title, rows, danger?, onConfirm, onCancel }` 介面**完全不變**;
   點「確認」→ `onConfirm` 恰一次、點「取消」→ `onCancel` 恰一次;確認點擊路徑不經任何
   guard(語意與現行逐 click 直呼一致)。
2. **caller 掛載契約**:4 個 caller(OrderPanel:283 / CapitalOrdersList:208 /
   CapitalPositionsList:110 / FuturesLadder:458)**零 diff**;條件掛載 = 開、unmount = 關;
   **unmount 不觸發任何 callback**(FuturesLadder 自動收窗行為不變)。
3. **視覺**:danger 標題列 `bg-loss` 紅底 +「正式」字樣、rows `<dl>` 版式、按鈕配色
   (danger 紅框 / 平常 accent 框)不變;遮罩改 `backdrop:bg-bg/85`(同色同透明度)。
4. **二次確認流程(專案 CLAUDe.md §7 三閘之一)不變**:送單仍必經此窗;Esc 只會取消,
   任何新路徑都不可能觸發 `onConfirm`。
5. 既有 2 支測試(callbacks / danger 樣式)**一字不改**,改後必須綠。

## 設計拍板(auto-default 集中記錄)

- `[auto-default: 維持條件掛載,不加 open prop、不改 caller | reason: (1) 白名單 1/2 要求
  caller 契約不變;(2) CapitalOrdersList 是每列 li 內掛一顆,persistent 掛載會變 N 顆常駐
  dialog(RTL 計數污染 + 無謂 DOM);(3) FuturesLadder 依 unmount 自動收窗;(4) next-time
  已記 OrderPanel premium gate 靜默卸載為獨立輪 Known Risk,本輪不碰掛載模式]`
- `[auto-default: dialog 元素不帶任何 display utility(不需要 open ? flex : hidden)|
  reason: 樣板「display 由 open prop 選」的本質是「author 層 display 不得蓋掉 UA 的
  dialog:not([open]){display:none}」(2026-07-31 空盒 bug)。本元件內容是普通 block 流
  (header + dl + 按鈕列),不像 WatchlistManagerDialog 需要 flex-col 容器 → 完全不寫
  display class,UA 規則天然生效,結構性免疫該 bug;且條件掛載下「關閉態」在 DOM 根本
  不存在。樣板三坑的另外兩坑照抄:onClose 拉回(見下)+ m-auto]`
- `[auto-default: onClose 拉回 = onClose → 去重後轉呼 onCancel | reason: 本元件無 open
  prop,「拉回 prop」語意映射為「原生關閉(任何路徑)→ 通知 caller 卸載」;閉合後元素
  因無 author display 蓋寫會被 UA 隱藏,不會出現樣板註解那種卡畫面形態]`
- `[auto-default: Esc 三層 = onKeyDown(jsdom 可測)+ onCancel preventDefault + onClose
  backstop,共用 closedRef 去重 | reason: 樣板用 onKeyDown(jsdom 無原生 Esc);真瀏覽器
  Esc 會同時走原生 cancel→close,不去重會對 caller 雙發 onCancel(現行 caller 全是冪等
  setState 不炸,但契約上「等同按一次取消鈕」必須恰一次);onCancel preventDefault 讓
  關閉單一由 React unmount 驅動]`
- `[auto-default: 初始 focus 用 effect 內 imperative focus(showModal 之後),不用 React
  autoFocus prop | reason: React autoFocus 是 commit 期 focus() 不落 DOM attribute,
  showModal 的 focusing steps 找不到 autofocus attribute 會把 focus 移到 dialog 本體 →
  時序上被蓋掉;effect 內 showModal() 後緊接 cancelBtn.focus() 是唯一確定序]`
- [amendment 2026-08-11: review R1(P0)] **effect 必帶 `if (!el.open)` 前置條件**(兩分支
  皆是):StrictMode(main.tsx 全站包)double-invoke 下第二次 `showModal()` 對已 open
  元素依標準拋 InvalidStateError → dev 白畫面;jsdom fallback 冪等測不到,只有真瀏覽器炸。
  樣板 WatchlistManagerDialog.tsx:54 同款防護。鎖法 = 新測試 6(StrictMode + prototype
  stub,對已 open 元素 throw)。
- [amendment 2026-08-11: review R2(P1)] **focus 歸還走 cleanup,不走 close()**:
  mount effect 內 `openerRef.current ??= document.activeElement`(`??=` 防 StrictMode
  第二輪把取消鈕誤記為 opener),cleanup 只做「opener 是 HTMLElement、`isConnected`、
  **且不是 document.body** → `opener.focus({ preventScroll: true })`」[amendment: R2-3 —
  FuturesLadder 平倉鈕在自動跟隨置中的階梯內,關窗瞬間 scroll-into-view 會拉走使用者
  盯的價位帶;開窗前無聚焦元素時 activeElement 是 body,對 body 還 focus 是雜訊],
  **不呼叫 el.close()**(cleanup close 會在確認路徑的卸載時序噴 close 事件,誤呼 onCancel
  風險 — 原「不做 cleanup」拍板修正為「cleanup 只還 focus」)。dialog removing steps
  不執行 close 演算法 → 原生不會歸還 focus,必須自己做。
- [amendment 2026-08-11: review R5(P2)] **settled 旗標補齊兩顆按鈕**:確認鈕 onClick =
  先直呼 `onConfirm()` 再 `closedRef.current = true`;取消鈕 = 先直呼 `onCancel()` 再設
  旗標(呼叫次數與順序不變,白名單 1「不經 guard」未破 — 旗標只擋**之後**的 Esc/close
  補發)。堵住「點確認送單後、caller 卸載前按 Esc → 又補發 onCancel,UI 誤導成已取消
  但單已送出」的真錢語意漏洞。closedRef 不重置 = 一次性,前提 = 4 個 caller 的
  onCancel/onConfirm 路徑皆卸載(現況成立,記 edge case)。
- [amendment 2026-08-11: review R6(P2)] **Escape 分支加 `e.stopPropagation()`**:
  FuturesLadder.tsx:240-247 武裝期間掛 window keydown(Escape → disarm),modal inert
  擋不了 window 層鍵盤監聽 → 不擋會「關窗 + 解除武裝」雙觸發。stopPropagation 不影響
  原生 cancel 預設行為(由 onCancel preventDefault 另擋)。
- [amendment 2026-08-11: review R7(P2)] class 清單補 `text-ink`(UA dialog 是
  `color: canvastext`,暗底防未來無色文字變黑字;樣板同款);**移除 `aria-modal="true"`**
  (原生 <dialog> + showModal 冗餘,fallback 非 modal 路徑留著反而是錯誤宣告;樣板無;
  全 repo 無測試依賴 aria-modal)。

## Diff 級章節(逐檔)

### 🔴 `frontend/src/components/capital/CapitalConfirmDialog.tsx`(行為改動:Esc/focus/inert 從無到有)

- 外層 `div role="dialog"` + 遮罩 div 兩層 → 單一 `<dialog ref aria-label={title}>`
  [amendment: R7 移除 aria-modal],class:`m-auto w-full max-w-sm border border-line
  bg-bg-deep p-0 text-ink backdrop:bg-bg/85`(m-auto 抵 preflight margin:0;p-0 顯式;
  text-ink 抵 UA canvastext;**無 display utility**)。
- 加 mount-only effect(元件掛載 = 開窗):`openerRef.current ??= document.activeElement`
  → feature-detect `showModal`(有 → **`if (!el.open)`** `showModal()`,jsdom →
  **`if (!el.open)`** `setAttribute("open","")`)[amendment: R1 防 StrictMode 重複開],
  接著 `cancelRef.current?.focus()`。cleanup = **只還 focus**(opener 是 HTMLElement 且
  `isConnected` → focus 回去),**不呼叫 close()**[amendment: R2]。
- 加 `closedRef` + `requestCancel()`(去重後呼 `onCancel`);掛
  `onKeyDown`(Escape → `e.stopPropagation()` [amendment: R6] + requestCancel)、
  `onCancel`(preventDefault + requestCancel)、`onClose`(requestCancel)。
- 兩顆按鈕 onClick 改為「先直呼原 callback,再設 `closedRef.current = true`」
  [amendment: R5](呼叫次數順序不變;旗標只擋之後的 Esc/close 補發)。
- **硬約束**[amendment: R8]:header / body / 按鈕列的 div 層級一律保留 —
  OrderPanel.test.tsx:188 與 CapitalOrdersList.test.tsx:273 以
  `getByText(標題).closest("div")` 斷言 bg-loss,header 那層 div 不可併進 dialog 元素。
- 加 `ref` 給取消鈕。

### 🔴 `frontend/src/components/capital/CapitalConfirmDialog.test.tsx`(先紅)

既有 2 支不動(該綠)。新增(1-6、8、9 現況必紅;7 是 lock test 走 mutation 驗證):
1. `原生 dialog 開啟`:`getByRole("dialog").tagName === "DIALOG"` 且有 `open` attribute。
2. `Esc → onCancel 恰一次且 onConfirm 零次`:`fireEvent.keyDown(dialog, { key: "Escape" })`。
3. `初始 focus 落在取消鈕`:`document.activeElement === 取消鈕`。
4. `原生 close 事件 → onCancel(backstop)`:`fireEvent(dialog, new Event("close"))` → 1 次。
5. `Esc 後補發 close 去重仍恰一次`(真瀏覽器雙路徑模擬)。
6. [amendment: R1/R3;R2-1/R2-2 修訂手法] `StrictMode + showModal stub 不炸`:
   **jsdom 26 的 HTMLDialogElement 只有 `open` 反射,無 showModal/close → 不能
   `vi.spyOn`(spy 不存在的方法會炸),一律手動裝 prototype、afterEach 手動 delete 拆**。
   stub = `vi.fn(function(){ if (this.open) throw new DOMException(...,"InvalidStateError");
   this.setAttribute("open",""); })` 直接賦值 `HTMLDialogElement.prototype.showModal`;
   `<StrictMode>` 包 render;斷言不 throw、**showModal 恰 1 次(= guard 的真正鎖,
   不可放寬)**、`vi.spyOn(HTMLButtonElement.prototype, "focus")` **恰 2 次**
   (StrictMode 生效自檢 = effect 兩輪各 focus 取消鈕一次;spy 釘在 HTMLButtonElement
   是為了不計 cleanup 對非按鈕元素的還 focus;兩個數字皆不可改不等式)。
7. [amendment: R3;R2-1 同手法;**lock test,無紅可先行**] `unmount → 零 callback`
   (白名單 2 合約):手動裝 close stub(移除 open + dispatch 非冒泡 close 事件)下
   unmount,onConfirm/onCancel 皆 0。mutation 驗證 = 暫時在 cleanup 加 `el.close()` →
   紅 → 還原(Edit 成對,commit 掛 `[lock]` + body `mutation-verified`)。
   裝 stub 的測試結束必拆(不拆會讓同檔測試 1/3/8 的 fallback 分支語意漂移)。
8. [amendment: R4] `class 契約`:dialog classList 含 `m-auto` / `backdrop:bg-bg/85` /
   `max-w-sm`(WatchlistManagerDialog.test.tsx m-auto 鎖法同款)。
9. [amendment: R2] `focus 歸還`:wrapper 內觸發鈕 focus → 掛載 dialog(activeElement
   轉取消鈕)→ 卸載 → activeElement 回觸發鈕。

既有測試該紅/不該紅盤點 [amendment 2026-08-11: review R8 — grep 已定案,全部不該紅]:
- OrderPanel.test.tsx:143/158/172/207(getByText/queryByText)+ :188(closest("div")
  bg-loss — 依賴 header div 保留,見硬約束)
- CapitalOrdersList.test.tsx:166/170/173 + :273(closest("div") 同上)
- CapitalPositionsList.test.tsx:151/159、FuturesLadder.test.tsx:380/399/407/456、
  RightRail.test.tsx:353/476/485(皆 getByText 系,不過濾 display:none)
- CapitalConfirmDialog.test.tsx:24 是全 repo 唯一 `getByRole("dialog")`,依賴 fallback
  設 `open` attribute(jsdom default stylesheet 有 `dialog:not([open]){display:none}`,
  無 open 會被 byRole 可及性過濾掉)
- WatchlistSidebar.test.tsx:599/606 的 `querySelector("dialog")` 不在本元件樹,不受影響

## Edge cases

1. **Esc 與原生 cancel/close 同拍雙發** → closedRef 去重,onCancel 恰一次(SC-2 測試 5)。
2. **FuturesLadder 行情斷自動收窗**(掛載條件轉假,無人按鈕)→ unmount,零 callback,
   top layer 隨元素離開 document 自動清;jsdom 無感。
3. **jsdom 無 showModal** → fallback `open` attribute + 照樣 focus 取消鈕(測試可測)。
4. **確認路徑**:onConfirm 直呼、無前置 guard、無 close 事件 → 恰一次,語意與現行全等。
5. **窄視窗(< 24rem)**:舊版靠遮罩 p-4 留 16px 邊;新版 `w-full max-w-sm` 貼滿寬。
   桌面看盤工具實際不可達,接受(視覺白名單 3 以 ≥ 通常視窗為準)。
6. [amendment: R5] **確認送出後、caller 卸載前按 Esc**(mutation in-flight 窗):
   settled 旗標已立 → 不補發 onCancel,不會出現「畫面表現成已取消但單已送出」。
7. [amendment: R5] **closedRef 一次性不重置**:若未來 caller 的 onCancel 不卸載,第二次
   Esc 無效(僅剩取消鈕可關)— 前提「4 caller 皆卸載」現況成立,破此前提時要改設計。
8. [amendment: R6] **武裝中的階梯開確認窗按 Esc**:只關窗,不解除武裝
   (stopPropagation 擋 window 層監聽;與現行「Esc 解除武裝、窗不關」相比,窗內 Esc
   語意改為以窗優先 — 這是 SC-2 的預期新行為)。
   [amendment 2026-08-11: 自評 review — 影響面實為三處同款 window 層 Escape 監聽:
   FuturesLadder.tsx:243、PriceLadder.tsx:310、StkfutLadder.tsx:235(皆 bubble 階段,
   stopPropagation 擋得住);CapitalOrdersList / CapitalPositionsList 與個股階梯同頁樹,
   「個股階梯武裝中從列表開刪單窗按 Esc」同語意。窗關後階梯仍武裝 — 第二次 Esc 與
   idle 自動解除計時器兜底,接受;替代設計記 next-time]
9. [amendment: R2] **opener 已離開 document**(FuturesLadder 自動收窗、列表重排):
   cleanup 檢查 `isConnected`,不在就不還 focus(落回 body,與現行同級)。
10. [amendment: R2-3] **opener = document.body**(開窗前無聚焦元素)→ 不還 focus;
    還 focus 一律 `{ preventScroll: true }`(不得引發階梯捲動)。

## Out of scope

- 改 caller 掛載模式(persistent mount + open prop)。
- OrderPanel `premium != null` gate 靜默卸載 UX(next-time 2026-08-05 節既有 Known Risk)。
- 其他 dialog(WatchlistManagerDialog / SignalRulesDialog)與 react-doctor 其餘 findings。
- Tab 循環的 jsdom 自動化測試(原生 focus trap 屬瀏覽器行為,真環境層驗)。

## Backward compat / migration

Props 介面、caller、wire 契約皆不變;無持久化資料 → 無 migration;可逆 = revert 單一
commit(元件 + 測試兩檔)。

## 三類 commit 計畫

🔵 無 → 🔴 `test(frontend): CapitalConfirmDialog 原生 dialog 行為紅測試 [red]` →
🔴 `fix(frontend): CapitalConfirmDialog 換原生 dialog(focus trap/Esc/inert)[green]`。

## 自評 review 處置(2026-08-11,round 1 收斂)

reviewer(opus,雙焦點)結果:**0 P0 / 0 P1 / 8 P2**;並獨立重跑全 gate(1719 tests /
tsc / eslint / react-doctor No issues / 4 caller 零 diff / 白名單 5 零刪改行)。P2 處置:
- **accepted 已修**(commit 6f626e70,[lock] + mutation-verified ×2):settled 旗標
  lock test、Esc 不外洩 window lock test、class 契約補 text-ink/p-0、取消後 close 去重
  測試、JSDoc 新 caller 硬性契約、spec edge case 8 影響面補記(上方 amendment)。
- **rejected(記錄不修)**:cleanup 三守衛(isConnected / !==body / preventScroll)
  獨立測試 — jsdom 對 preventScroll 無感、opener 移除情境 harness 成本 > 價值,守衛
  屬防禦性;測試 6 harness 重寫 — 註解已載明前提;passive effect 一幀空窗 — 樣板同款,
  接受。

`self_review_head`: 6f626e70
