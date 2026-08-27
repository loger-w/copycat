# chore/test-hygiene-batch — verification

主 tree 直做;branch 自 master 第 0 筆「chore(docs): next-time —— artifact 引 SHA 處置 user 拍板 (b) …」開。
來源 = `docs/next-time.md` 2026-08-28 / 08-27 兩節三條純測試層留尾(handoff 全文見同目錄 `change-spec.md`)。
**本檔依 user 2026-08-28 拍板 (b) 不引分支 SHA,commit 以「第 n 筆 + subject」指認**(rebase merge 後順序與標題不變);
是 (b) 寫法的首例。

## 0. 白名單(handoff §3:生產碼零 diff、斷言語意不變)

| # | 項目 | 證據 | 結果 |
|---|---|---|---|
| 1 | `copycat/` 零 diff | `git diff master --stat -- copycat/` → 空 | PASS |
| 2 | A 不改 `bars.py` | 同上;`MIDNIGHT_BUFFER_END` / `_now_time` 未動 | PASS |
| 3 | C 搬移逐 byte 相同 | python 取 `git show master:tests/capital/test_balance.py` 五常數、`test_client.py` 的 `_BAL_3357` / `_BAL_2493` 與內嵌 13 處字面(含 def)逐一 `==` `balance_rows` → 五常數 True(69 / 69 / 78 / 75 / 52 bytes)、`_BAL_3357 == RAW_C_MARGIN` True、`_BAL_2493 == RAW_T_BOUGHT` True、內嵌 13/13 True;`ALL BYTE-EQUAL: True` | PASS |
| 4 | C 斷言一條都不動 | `git diff master -U0 -- tests/capital/test_client.py` 的每個 `-` 行 = 字面 / `_BAL_` def / 多行呼叫的開括號與閉括號;`test_balance.py` 只刪五個定義 + 加 import | PASS |
| 5 | 不順手重排既存格式 | 第一次 `ruff format` 誤把 test_client 既有行(`apply_reply` / `pytest.raises` / `set_positions`)一起重排 → `git checkout master -- test_client.py` 後重跑同一支確定性替換腳本還原,diff 回到 63 行;`balance_rows.py` 是新檔,format 結果保留 | PASS(事故見 §6) |

## 1. A:`test_bars.py` 牆鐘相依(紅先行)

- **重現(修前,不等半夜)**:plugin `evidence/freeze_0005.py`(`bars._now_time = lambda: time(0, 5)`)
  `PYTHONPATH=<evidence> pytest -q tests/server/test_bars.py -p freeze_0005` → **`5 failed, 46 passed`**,紅的正是 handoff 點名的五條
  (`TestMinuteTwoTier` ×3 + `TestEmptyNegativeCache` ×2),失敗形狀 `assert [] == hist + cur`(00:05 緩衝窗內 yesterday 不永久化 → 歷史段重抓)。
- **紅先行固化(第 1 筆 `test(server): test_bars 哨兵 …`)**:`TestModuleClock::test_default_clock_is_frozen_outside_midnight_buffer`
  斷 `bars_mod._now_time() == _DAYTIME` 且 `_DAYTIME >= MIDNIGHT_BUFFER_END`。裸跑 → **`1 failed, 51 passed`**(讀到真牆鐘,恆紅、不只半夜)。
  沒照 handoff 的「00:05 下五條要綠」parametrize:五條的期望本來就是白天語意,要它們在 00:05 綠等於要緩衝窗失效;哨兵在 fixture 缺席時恆紅,比只在半夜紅更早報警。
- **修(第 2 筆 `fix(tests): test_bars 模組級 autouse 凍 09:00 …`)**:模組級 `@pytest.fixture(autouse=True) _daytime_clock` monkeypatch `bars_mod._now_time` → `_DAYTIME`(09:00);
  `TestMidnightMemoRace._freeze` 在 fixture 之後再 setattr,自然覆寫(五條緩衝窗測試不動)。
  裸跑 **`52 passed`**;同一 plugin 重跑 **`52 passed`**(plugin 在 import 期改模組屬性,fixture 每條測試再覆寫 → plugin 失效 = 本檔不再吃任何外部時刻)。
- 沒放 `tests/server/conftest.py`:root conftest docstring(2026-08-20 實證)記子目錄 conftest 的 autouse 會被 `-p` / 收集邊界靜默丟失;只有本檔需要,放模組內最窄。

## 2. B:`test_ws_streams_index_payload` 順序型 flake

- **前提校正**:handoff 寫「`/ws/index` 連上時先送初始快照」。核 `app.py::ws_index` → `relay(websocket, index.stream())`,`index.stream()` = `WsBroadcaster.stream()` **無 seed**;
  relay docstring 亦寫「無 seed 的路(index/capital/futures)首則可能是 ping」。搶在 quote 前的其實是 `_broadcast_loop`(throttle 10 ms)任一 dirty 拍
  (回補完成 / MIS poll / `_swap_day` 撥 `_dirty`)發的 `_payload()`;常態下 quote 先被 `_handle_quote` 處理(它自己撥 dirty),首則就含 `p`。
  → handoff 修法 (1)「先 receive 吃掉快照」在常態會把 quote 那則誤當快照、斷 `p is None` 反而紅;採 (2) 有界迴圈。
- **重現(修前)**:單跑 20 次全綠(race 只在負載下露臉);改用 plugin `evidence/race_index_ws.py` 固定序(`stream()` 回傳後撥 `_dirty=True` 模擬連上那拍有待發 payload;
  `on_message` 延 50 ms 讓 loop 先發)→ **3/3 `1 failed`**,`assert None == 42039920`,與 08-27 全量那次同形。
- **修(第 3 筆 `fix(tests): test_ws_streams_index_payload 改收到含 p 的那則為止 …`)**:`for _ in range(_WS_PRE_QUOTE_MAX + 1)` 收到 `twse.p` 非 None 即 break,
  每則仍斷 `type == "index"`,尾斷 `seen[-1] == 42_039_920`(失敗訊息列出前 n 則 `p`)。上限取 5 而非 handoff 的 2:前置拍理論上 ≤ 2(回補 + MIS),
  留餘裕不影響語意 —— 超過 5 則仍是 None = 推播鏈真的壞了,不是順序問題。
  同 plugin 重跑 **3/3 `1 passed`**;整檔 `11 passed`;修後裸跑 20 次:見 §5。

## 3. C:庫存報告列 fixture 去重(🔵,第 4 筆 `refactor(tests): 庫存報告列 19 欄收進 tests/capital/balance_rows.py …`)

- 新檔 `tests/capital/balance_rows.py`:`RAW_T_BOUGHT` / `RAW_T_FLAT` / `RAW_C_MARGIN` / `RAW_L_SHORT` / `RAW_END`,docstring 比照 `profit_rows.py`
  (欄位語意 + 為什麼收成一處)。`test_balance.py` 刪五定義改 import;`test_client.py` 內嵌 **12 處**(多行呼叫形 6 + 單行 6)+ `_BAL_3357` 8 引用 +
  `_BAL_2493` 3 引用全換 `RAW_C_MARGIN` / `RAW_T_BOUGHT`,兩個 `_BAL_*` def 刪。殘留 grep(`3357,C,2000,1944` / `2493,T,0,0,0,0,0,1000` / `_BAL_`)兩檔 0。
  handoff 寫「10 處內嵌」,實數 12(next-time 原文寫 12,以 grep 為準)。
- `tests/capital` **`403 passed`**;byte 比對見 §0 #3。
- 沒動 `test_balance.py` 六處 `RAW_*.replace(…)` 字串變異(scope:純搬移),記 next-time 本輪節(候選 `balance_variant`)。
- review S-1 抓到第三份:`test_fill_latency.py::_BAL_ROW`(`3357,T,2000,1944,…`,kind T 帶資額度數字的合成列,我的 grep 只找 `3357,C` 漏掉)。
  第 6 筆原樣搬入 `RAW_T_HELD`(vs master `_BAL_ROW` IDENTICAL,78 bytes);**不改引 `RAW_C_MARGIN`** —— 那會把種類 T→C,與同檔 `pnl_variant(…現股)` 對不上。三檔殘留 grep 0。

## 4. Commit 分組(handoff §3)

| 第 n 筆 | type | 內容 |
|---|---|---|
| 1 | `test(server)` | A 哨兵(紅先行) |
| 2 | `fix(tests)` | A autouse fixture |
| 3 | `fix(tests)` | B 有界迴圈 + `_WS_PRE_QUOTE_MAX` |
| 4 | `refactor(tests)` | C `balance_rows.py` 搬移 |
| 5 | `chore(docs)` | next-time 勾三條 + 本輪留尾兩條 |
| 6 | `refactor(tests)` | review S-1 / S-5 / S-2:`RAW_T_HELD` + docstring 引 balance.py + import 序 |
| 7 | `fix(tests)` | review P-3 / S-3:ping 不計入上限、上限註解改語意 |
| 8 | `test(server)` | review S-4:哨兵補 `build_minute` 真路徑一條 |
| 9 | `chore(docs)` | review S-8 / P-4:next-time 勾銷改 `~~原文~~ → 結論` 形 |
| 10 | `chore(chore-test-hygiene-batch)` | artifacts(本檔 / change-spec / review JSON / evidence 兩支 plugin) |

紅先行那筆(1)獨立;A / B 用 `fix(tests)`(改的是測試自身的錯誤行為:吃牆鐘 / 吃順序),C 純搬移用 `refactor`。

## 5. 自動化 gate(handoff §4)

- `pytest -q` 全量:**`3136 passed`**(190.8 s;= master 3135 + 哨兵 1),exit 0;HEAD 第 5 筆
- `ruff check copycat tests`:All checks passed!(第 4 筆後 + 收修後各一次)
- `pyright`:0 errors, 0 warnings, exit 0
- `copycat validate`:未跑(未動 replay,handoff §4 明示不需)。frontend 未動,vitest 不跑。
- B 修後裸跑 20 次:**20/20 `1 passed`**(0.38–1.07 s)
- 跑的時段:2026-08-28 01:05–01:08(不在台北 00:00–00:10;A 修後也不再相依)。
- **收修後(第 9 筆)重跑**:`pytest -q` **`3137 passed`**(188.9 s;3135 + 哨兵 2)exit 0;`pyright` 0 errors exit 0;`ruff check copycat tests` PASS;時段 01:15–01:18。

## 6. 事故 / 教訓

- `ruff format --check -`(stdin)對 master 版 test_client 判讀成「已 format」是錯的 —— 隨後 `ruff format test_client.py` 把三處既有行一起重排。
  發現於 `--diff` 輸出含非本輪 hunk;處置 = `git checkout master -- <file>` + 重跑確定性替換腳本(產出與第一次逐行相同),不再 format。
  教訓:判「既有檔是否 formatted」用 `git show master:<file> > tmp && ruff format --check tmp`,不用 stdin `-`;或乾脆只對**新檔** format。
- handoff 的前提(B「初始快照」)要自己核 code 再選修法 —— 兩個候選只有一個在常態不會反紅。

## 7. Two-axis review(round 1,fixed point = merge-base 第 0 筆;兩軸 opus)

- **Standards 8 條(1 P2 + 7 P3)**:S-1 `test_fill_latency._BAL_ROW` 第三份未收(P2)/ S-2 import 序 / S-3 上限 5 過寬 / S-4 哨兵不碰 `build_minute` /
  S-5 docstring 欄位語意與 balance.py 不同源 / S-6 命名族不一致 / S-7 紅綠 scope 不一 / S-8 next-time 勾銷形。**5 fixed、2 declined(S-3 / S-6,理由見 JSON)、1 accepted(S-7,不重寫歷史)**。
  白名單三項 reviewer 自核 PASS(含 test_client 每個 `-` 行無順手重排)。
- **Spec 4 條(1 P2 + 3 P3)**:P-1 artifact 未落檔(P2;= 第 10 筆)/ P-2 `fix(tests)` vs handoff `refactor` / P-3 迴圈不容 ping / P-4 留尾措辭。**3 fixed、1 accepted(P-2)**。
  PASS 表:§2.A / §2.B / §2.C / 白名單 1–3 全 PASS(reviewer 自跑 AST 比對與全量 pytest);§3 commit 分組「部分」→ P-1 / P-2 收修後 PASS。
- **兩軸對兩處刻意偏離 handoff 的判定一致**:B「初始快照」前提為假(Spec 軸核 `app.py:1885` / `index_engine.py:767` / `ws.py:61`)→ 修法 (1) 不採;
  A 哨兵比 parametrize 強(`_now_time` 帶微秒恆不等 → fixture 缺席全天恆紅)。
- **兩軸唯一相左 = B 上限**(Standards 要收 2、Spec 核 `_dirty` 撥點 >2 認 5 合理):採 Spec 的實證,值不動、註解改成「只防無界等待,不是契約」(第 7 筆)。
- 收修 commit:第 6–9 筆(🔵 / fix / test / chore 各一,依 F-04 慣例新增斷言另拆 `test`)。增量由主 agent 機械快篩(467 passed + 兩支 plugin 重跑 + ruff)+ 全量重跑(§5)。JSON:`code-review-round-1.json`。

## 8. 需 user 知情

- 本分支不動生產碼、不需重啟 prod;prod 8721 仍應由 user 從 master 重起(handoff §1)。
- handoff §5 的 SHA dangling 處置已拍板 (b),本檔即首例;`branch-lifecycle` / `closeout.md` 的格式一行仍攢批未動 `~/.claude/`。
