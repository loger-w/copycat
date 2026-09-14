# 重啟前基線(2026-09-14 20:3x,prod 仍跑舊版 6cbf7cdd,15:07 起)

## 時鐘偏差(T1 模組 `clock_monitor.probe` 在 worktree 直跑)

```
INFO copycat.server.clock_monitor: 時鐘偏差:+2861 ms(time.google.com,RTT 9 ms)
ERROR copycat.server.clock_monitor: 時鐘偏差 2861 ms 超過 2000 ms:本機鐘超前,校時服務可能沒在跑(W32Time 設 Automatic + w32tm /resync)
ClockSample(offset_ms=2860.59, rtt_ms=8.92, host='time.google.com')
```

- 17:32 手寫 SNTP 腳本三台一致:server − local = −2624 / −2627 / −2626 ms → 本機**超前** 2.6 s(spec 正文的
  「落後」是符號讀反,已在 #232 留言勘誤)。
- 20:30 模組量:+2861 ms。三小時漂 +0.24 s。
- `Get-Service W32Time` → Stopped / Manual;登錄 `NtpServer = time.windows.com,0x9`;此 shell 非 elevated。

## 回報鏈(`python -m copycat chain-stats`,worktree 版對主樹 logs/)

```
== 全部 logs/server-*.log
回報鏈 198 條,乾淨 150 條(排除:no_start 4、non_monotonic 6、off_session 33、short_balance 5)
乾淨子集落地耗時:p50 1952 ms / p90 2993 ms / p99 6433 ms
群益 1019 × 342
== server-20260910-0905:20 條,乾淨 19(non_monotonic 1);p50 2264 / p90 5412 / p99 6639;1019 × 14
== server-20260911-0905: 9 條,乾淨 6(non_monotonic 2、short_balance 1);p50 2001 / p90 3947 / p99 3947;1019 × 13
== server-20260914-0815:13 條,乾淨 10(non_monotonic 3);p50 1900 / p90 2013 / p99 2936;1019 × 18
```

對照 V2 §2.3(178 條、乾淨 150 條、盤中乾淨 p90 3,027):同量級,判準腳本與研究手算一致。

## 群益 status(舊版 server,重啟前)

```
GET /api/capital/status → {"status":"ok","env":"prod","account_masked":"****0270","futures_account_masked":"****7083","order_enabled":true}
GET /api/health → {"git_sha":"6cbf7cdd","git_dirty":true,"started_at":"2026-09-14T15:07:05"}
```

`reply_connected` 缺欄 = 舊後端(#235 契約:缺欄 = 舊後端,前端不讀)。

## 手機下單三筆(回報線帳號層級證實)

09-14 回報線 23 個委託序號、audit 20 個;差 3 個(8358 失敗 / 081802 委託後刪單 / 3008 十股成交)
都在 `/api/capital/orders`;3008 是零股,閃電梯排除零股是設計(CLAUDE §4)。
