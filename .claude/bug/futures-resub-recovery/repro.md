# fix/futures-resub-recovery — futures_engine 重連復原三洞(startup-names 回溯補審 P1 批)

**分流判定**:規格來自已拍板文件(docs/next-time.md 2026-08-10 節 +
`.claude/bug/startup-names-futures-resub/code-review-round-1.json` 回溯審,逐條含
suggestion)→ 預核准,無方向性抉擇。正解照抄 corr/stock 姊妹實作語意。

## Scope

- **P1-1**:`_resub_loop` 只接 `ConnectionError` — 壞電文(JSONDecodeError/KeyError)
  殺死復原路徑且零 log;同顆例外從 `close()` 的 `await resub` 重拋 → `source.close()`
  跳過 → KeepAlive 洩漏 process 不退。修法照 corr_engine `_resub_round` + except
  Exception 續行 + close suppress 放寬。
- **P1-2**:`close()` 只 cancel 不等 in-flight `to_thread` — 排入 executor 未啟動的
  工作項在 `source.close()` 之後才跑 subscribe → `_ensure_connected` 重建 TC4 連線。
  修法照 stock_engine `_EngineClosing` 縮窗(worker 先查 `_loop is None`)。
  [auto-default: 採縮窗不採「close 等完 in-flight」| reason: task 指名照抄 stock
  縮窗語意;等完在 outage 下會讓 close 阻塞 REQ timeout 10-20s,stock 已文件化接受
  縮窗;殘餘 race 的根治 = tc4 _ensure_connected 原子化(P2-5,獨立 /mod 本輪不動)]
- **P1-3**:`_check_stale` 重連掉訂閱零復原 — SUBQUOTE 失敗品靜默丟出 `_subscribed`
  且零 log;迴圈中途拋錯 → 尾段 symbol 永久蒸發;FuturesEngine 是四引擎唯一沒接
  `on_reconnect` 的。修法 = engine 接 on_reconnect 對帳(全品回填 `_pending_subs`
  重啟迴圈;subscribe UNSUB→SUB 冪等,重掛活品無害)+ tc4 重連迴圈 else 補 warning。
- **P2-1**:重試成功後 HOT + leaf 雙訂閱 → 重試成功處 `_leaf_fed.discard(product)`
  + 更正過寬註解(部分失敗時 leaf 接得到,全失敗才接不到)。
- **P2-3**:兩條收斂不變式斷言結構性無效(M1/M2 mutant 存活)→ 照 corr 版改
  `assert engine._resub_task is None` + 收斂後 pending 空 + task done;mutation 抽驗。
- 順帶:舊 repro.md「唯一缺的復原路徑」框架補 amendment 更正(P1-3 要求)。

**Out of scope**:tc4 `_ensure_connected` 無鎖 check-then-act race(P2-5,共用層
獨立 /mod);P2-2/P2-4(useStockNames,2026-08-11 已修畢);reconnect 掉 leaf 訂閱
的對帳(留 next-time);stock/corr/index 在 `_check_stale` 尾段蒸發下的各自復原
完整性(留 next-time)。

## 重現(loop-first)

真環境觸發源(REQ 為何逾時)上輪 8 次觀測未重現 — 機制層缺陷已由回溯審以實驗證實
(blocking fake source 實測 close() 0.000s 返回、事件序列 subscribe_enter →
source.close → subscribe_exit;M1/M2 subclass mutant 實跑全綠)。本輪重現 loop =
每 finding 一條 fake-source 紅測試(秒級、決定性),紅在 review 描述的具體症狀上:

| Finding | 紅測試(指令)| 紅的症狀 |
|---|---|---|
| P1-1 | `pytest tests/server/test_futures_engine.py -k bad_retry -q` | ValueError 殺死迴圈 → 永不復原;close() 重拋 → source.close 跳過 |
| P1-2 | `pytest tests/server/test_futures_engine.py -k refuses_after_close -q` | close 後 worker 照樣碰 source |
| P1-3 | `pytest tests/server/test_futures_engine.py -k reconnect -q` | engine 未接 on_reconnect → 掉訂品永久蒸發 |
| P2-1 | `pytest tests/server/test_futures_engine.py -k leaf_fed -q` | 重試成功後 `_leaf_fed` 殘留 → 跨日重複補 leaf |
| P2-3 | mutation 抽驗(M1 拿掉 start 守衛 / M2 while True)| 現斷言全綠 = 鎖無效 |

## Root cause

三洞同根:當輪(2026-08-03)把 pending-resub 當成「唯一缺的復原路徑」收工,
未對齊姊妹實作後續長出的三道防線 — corr 的 per-round 例外圍籬(C-3)、stock 的
`_EngineClosing` 縮窗、四引擎 on_reconnect 對帳。futures 是被照抄的原型,原型
沒有回補。

## 實驗記錄(紅→綠)

- **P1-1**:紅 2 條(`_BadRetrySource`:ValueError 殺迴圈 → TXF 永不復原逾時;
  `_AlwaysBadRetrySource`:close() 重拋 ValueError、src.closed False)
  `696dff59`(紅)→ `dc279b83`(修:_resub_round + except Exception 續行、
  close suppress 放寬)→ 綠。
- **P1-2**:紅 1 條(_EngineClosing/_retry_subscribe 不存在 ImportError)+
  既有 `attempts <= n+1` 允許值改鎖 `== n`(review 已標該變)
  `13510f05`(紅)→ `708509b7`(修:worker 縮窗)→ 綠。
- **P1-3**:紅 4 條(engine 未接 on_reconnect ×3;tc4 重掛失敗零 warning ×1)
  `5d32f19c`(紅)→ `ef3ffa62`(修:on_reconnect 全品對帳 + tc4 warning)→ 綠。
- **P2-1**:紅 1 條(`_leaf_fed` 殘留 `{'TMF','TXF'}`)
  `d427a2a3`(紅)→ `f16126af`(修:retry ok 即 discard)→ 綠。
- **P2-3**:lock 改寫 `3ab2081a`;mutation 抽驗 M1(拿掉 start 守衛)→
  test_all_success_no_retry_task 紅、M2(while True)→
  test_failed_products_retried_until_success 紅;Edit 還原後全綠,無 MUTANT 殘留。
- 全量 gate:pytest **2588 passed**(baseline 2580,+8)/ ruff clean /
  pyright 0 errors / `copycat validate` 42/42 PASS。

## 反向驗證

兩實作檔(futures_engine.py / tc4.py)checkout 回修復前快照(696dff59,等價
revert 全部五個 fix commit;紅測試保留)→ `pytest tests/server/test_futures_engine.py
tests/live/test_tc4.py` = **15 failed / 54 passed** —— 本輪全部紅測試與 lock
(P1-1×2 / P1-2 / P1-3×3+tc4 / P2-1 改寫 / C-2/C-3/C-4 / T-2/3/5/7 等)紅回,
bug 重現。`git restore --source=HEAD`(含 index)還原 → **69 passed** 綠回。
測試確實抓得住全部修復。
