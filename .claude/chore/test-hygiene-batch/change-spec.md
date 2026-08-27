# copycat handoff — 2026-08-28:測試衛生三條合一支分支收掉(牆鐘 flake ×2 + 庫存報告列 fixture 去重)

新 session 目標:**一支分支**把 `docs/next-time.md` 2026-08-28 / 08-27 兩節裡三條「純測試層」留尾做完(user 2026-08-28 拍板
「統一一個分支就好」)。三條全與生產碼行為無關;都不需要真環境驗證。

## 0. 先讀什麼(不重抄,照路徑讀)

- `docs/next-time.md` 檔頭兩節:`## 2026-08-28(/pr-review #131 回溯 review 留尾)` 第 1 條(test_bars)、
  `## 2026-08-27(chore/pr-review-128-130-followups …)` 第 2 條(WS 順序型 flake)與第 3 條(`_BAL_3357`)。
- 樣板:`tests/capital/profit_rows.py`(pr-129 F-02 / #131 把損益列收成單一定義處的做法,docstring 有分工說明)、
  `tests/helpers/frontend_source.py`(helper 慣例:模組 docstring 講為什麼、raise 不 skip)。
- 專案 skills:`backend-conventions`(pytest + monkeypatch、不 unittest.mock)、`ops-discipline`(全量 vitest 與全量 pytest 不並跑)。
- memory:`~/.claude/projects/C--side-project-copycat/memory/pr-review-128-130-followups-shipped.md`(這三條怎麼被發現的)。

## 1. 環境現況(08-28 01:0x)

- master = `e600f341`(local = origin;含 next-time 拍板 (b) 那筆)。working tree 有他 session 未提交的 `.claude/skills/ops-discipline/SKILL.md`(+7 行)——
  **不要碰、不要 commit、rebase 用 `--autostash`**;`git add` **只點名檔案、不用目錄**(08-27 曾把他 session 的 untracked
  artifact 掃進 commit)。根目錄 `node_modules/` untracked,不動。
- 另一 session(`mod/futures-day-1500`,期貨 tab 15:00 起算)可能還在推 master:push 前 `git fetch` 重查,分岔就 `rebase --autostash`。
- prod 8721:user 08-28 開盤前會自己從 master 重起;本分支不需重啟。

## 2. 三條的精確位置與修法

### A. `tests/server/test_bars.py` 5 條在台北 00:00–00:10 會紅(牆鐘相依)

- 根因:`copycat/server/bars.py:510` `hold = hi == yesterday and _now_time() < MIDNIGHT_BUFFER_END`(`MIDNIGHT_BUFFER_END = 00:10`,:60)
  吃真牆鐘;該檔 `TestMidnightBuffer`(約 :585–:600)已 `monkeypatch.setattr(bars_mod, "_now_time", lambda: _dt.time(hh, mm))`,
  但下列 5 條沒凍結:
  `TestMinuteTwoTier::test_history_memoized_today_refetched` / `test_holiday_negative_cache_prevents_refetch` /
  `test_today_ttl_expiry_refetches_only_today`、`TestEmptyNegativeCache::test_today_empty_with_nonempty_history_still_short_cached` /
  `test_today_empty_short_ttl_expires`。
- **重現(不用等半夜)**:寫一個 plugin 檔 `freeze_0005.py`(內容 `import copycat.server.bars as bars; bars._now_time = lambda: _dt.time(0, 5)`),
  `PYTHONPATH=<dir> .venv\Scripts\python -m pytest -q tests/server/test_bars.py -p freeze_0005` → `5 failed, 46 passed`(08-28 00:5x 實跑)。
  這就是紅先行:**先把這個重現固化成測試層機制**,再修。
- 修法(擇一,建議第一個):(1) 該檔加 autouse fixture 把 `bars._now_time` 凍到 09:00,`TestMidnightBuffer` 自己覆寫;
  (2) 5 條各自 monkeypatch。修完用同一個 plugin 重跑 → 51 passed 才算。**不准**改 `bars.py`(那是行為,午夜緩衝是 TZ-2 設計)。

### B. `tests/server/test_index_routes.py::TestIndexState::test_ws_streams_index_payload` 順序型 flake

- 現況(:70–:88):`websocket_connect("/ws/index")` 後立刻 `fake.on_message(quote)`,再 `ws.receive_json()` 斷 `twse.p == 42_039_920`。
  `/ws/index` 連上時先送**初始快照**(`twse.p` None);quote 廣播若排在快照之後,首則就是快照 → `assert None == 42039920`。
  08-27 全量 1/3135 紅、單跑 1 紅 5 綠、整檔綠。
- 修法(擇一):(1) 先 `receive_json()` 吃掉初始快照、斷它是 `type == "index"` 且 `p is None`,再送 quote、再收一則;
  (2) 迴圈收到含 `p` 的那則為止(上限 2 則)。(1) 語意更清楚(順便釘「連上先送快照」這個契約)。
- 紅先行怎麼做:這條是 race,無法確定性變紅;以「連跑 20 次」當證據(`for i in 1..20: pytest -q <nodeid>`,修前至少 1 紅、修後 20 綠)。

### C. `tests/capital/test_client.py` 庫存報告列(19 欄)散裝複本

- `_BAL_3357`(:1467)與 `tests/capital/test_balance.py::RAW_C_MARGIN`(:69)逐字相同;`_BAL_2493`(:1468)= `RAW_T_BOUGHT`(:65);
  另有**同一字串直接內嵌** 10 處(:1077 / :1103 / :1124 / :1189 / :1217 / :1240 / :1298 / :1318 / :1331 / :1345,
  `grep -n '"3357,C,2000,1944' tests/capital/test_client.py`)。群益改欄形只改到一份、其餘靜默留舊欄形 —— 與 pr-119 F-05 / pr-129 F-02 同坑。
- 修法:比照 `profit_rows.py` 開 `tests/capital/balance_rows.py`(或併進 `profit_rows.py` 改名 `capital_rows.py`,你決定;獨立檔比較不會讓
  docstring 變兩段),收 `RAW_T_BOUGHT` / `RAW_T_FLAT` / `RAW_C_MARGIN` / `RAW_L_SHORT` / `RAW_END`(test_balance :65–:73),
  test_balance 與 test_client 都改 import;test_client 的 `_BAL_*` 與 10 處內嵌全部換成常數。
  搬移後用 python 逐 byte 比對(pr-129 4.3b 手法)寫進 verification。純 🔵,**斷言一條都不動**。

## 3. 分支與 commit 分組

分支名建議 `chore/test-hygiene-batch`(走 `/chore`;白名單 = 生產碼零 diff,`git diff master --stat -- copycat/` 必為空)。

- `test(server)`:A 的 plugin 重現固化(若採 autouse fixture,紅先行 = 先加一條「00:05 下五條要綠」的 parametrize,現況紅)。
- 🔵 `refactor(tests)`:A 凍結 / B 改收快照 / C fixture 去重 —— 三件可分三筆或合一筆,但**不要跟 test 紅先行那筆混**。
- chore:`docs/next-time.md` 勾掉三條 + artifact(`.claude/chore/test-hygiene-batch/verification.md` + `code-review-round-1.json`)。

## 4. 收尾 gate

`pytest -q` 全量(3135+;**不要**在台北 00:00–00:10 跑,除非 A 已修)、`ruff check copycat tests`、`pyright`、`copycat validate` 不需(未動 replay);
不動 frontend/ 就不跑 vitest。two-axis review dispatch 顯式 `model=opus`;PR merge `--rebase --delete-branch`。

## 5. 不在本分支、但 user 拍板中

- artifact 引 rebase 前 SHA 的處置:**user 2026-08-28 已拍板 (b)** —— artifact 不引 SHA,改引「第 n 筆 + commit subject」。
  本分支的 verification / review JSON **直接用 (b) 寫法當首例**(例:「第 1 筆 `test(server): …`」);harness(`branch-lifecycle` 收尾節)
  改動仍攢批、本分支不動 `~/.claude/`。

## Suggested skills(Skill tool)

`chore`(入口;三條都是「補測試 / 不改實作」)、`branch-lifecycle`(開工 / 收尾)、`tdd`(A 的紅先行)、`backend-conventions`、
`code-review-two-axis`、`receiving-code-review`、`auto-verify`、`verification-before-completion`、`ops-discipline`(全量 pytest 時段與並跑紀律)。
