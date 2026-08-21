# verification — mod/signal-alert-grouping(R3)
## 自動化(2026-08-21 16:3x)
| vitest | 136 files / 2468 passed(baseline 2447 → +21)| tsc 0 | eslint 0 | react-doctor No issues |
## SC
- SC-1 同 tick 三則一張(含 StrictMode、overflow 浮首、stale drop、dismiss 後同鍵、同 kind 去重)PASS;SC-2 嗶每組 PASS;
- SC-3 通知 trailing(絕對時刻 192 / 228 / 跨標的 / 合併文案字面 / 節流窗 / 丟棄不記帳 / unmount)PASS;SC-4 單則等價 PASS;
- SC-5 截圖 docs/specs/mod-signal-alert-grouping/screenshots/(同 tick 三則一張 + 另檔獨立)。**待 user 過目:多行 toast 觀感(C7)、真實 hidden tab 首則通知延遲 ≈1s(C1)。**
## 白名單 W1 音效 11 案未動 / W2 固定 tag + 5s 窗(TQ-1 新 lock)/ W3 / W4 formatToastText、groupSignals 未動 / W5 ToastStack 未動。
抽 2 未改:useSignalFeed.test 綠;SignalRail 測試綠。dev 注入口已 revert(e4df8ab1)。
## Migration 無。self_review_head = e24b4a12
