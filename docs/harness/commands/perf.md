# Optimize: $ARGUMENTS

(若 $ARGUMENTS 為空,先問我要優化什麼、目標數字是多少再繼續。)

共通鐵則套用 `~/.claude/CLAUDE.md`。自主模式契約見 `~/.claude/commands/auto.md`。

## 核心紀律
**沒量測就不是 optimization。** 沒可量化目標 → 切到 `/refactor`。

## Phases

0. **Phase 0|工作區**:呼叫 `branch-lifecycle` 開工節(status 乾淨 + 主線同步 + `git switch -c perf/<slug>`)
1. **Phase 1|量化目標 gate**(必須,不可跳):
   - **現況數字** + 量測方式 + 環境(例:LCP p95 = 3.2s / DevTools Performance / prod-like build)
   - **目標數字**:具體 threshold
   - **可重現量測步驟**(寫下來,unit + 指令,同 /feat 的量化 SC gate)
   - Baseline 量測前呼叫 `auto-verify` 自動化節確認全綠(壞掉的 tree 量出的 baseline 無意義;對應該 skill「何時呼叫」的 /perf Phase 1 條目)
   - 沒可量化目標 → 停,「感覺慢」不算
2. **Phase 2|Profile 找真實 bottleneck**:呼叫 `superpowers:systematic-debugging`(profile 假說同樣是假說 — 一次驗一個,用實驗證明是 **root bottleneck** 不是「順便也慢」的旁支),不准靠直覺猜:
   - Frontend:DevTools Performance / React Profiler / bundle analyzer
   - Backend:py-spy / cProfile / SQL EXPLAIN ANALYZE / APM
   - 網路:DevTools Network / HAR / k6
   - **退出條件**:3 輪 profile 仍定位不到 bottleneck → 套鐵則 F 停下回報(可能是分散式慢、無單一 bottleneck,該重新定義目標)
3. **Phase 3|策略 + Trade-off**:寫 `.claude/perf/<slug>/optimize-plan.md`
   - 每策略:預期改進幅度(理論計算或粗估)/ 複雜度成本 / 新 failure mode 風險
   - 列「**行為保證不變**」的既有測試 / 功能白名單
   - 排優先序:CP 值高的先做(big O > 常數級)
4. **Phase 4|實作**:
   - 既有測試保持全綠(行為不變)
   - 加 **performance test / benchmark**(可重複跑的,入庫 — Done 條件之一)
   - Cache 類策略:實作前 optimize-plan.md 該策略節必列 invalidation 三欄 — 失效時機 / bust 觸發點(誰在哪呼叫)/ 驗證測試名;缺任一欄不准實作(cache 是最容易引入 bug 的優化)
   - **一個策略一個 commit**(才能歸因哪個有效)
5. **Phase 5|量測**(關鍵):
   - 跑跟 Phase 1 **完全一樣**的量測方式
   - 對照目標 → 達標寫 before/after 改善 %
   - 量**其他不該退化的 metric**(整體性能 / 記憶體 / 其他 endpoint)→ 確認沒拆東牆補西牆
6. **Phase 6|行為驗證**:呼叫 `auto-verify` skill(自動化 + 真實環境)— 全部測試綠 + dev server 真實場景結果跟優化前完全一樣 + 邊界 case(空 / 大量 / 極端輸入)+ prod-like 量測(dev 數字常騙人)
7. **Phase 7|回頭核**:呼叫 `superpowers:verification-before-completion` — 目標達標?(before / after 表)沒退化其他 metric?Trade-off 可接受?三個月後別人看得懂?

## 失敗 routing
- **沒達標** → 不是「優化成功只是不夠多」,hypothesis 可能錯,回 Phase 2 重新 profile(瓶頸可能已移到別處)
- 行為變了 → **這已經是 mod 不是 perf**,停下切 `/mod`
- 其他 metric 退化 → 回 Phase 3 重估 trade-off,可能 revert
- 3 次量測都沒達標 → 套鐵則 F 回報三策略

## 自主模式建議
✓ 強烈推薦:`/auto <metric 達標如 LCP < 2.5s> 且 既有測試全綠 /perf <metric>`

## Done
Metric 達標 + 既有測試全綠 + benchmark 入庫 + 沒退化其他 metric + before/after 對照表。
**全過後呼叫 `branch-lifecycle` 收尾節**(push → PR → review 補齊 → merge 確認 → auto-merge),再做最終回報。

## 禁止(本流程特有,共通禁止見 CLAUDE.md)
- ❌ 沒量測就開始改(premature optimization)
- ❌ 沒 profile 靠猜哪裡慢
- ❌ optimize-plan.md 沒列 invalidation 三欄(失效時機 / bust 觸發點 / 驗證測試名)就加 cache
- ❌ 為了 1% 改善加 100% 複雜度
- ❌ 改完沒重新量測就說「應該更快了」
- ❌ Dev 環境量到的數字當 production 用
- ❌ 行為變了硬說「優化成本」(那是 mod)
- ❌ 一次改 N 個策略沒辦法歸因哪個有效
