# progress ledger — futures-allday-tab

plan: .claude/feat/futures-allday-tab/implementation/PLAN.md(worktree:
C:/side-project/copycat/.claude/worktrees/feat-futures-allday)

Task 切分(序列 dispatch,一次一個 implementer,opus):

- T1 後端 bars:PLAN §1–§6(stock_source 多段域+uv/dv、futures_source allday、
  futures_engine session、bars.py cache key、fake_sources、app.py session query)
- T2 後端 OI:PLAN §7(oi_levels.py + route 整合測試)
- T3 前端 libs:PLAN §8–§15 + §23(allday、fut-chart-mode、trading-hours、candle.ts、
  settlement、spot-session、oi-levels、close-order、constants、types)
- T4 前端 hooks + CandleChart:PLAN §16–§18
- T5 FuturesChart + FuturesPage + App:PLAN §19–§20
- T6 FuturesLadder + CapitalPositionsList:PLAN §21–§22

## log

(每 task 完成追加:task / commit 範圍 / review 結果;fix round 逐輪追加)

- T1 完成:commits d75a78f..7ba65e8(red/green 兩對)。review gate PASS(main agent
  讀 diff 手驗段判定/clamp/filter/cache 複合鍵;自跑 pytest 1764 passed + ruff +
  pyright 0)。合理偏離 2 項:白箱 cache 測試鍵字面值同步 "2330:day"(防 vacuous);
  _delta_vol 兩欄皆缺回 None 不填 0(保 bar 形狀,優於 PLAN 字面)。
- T2 完成:commits 8ffd346(red)+ 91e91f1(green)。review gate PASS(oi_levels.py
  303 行讀過:口徑/降級/402/token 慣例全對齊;pytest 1778 passed)。合理偏離 2 項:
  空 pivot 結果走負向 TTL 不永久快取(don't-cache-empty 同理);asyncio.Lock 改
  per-event-loop(測試多 loop 相容,server 單 loop 行為恆等)。
- T3 完成:commits e0d76c2..9d5e125(三對 red/green + 1 紅測試算術修正)。review gate
  PASS(candle.ts diff 手驗:桶溢位進位/deltaVol null 語意/hlineYOf 借 priceAtY 夾制;
  vitest 1223 passed / tsc / eslint 0)。偏離 8 項全接受;注意:kindOf 改 Object.hasOwn
  (病態值行為修正,T6 接線時生效)。
- T4 完成:commits 8abb67f(red)+ bd44586(green)。review gate PASS(vitest 1241 /
  tsc / eslint 0;既有 CandleChart 38 條原文未動)。偏離 3 項全接受(EMPTY_HLINES 模組
  常數防 memo 打穿、hline 文字不套 stroke class、FuturesBarsKey 型別不反向依賴 App)。
  T5 接口備忘:unavailable 由消費端處理;hlines 必 useMemo;volumeDelta 可恆傳 true。
- T5 完成:commits f1c5bfe(red)+ 1732b6c(green)。review gate PASS(vitest 1265 /
  tsc / eslint 0;live 點 +1 終點標記與錨定日 gate 手驗;FuturesPage 既有斷言逐字未動,
  test-infra 換 wrap(QueryClientProvider)已註明)。偏離 7 項全接受(分時幾何留元件層
  purely 純函式可測、INTRADAY_VB_W=ALLDAY_LEN 一分一像素、不加 stream prop)。
- T6 完成:commits ca6a711(red)+ 84b7460(green)+ 9ae1c90(refactor)。review gate
  PASS(vitest 1274 / tsc / eslint 0;紅態 7 failed 證據;PositionsList 既有 9 測試
  一字未動 = 重構保護)。偏離 3 項全接受(彈窗不帶 danger → next-time、無部位 title
  分開寫、todayOf 重複 4 行 → next-time)。觀察:一次未落檔的 3-test flake 後連續 4
  次全綠,環境級嫌疑,Phase 5 再盯。
- Phase 3 完成(T1–T6 全落地)。
- Phase 4 code review round 1:3 lens(時序/覆蓋 mutation/spec 白名單)→ P1 x4 + P2 x13,
  16/17 accepted(LF-5 rejected:既有大盤行為,記 next-time)。後端 fix 波
  62c582b..c0d3800(TC-1/5/6/7、TZ-1/2、LF-3/4;pytest 1794 passed;DOTENV_MODULES
  反駁接受不加)。前端 fix 波 ef2c07a..1b95d89(TC-2/3/4/8、LF-1/2、TZ-3;main agent
  複跑 vitest 1290 passed / tsc / eslint 0 —— 中斷只切掉子代理回報,commit 全落地)。
