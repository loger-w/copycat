# Progress ledger(refactor/memo-boundaries)

- [x] Why gate + branch(refactor/memo-boundaries,自 master 294f604a)
- [x] test-inventory.md / refactor-plan.md
- [x] plan review round-1(P0×3 accepted 修入)+ round-2 限縮(P1×1 修入,無 P0)
- [x] baseline:vitest 2323 全綠(分支 HEAD,2026-08-20 14:2x)
- [x] S1 App→RightRail 邊界(三拍:baseline evidence → 🔵 8baec1f1 → 🟢 a2bbf860)
      baseline 個股 tab 2→4 / 台股綜合 tab 4→8;改後皆 +0。
      mutation:拔 memo → 紅;stockCtx deps 去 accum → 紅。
      gate:vitest 2327 全綠 / tsc / eslint 全過。
- [x] S3 江波圖 corr(四拍:🟢 64176619 characterization → baseline evidence → 🔵 81ebb195 → 🟢 bff966e4)
      baseline → 改後:hover 三則 mousemove 幾何 +3→+0;單腿 tick 的對照腿幾何 +1→+0、
      並排卡片 render +3→+1(只有真的動了的那張)。
      mutation:(a) 拔 memo(RiverCard) → 跨腿案紅(3 vs 1);(b) 幾何 useMemo deps 加
      cursor → hover 案紅(+3 vs +0);(c) 附帶驗 characterization:readout 改包
      useMemo([g])(R1 失敗模式)→ hover 4 條中 3 條紅。
      **偏離 plan**:計次探針多加一支 `timeTicks`(render 次數)—— 第一版只量
      buildLegGeometry,mutation (a) 當場全綠 = 假 lock(卡內 useMemo 把幾何擋住,
      量不出 memo 在不在)。plan 的「量子元件邊界」在此不可行(RiverCard 是
      RiverCards.tsx 內部符號,mock 不到),故以 render body 內的 lib 呼叫當探針。
      gate:npm test 2333 passed(133 檔)/ tsc -b / eslint src / react-doctor
      --scope changed(7 檔,No issues)全過。
- [x] S2 MarketPane OverlayCard 幾何(三拍:baseline evidence → 🔵 951628ff → 🟢 9497ac44)
      **toggle 狀態(plan R10)**:計次測試強制開啟「重疊」(fireEvent.click),產品預設是關
      → 使用者不開重疊時本步實際收益 = 0,收尾對照須以此解讀。
      baseline → 改後:期貨 tick 連推三則(twse/otc 同參照)幾何 +3→+0(1.0 次/事件);
      加權多一個分鐘點 +1 不變(反向守門)。
      deps = [twse.minutes, twse.ref, otc.minutes, otc.ref, height];`size` 物件現建不入
      deps(memo 內改吃 `{ width: SIZE.width, height }`)、`unitScale`/`font` 非幾何輸入。
      mutation:(a) 拔 useMemo → 無關 rerender 案紅(3 vs 0);(b) deps 改 [] → 真變更案
      紅(0 vs 1)。兩方向各有守門。
      gate:npm test 2335 passed(134 檔)/ tsc -b / eslint src / react-doctor
      --scope changed(9 檔,No issues)全過。
- [x] Code review fix 波(雙 lens review 9 項;兩拍:🔵 fa53c357 → 🟢 72d144ef)
      🔵 fa53c357 = F 項(唯一動 source):`OverlayCard` 內兩份
      `{ width: SIZE.width, height }` 字面量(幾何一份 / viewBox+刻度一份)併成
      `const size = useMemo(…, [height])`,幾何 useMemo deps 由 `[…, height]` 換
      `[…, size]`(等價)。行為零差異,index/ 8 檔 160 tests 全綠。
      🟢 72d144ef = A–E / G–I 八項測試與註解:
      - A 期貨 tab 案(mock FuturesLadder 葉子記 {state,contract};連號 WS →
        葉子拿到新 p/新 bids)+ 反向串擾案(watchlist_quote → 期貨葉子 +0)
      - B `pushFuturesTicks` 註解修正(舊註解把「計次沒變」的證明力講反了)+
        新 `expectFuturesDelivered()`(跳號 seq 99 → 計次 +1)掛在兩條 +0 案
      - C 重疊模式反向 lock(幾何 +1 且該腿末點標籤 x 68→100,台指維持 68)
      - D 三支葉子改 `importOriginal` partial mock(PriceLadder 的 TRADE_KINDS /
        CapitalOrdersList 的 isFutMarket 會被全量 mock 吃掉)
      - E book 案補 meta.name;換股案 ×2(見下方偏離)
      - G hover render-body 成本拍照(ticks +3,註明非收斂目標)
      - H `components/corr/river-test-fixtures.ts` 共檔(DAY/riverState/mockRect/xAt)
      - I App.memo 檔頭註記 TXO snapshot 恆 null 是 orders 計數器的前提
      mutation(全部 Edit 成對還原,`git diff` 確認無殘留):
        (a) `futuresCtx` deps 去 `futProd` → A 案紅(expected 2 to be greater than 2)
        (b) `entries` deps 由 `[legs, off]` 改 `[off]` → C 案紅(expected +0 to be 1)
        (c) `stockCtx` deps 去 `stockCode` → 「snapshot 未到就換股」案紅
            (expected '9101' to be '9102')
        (d) 拔 `memo(RightRail)` → 三條 +0 案全紅(含新的反向串擾案 4 vs 2,
            證明 watchlist_quote 確實重繪整棵樹,+0 不是空綠)
      **偏離 plan(E)**:plan 寫的「換主檔 → 新 snapshot 落地 → 斷言新 code +
      新 meta.name」在 mutant (c) 下**是綠的** —— 換股必經 `setAccum(null)`,
      `accum` 這個 dep 自己就把 memo 撞開,漏 `stockCode` 只影響中間一幀、終值
      照樣收斂。故該條保留為值 lock,另補「兩檔 snapshot 皆 404 → accum 全程
      null、identity 不換」的案例才取得真紅(此時右欄**永久**掛上一檔股號)。
      gate:npm test 2340 passed(134 檔)/ tsc -b / eslint src /
      react-doctor --scope changed(10 檔,No issues)全過。
- [ ] 全套 gate + verification.md
- [ ] 真 tick 層(驗證窗口:夜盤 15:00+ 或次一交易日)
- [ ] 收尾(branch-lifecycle)
