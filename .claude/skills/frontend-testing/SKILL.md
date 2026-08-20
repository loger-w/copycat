---
name: frontend-testing
description: 前端 vitest / RTL 測試慣例。寫 component 或 hook 測試前先讀 — 含 vi.spyOn mock pattern、本專案沒裝 jest-dom/user-event 的替代寫法、RTL selector 陷阱、Radix Tabs jsdom 不可靠、TanStack Query error 終態測試。
---

> 來源:2026-07-06 自 neigui 專案複製。文中「樣板」檔案路徑(services/finmind.py、conftest.py、lib/api.ts 等)指 neigui repo(C:\side-project\neigui)的 code,本專案對應實作落地後再改寫為本地路徑。

# 前端測試慣例

- **Mock 一律 `vi.spyOn(optionsApi, "...").mockResolvedValue / mockRejectedValue`**,**不要**引入 MSW(專案沒裝)。Failure-isolation 測試在 `OptionsChipPanel.test.tsx` 用 `vi.spyOn` + `screen.getByText` 驗,不走 DevTools MCP。Trigger:寫 hook / component 測試時。
- **沒裝 `@testing-library/jest-dom` 也沒裝 `@testing-library/user-event`**。**禁止**用 `toBeInTheDocument()` / `toHaveTextContent()` / `userEvent.click()`,以 `ModeSwitch.test.tsx` 風格為標準:`expect(el).toBeTruthy()` / `expect(el).toBeNull()` / `el.textContent` / `el.getAttribute()` + `fireEvent.click(...)`。Trigger:寫新 component / hook 測試。
- **RTL `getByText(regex)` 撞多元素 = selector 過鬆,不是 Portal leak**。Radix Popover 內兩處含相同 substring 時寬鬆 regex 會 `getMultipleElementsFoundError`。修正:換更精確 substring(動詞前綴如 `/新增X/`)或 `within(container)` 收斂 scope,**不要**第一直覺加 `document.body.innerHTML = ""` afterEach hack(只在真有 portal 殘留時才必要)。Trigger:寫 Radix Popover / Dialog 元件測試,內容含 user-editable 文本。
- **Radix `Tabs` 在 jsdom + fireEvent.click 不可靠**:Tabs.Trigger 走 pointer events,fireEvent.click 不一定觸發 onValueChange;且 inactive `TabsContent` 不 forceMount = 內容不在 DOM。**不要**為了「對齊 Radix」而用,改寫成普通 `<button role="tab" aria-selected>` + 條件 render(`MarketLeaderboard.tsx` 是樣板)。Trigger:寫 jsdom 測試含 Tab 切換的元件。
- **TanStack Query v5 hook 的 `retry: 1` + `error` 終態測試**:default `retryDelay` 是 exponential backoff(初次 1s,二次 2s),`waitFor` default 1s timeout 抓不到 settle。error path test 必須給 `waitFor` timeout: 5000 或 mock cancelable promise。Trigger:寫 useQuery hook 的 error path test。
- **useContainerSize 多態渲染的 regression lock jsdom 測不到**(getBoundingClientRect 恆 0):用真 hook + **fake `ResizeObserver`**(`observe(node)` 時同步呼叫 callback 餵 `[{contentRect:{width,height}}]`;`vi.stubGlobal` 只在該 it 內 + `afterEach(vi.unstubAllGlobals)`,對照案不 stub → 退固定 SIZE)後 assert svg `viewBox` 高 ≠ 固定值(本 repo 樣板 `components/index/MarketPane.size.test.tsx`,2026-08-16;舊引用 `MarketColdLoad.test.tsx` 是 neigui 遺留,本 repo 不存在)。注意 hook 讀的是 RO entry 的 `contentRect`,stub `getBoundingClientRect` 量不到。詳見 skill `frontend-conventions` 的 useContainerSize 條目。Trigger:元件用 useContainerSize 且有 skeleton / 降級多態時。
- **`React.lazy` 元件的閘門測試三坑**(stub 計數閘門樣板 `IndexPage.test.tsx` 歷史版 / 真身拆檔樣板 `App.corr-tab.test.tsx`(不 mock CorrPage、錨點「等待六腿資料…」與 Suspense fallback 逐字可區分),2026-08-06 建、2026-08-16 CorrSection 刪除後改指):(1) `vi.mock` 目標是 default export 時 factory **必須回 `{ default: Stub }`**,否則 lazy 解析直接炸;(2) lazy 即使被 mock 仍非同步 —— 首次 render 必走 Suspense fallback,「query 為 null」對「沒 render」與「還在 suspend」是同一個答案 → 閘門斷言要用 **stub 內 useEffect 的 mount/unmount 計數**(展開先 `await findByTestId` 等真 mount,收合斷言 unmount 計數 +1 而非 queryBy null);(3) vi.mock 是檔案級 + hoisted,「mock stub 測閘門」與「真身測 lazy 路徑」**必須拆兩檔**;真身檔的錨點文字要與 Suspense fallback 逐字可區分。Trigger:寫任何 lazy + 條件 render 元件的測試。
- **期望值寫字面量,不由 import 的同一顆常數算回來**(2026-08-21 B1 review B2 實證):`expect(f(x)).toBe(g(CONST))`
  與實作同源同常數 = 同義反覆,`CANDLE_CHROME_Y` 100→84 / `INSET_X` 34→30 的 mutant 71/71 全綠。
  契約常數的測試把數字寫死並在註解寫拆解(`396 = 430 − 34(border 2 + p-4 32)`);常數只 import 給
  「邊界值恰等於常數」這類語意案例。取整(round/floor)要用**小數輸入**才有鑑別力(`430.6 → 397`
  只有 round 給得出)—— ResizeObserver 的 contentRect 本來就是小數。Trigger:測任何「量測 → 尺寸」
  純函式或 chrome 常數。
- **手寫 FakeWS 要讓 `close()` 記狀態**(`closed = true`),「元件 unmount = 連線關閉」必須斷言 `instances.every(w => w.closed)` —— 只驗元件消失是 vacuous(cleanup 被改掉照樣綠),並用 mutation(暫時註掉 hook cleanup 的 `ws?.close()`)驗測試真的會紅。Trigger:測任何「unmount 應斷線」的行為。
- **TanStack Query v5 的 refetch 失敗不清 data:`isError=true` 且 `data` 仍在**(`QueryObserverRefetchErrorResult`;2026-08-06 R3 實測)。顯示層拿 `isError` 當「載入失敗」判別子會讓「已有資料 + 背景 refetch 打嗝一次」整片畫面消失 —— 要分 `isError && data === undefined`(從未成功)與 `isError && data !== undefined`(保留資料 + 「更新失敗」弱提示)。樣板:`LimitListSection.tsx`。Trigger:任何 useQuery 消費端寫 error 分支時。
- **TQ observer 通知走 notifyManager 的 macrotask 排程**,`await act(...)` 只 flush microtask → 斷言 query state 轉換(如 refetch 轉 error)前要再補一層 `waitFor`。Trigger:測 refetch / invalidate 後的 state 轉換。
- **TQ v5 的 refocus refetch 只聽分頁 `visibilitychange`(hide→show),純 window focus 不觸發**(v5 focusManager 移除了 v4 的 focus listener;2026-08-11 useStockNames review 實證):「停掉輪詢後靠 refocus 復原」這類假設要以此為準 — 使用者切到別的應用程式視窗但分頁仍可見時**不會**觸發。測 refocus 後門用 imperative API:`focusManager.setFocused(false); focusManager.setFocused(true)`(不依賴 jsdom 事件),`afterEach` 補 `focusManager.setFocused(undefined)` 防外溢;樣板 `useStockNames.test.tsx` 永久失敗整合測試。Trigger:寫任何依賴 refetchOnWindowFocus 的行為或其測試。
- **StrictMode double-invoke 紅測試法(updater 純度 bug 專用)**:updater 內夾副作用(fetch /
  localStorage 寫入)在一般測試下恆綠 — 要 `<StrictMode>` wrapper + 副作用計數斷言恰一次
  (fetch calls 記 `before` 差值 / `vi.spyOn(Storage.prototype, "setItem")`)。三個必要件:
  (1) **StrictMode 生效自檢**(FakeWS `instances.length === 2`,或 getItem spy 對 useState
  lazy initializer 計 2 次)— 否則 wrapper 被拿掉時測試靜默轉 vacuous;(2) 紅態期望不寫死
  次數(eager updater 可能 3 不是 2),斷言修後的「恰 +1」;(3) FakeWS 場景取
  `instances.at(-1)`(對 instances[0] 發訊息會被 `alive=false` 丟掉 → 假綠)。樣板
  `useRiver.test.ts` / `WatchlistSidebar.test.tsx` StrictMode 節(2026-08-11)。Trigger:
  修任何「setState updater 內有副作用」bug 或寫其紅測試。
- **key 穩定性用 DOM node 恆等測試釘**:list key 位移(index-as-key 前插)的症狀是整片卸載
  重掛,RTL 文字斷言全抓不到 — 記住列的 element reference,rerender 後斷言 `===` 恆等
  (位移時 React 以新 key 建新 node → 必紅)。樣板 `TickTape.test.tsx`(2026-08-11)。
  Trigger:改任何 list key 策略或修 index-as-key finding。
- **jsdom 26 的 `HTMLDialogElement` 只有 `open` 反射,無 showModal/close/原生 Esc**(2026-08-11
  CapitalConfirmDialog 實證):(1) `vi.spyOn(prototype, "showModal")` 會炸(spy 不存在的方法)—
  要測 showModal 分支一律**手動裝 prototype stub**(`vi.fn(function(){ if (this.open) throw new
  DOMException(...,"InvalidStateError"); this.setAttribute("open",""); })`,close 同款派發非冒泡
  close 事件)+ **afterEach 手動 `delete` 拆**,不拆會讓同檔 fallback 分支測試語意漂移;
  (2) fallback 分支(元件 feature-detect 後 setAttribute("open"))與 stub 分支拆兩個 describe;
  (3) StrictMode 雙輪鎖 `!el.open` guard 時,focus 自檢 spy 釘 `HTMLButtonElement.prototype`
  (不計 cleanup 對 body/opener 的還 focus),showModal 恰 1 次 + focus 恰 2 次皆不可放寬成
  不等式。樣板 `CapitalConfirmDialog.test.tsx`。Trigger:測任何 `<dialog>` 元件。
- **RTL `waitFor` 在 vitest 下偵測不到 fake timers**(`jestFakeTimersAreEnabled()` 查全域 `jest`,vitest 恆 false → 退回真 interval):`vi.useFakeTimers()` + `findBy*`/`waitFor` 組合會 timeout(lazy 元件連 mount 都等不到)。解法:輪詢行為用「hook/元件層 fake timers + 手動 advance」測;App 級整鏈改斷言 `refetchInterval` 求值結果(白盒但可紅),或只假造 `Date` 不假造 timer。用了 fake timers 的測試檔 `afterEach` 必補 `vi.useRealTimers()`(不還原會外溢到別檔)。樣板:`useBreadthRows.test.ts` / `App.test.tsx` R3 跳轉測試。Trigger:測任何 refetchInterval / 輪詢節奏。
- **「preventDefault 有沒有被呼叫」jsdom 可觀察:`fireEvent.*` 的回傳值就是 `dispatchEvent` 結果**(2026-08-11 CandleChart wheel 實證):事件 `cancelable: true` 且任一 listener(含原生 `passive: false` 的 addEventListener)呼叫 `preventDefault` → `fireEvent` 回 `false`。「原生 listener + passive:false 擋頁面捲動」這類契約別當成 jsdom 不可測 —— 一行 `expect(fireEvent.wheel(el, { …, cancelable: true })).toBe(false)` 就釘住(換回 React `onWheel`(root 掛載,passive)或忘了 preventDefault 的 mutant 都會紅)。另:連發兩個 mousemove 才能區分「絕對位移(以拖曳起點為基準)」與「逐次累加」— 單 move 的拖曳測試兩種實作恆同值,clamp 漂移 mutant 全綠。樣板 `CandleChart.test.tsx` characterization 節。Trigger:測 wheel/scroll 攔截、或任何「以起點為基準」的拖曳幾何。
- **memo 計次 lock 的探針不能落在 useMemo 內**(2026-08-20 memo-boundaries 實證):量「拔
  `memo(Component)` 會不會紅」時,若探針是元件內已被 `useMemo` 包住的計算(如幾何函式),
  拔掉 memo 後 useMemo 照樣擋住重算 → mutant 全綠、lock 是假的。探針要選 **render body 內、
  不在任何 useMemo 裡**的呼叫(如 `timeTicks`)或子元件邊界;寫 lock 前先想「目標 mutant
  會不會讓這個探針動」。同輪教訓:內部符號(`RiverCard`/`OverlayCard`)`vi.mock` 搆不到 →
  `importOriginal` partial mock lib 函式,**其餘 export 必須 `...actual` 保真**(漏了
  X_START_MIN/offsetAtX 這類常數,座標全 NaN)。樣板 `RiverPanel.memo.test.tsx` /
  `MarketPane.memo.test.tsx` / `App.memo.test.tsx`(葉子 mock + deps 內容斷言雙向守門)。
  Trigger:寫任何 `.memo.test.tsx` 計次測試 / mock 內部元件符號。
