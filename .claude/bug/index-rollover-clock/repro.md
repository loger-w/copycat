# Bug 2 — test_rollover_two_phase 時間相依

## 1. 重現

`repro_clock.py <hour>` 把 `copycat.server.index_engine` 模組的 `_dt` 換成固定時刻的 shim
後跑該測試(**注意**:腳本直跑時 `sys.path[0]` 是腳本目錄,`import copycat` 會被 venv 的
editable install 解析到主 tree — 腳本已顯式把 worktree root 插到 `sys.path` 最前面)。

修前:

| 注入時刻 | 結果 |
|---|---|
| 00:00 | **紅** `AssertionError: assert '2026-07-29' in ['2026-07-28']`(index_engine 275 行) |
| 08:00 | **紅** 同上 |
| 10:00 | 綠 |

即 08:30 門檻前一律紅。真實牆鐘 < 08:30 跑 gate 就會紅。

## 2. Root cause

`_rollover_loop`(`copycat/server/index_engine.py:279`)`now = _dt.datetime.now().time()`
判 08:30 門檻,該時鐘**沒有注入點** —— 同一個建構子已經注入了 `today_fn` 與
`in_watch_window`,唯獨漏它。

## 3. 修法(最小)

- 新增模組級 `now_time()`(= 真實牆鐘),建構子加 `now_fn: Callable[[], _dt.time] = now_time`。
- 279 行改 `now = self._now_fn()`。
- `tests/.../make_engine` 預設注入固定 10:00;另補 `test_rollover_gate_opens_at_0830`
  覆蓋門檻本身(原本無測試 —— 唯一的時鐘讀取沒有注入點,寫不出來)。

命名沿用 repo 既有慣例:`corr_engine` 的建構子已經有同名同形狀的 `now_fn`。

## 4. 驗證

- 注入 00 / 08 / 10 / 23 時皆綠(修前 00、08 紅)。
- `tests/server/test_index_engine.py` 15 passed。
- **Blast radius**:`IndexEngine(` 只有兩個呼叫點 —— `app.py:210` 不傳 `now_fn` → 走預設
  真實牆鐘,**prod 行為零改變**;另一個是測試。
- **反向驗證**:`git revert --no-commit <fix>` → 12 failed;還原 → 15 passed。
