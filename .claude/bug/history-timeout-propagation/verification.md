# verification — bug/history-timeout-propagation(R8)
## 自動化(2026-08-21 22:3x):pytest 2887 passed(baseline 2853 → +34)| ruff All checks passed | pyright 0 | 前端未動(payload 零變)
## 紅測試 → 綠:初版 20 支(四 caller 家族 + 引擎層)+ review round 1 七條行為 12 紅;反向驗證:`git revert --no-commit d73477ba` → 同 20 支紅,還原 1724 綠。
## Mutation:round 1 fix 7/7 killed(ConnectionError 子類 / rollover 清 / Date 閘關 / Date 台北換算 / dk and→or / 純 ConnectionError 進 pending / close 不取消)。
## Plan review(13 條)→ 收窄:index 路徑不改(variant 逃逸)、DK 保留 fallback、futures engine 內吃掉只 log、stock 回補與 river 腿有界重試。Code review:P1×4 / P2×14 全 accepted(TQ-11 rejected:optional 耦合)。
## Blast radius:`HistoryTimeoutError(ConnectionError)` 可達四條 raise(stock backfill / fetch_daily_bars 雙段 / futures bars / river 首頁),上游皆顯式接住;其餘 `except ConnectionError` 站點不可達(TXO round 制、index fetch_day_minutes 不改、stock bars 三態)。tests/live + tests/server 1741 綠。
## 真實環境:TC4 冷啟動忙碌窗口不可刻意重現 → 以 fake timed_out 測試為證;merge 後重啟 8721 health sha;**user 於下次冷啟動(盤前)看 log:`backfill … timeout 重排` / `river 回補逾時腿 … 重試` 字串 = 機制命中;不再出現「首頁未備妥,回空」後無後續**。
## 留尾(next-time 已記):期貨三態 status 通道(payload + 前端)、fetch_daily_bars 1K fallback 縮窗、格式改動夾 🔴、BalanceCollector 無關。
