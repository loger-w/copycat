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
- **useContainerSize 多態渲染的 regression lock jsdom 測不到**(getBoundingClientRect 恆 0):用真 hook + polyfill ResizeObserver + stub `Element.prototype.getBoundingClientRect`,rerender loading→data 後 assert svg width(`MarketColdLoad.test.tsx` 是樣板)。詳見 skill `frontend-conventions` 的 useContainerSize 條目。Trigger:元件用 useContainerSize 且有 skeleton / 降級多態時。
- **`React.lazy` 元件的閘門測試三坑**(`CorrSection.test.tsx` / `CorrSection.lazy.test.tsx` 是樣板,2026-08-06):(1) `vi.mock` 目標是 default export 時 factory **必須回 `{ default: Stub }`**,否則 lazy 解析直接炸;(2) lazy 即使被 mock 仍非同步 —— 首次 render 必走 Suspense fallback,「query 為 null」對「沒 render」與「還在 suspend」是同一個答案 → 閘門斷言要用 **stub 內 useEffect 的 mount/unmount 計數**(展開先 `await findByTestId` 等真 mount,收合斷言 unmount 計數 +1 而非 queryBy null);(3) vi.mock 是檔案級 + hoisted,「mock stub 測閘門」與「真身測 lazy 路徑」**必須拆兩檔**;真身檔的錨點文字要與 Suspense fallback 逐字可區分。Trigger:寫任何 lazy + 條件 render 元件的測試。
- **手寫 FakeWS 要讓 `close()` 記狀態**(`closed = true`),「元件 unmount = 連線關閉」必須斷言 `instances.every(w => w.closed)` —— 只驗元件消失是 vacuous(cleanup 被改掉照樣綠),並用 mutation(暫時註掉 hook cleanup 的 `ws?.close()`)驗測試真的會紅。Trigger:測任何「unmount 應斷線」的行為。
- **TanStack Query v5 的 refetch 失敗不清 data:`isError=true` 且 `data` 仍在**(`QueryObserverRefetchErrorResult`;2026-08-06 R3 實測)。顯示層拿 `isError` 當「載入失敗」判別子會讓「已有資料 + 背景 refetch 打嗝一次」整片畫面消失 —— 要分 `isError && data === undefined`(從未成功)與 `isError && data !== undefined`(保留資料 + 「更新失敗」弱提示)。樣板:`LimitListSection.tsx`。Trigger:任何 useQuery 消費端寫 error 分支時。
- **TQ observer 通知走 notifyManager 的 macrotask 排程**,`await act(...)` 只 flush microtask → 斷言 query state 轉換(如 refetch 轉 error)前要再補一層 `waitFor`。Trigger:測 refetch / invalidate 後的 state 轉換。
- **RTL `waitFor` 在 vitest 下偵測不到 fake timers**(`jestFakeTimersAreEnabled()` 查全域 `jest`,vitest 恆 false → 退回真 interval):`vi.useFakeTimers()` + `findBy*`/`waitFor` 組合會 timeout(lazy 元件連 mount 都等不到)。解法:輪詢行為用「hook/元件層 fake timers + 手動 advance」測;App 級整鏈改斷言 `refetchInterval` 求值結果(白盒但可紅),或只假造 `Date` 不假造 timer。用了 fake timers 的測試檔 `afterEach` 必補 `vi.useRealTimers()`(不還原會外溢到別檔)。樣板:`useBreadthRows.test.ts` / `App.test.tsx` R3 跳轉測試。Trigger:測任何 refetchInterval / 輪詢節奏。
