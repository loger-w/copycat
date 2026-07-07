
## 2026-07-07(tday-join-ga-backtest 收尾沉澱)

- [ ] config JSON 載入器樣板與 strategy_config.load_config 重複 → 抽 generic helper(review Reuse3,動既有檔屬 🔵 獨立工)
- [ ] atomic write(tmp+os.replace)全專案 5 處手刻 → 共用 helper(review Reuse5)
- [ ] simulate 完整 derived-series 預計算重構(review F2 只做了 anchor 網格限定;若 Phase B 全量變慢再做)
- [ ] neigui 種子事件池刷新管道(池截止邊界:3055 2026-06-18/24 不在池內;滾動重驗前置)
- [ ] .claude/harness.json 殘留模板修正(verify 陣列指向不存在的 backend/frontend)
- [ ] 對照組 T+1 1K 補抓 2,068 筆 + 7-8% 帶 6,509 stock-day TC4 回補(Phase B 前置,需達錢 4 開著)
