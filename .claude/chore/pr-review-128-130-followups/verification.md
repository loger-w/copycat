# chore/pr-review-128-130-followups — verification

主 tree 直做;branch 自 master `c37e0401` 開。來源 = `docs/superpowers/specs/pr-128-review.md`(6)/ `pr-129-review.md`(8)/
`pr-130-review.md`(8)共 22 條 finding,全 Nice to Have、零 Must / Should;handoff 見同目錄 `change-spec.md`。
三條 ask-user(#128 F-06 / #129 F-02 / #129 F-05)user 2026-08-27 深夜開場一次拍板**全做**。

## 1. 唯一行為改動(#130 F-01;紅先行)

- `8e25d87a` test:`TestLoadConfig::test_bad_sparse_flag_is_not_reported_when_the_whole_file_is_discarded`
  (parametrize:後面腿缺欄 / base 不在 legs)。紅:`2 failed, 20 deselected` —— log 先出「NQ 的 sparse 非 true/false…旗標無效」
  再出「改用預設腿」,正是 finding 描述的誤導組合。
- `ee916937` fix:`_parse_legs(raw, bad_sparse)` 以輸出參數蒐集 `(key, 原值)`,`load_config` 過完 legs / base 兩道降級檢查
  **確定採用**後才印 WARNING。`test_corr_config.py` 22 passed;`(review S-3)` 尾綴隨「parser 內破例 log」的理由一起消失。
- 語意界線:採用設定檔的情況(既有 `test_sparse_flag_only_accepts_json_true…` 六腿 / null 腿)WARNING **照印**,訊息字面不變;
  只有整份被丟時不印(那時「改用預設腿」才是對的訊號)。

## 2. 行為不變的部分(🔵 / 🟢)

| commit | 類 | 內容 |
|---|---|---|
| `1f3fe386` | 🔵 | #129 F-02 `RAW_PNL_ROW` / `RAW_PNL_MARGIN` 收進 `profit_rows.py`(test_balance / test_client 改 import,`_PNL_3357` 刪);#129 F-03 哨兵 `[25]="3"` → `"9"` + `assert any("種類標籤未知" …)`;#129 F-04 模組 docstring 六份→七份、刪 155.63 因果句;#130 F-05 三條不看 sparse 的 wiring 測試改傳 `DEFAULT_CONFIG` |
| `d3d4b710` | 🔵 | #128 F-06 parity 測試搬 `tests/server/test_index_engine.py::test_watch_end_is_the_index_heal_gate_boundary`;`tests/live` 不再 import `copycat.server`(grep 0) |
| `1d2242f5` | 🔵 | #130 F-02 `app.py` / `verify.py` 的 `(review S-1)` 尾綴刪;#129 F-08 `types.ts` JSDoc 一行位移 |
| `4697b4da` | 🟢 test | #129 F-05 `tests/capital/test_models.py::test_avg_source_parity_with_frontend`(後端測試直讀 `types.ts::AVG_SOURCES` 字面比 `get_args(AvgSource)`,同 river palette 姿態) |
| `495de4a2` | chore | 14 條文件 / 註解 / artifact:#128 F-01~F-05、#129 F-01 / F-04 / F-06 / F-07、#130 F-03 / F-04 / F-06 / F-07 / F-08;CLAUDE.md §4 兩條改寫 + parity pin |
| `a58e37ee` | chore | next-time 記 `test_ws_streams_index_payload` 順序型 flake |

## 3. 反向 / 守門驗證(mutation 級;腳本 `try/finally` 還原,commit 前 `git status` 對照)

| 突變 | 結果 |
|---|---|
| M-a `balance._PNL_KIND_CODE` 補 `"9": "short"`(模擬日後補融券碼) | `test_profit_row_unknown_kind_skipped_keeps_previous_broker_avg` → `1 failed`(新斷言「種類標籤未知」擋住;舊哨兵 `"3"` 在同型情境不會紅 —— 正是 pr-129 F-03 的點) |
| M-b `types.ts` `AVG_SOURCES` 加 `"manual"` | `test_avg_source_parity_with_frontend` → `1 failed` |
| M-c(紅先行本身)`_parse_legs` 內即時印 WARNING | `test_bad_sparse_flag_is_not_reported…` → `2 failed` |

還原後 `git status` 只剩他 session 的 `.claude/skills/ops-discipline/SKILL.md`。

## 4. 白名單核對(handoff §3:三個 PR 行為逐 bit 不變,除 #130 F-01)

1. `load_config` 採用設定檔時的回傳值與 WARNING 字面不變 —— 既有 22 條 corr_config 測試全綠,PASS。
2. `_default_corr_source` prod caller 不動(app.py 只改一行註解),PASS。
3. `tc4.py` / `index_engine.py` / `stock_engine.py` / `store.py` / `client.py` 不在 diff,PASS。
4. 前端只動 `types.ts` 一行註解位移:`tsc -b` / eslint / vitest 2848 passed / react-doctor 0 issue,PASS。
5. 測試重組不改斷言語意:`_PNL_3357` → `RAW_PNL_MARGIN` 逐 byte 相同(pr-129 4.3b 已比對);哨兵改值 + 斷言只加不減,PASS。

## 5. 自動化 gate

- review 收修後 HEAD `1e3dfcbf`:`pytest -q` **`3135 passed`**(192 s);`ruff check` PASS;`pyright` 0。
- review 前 HEAD `a58e37ee`:`pytest -q`:`1 failed, 3134 passed`(195 s)。紅的是 `tests/server/test_index_routes.py::TestIndexState::test_ws_streams_index_payload`
  —— 單跑 1 紅 5 綠、整檔 11 passed;失敗形狀 `assert None == 42039920`(`/ws/index` 首則是初始快照而非 quote 後狀態),
  index routes / ws / engine 不在 diff → 順序型 flake,依 branch-lifecycle 規則記 next-time(`a58e37ee`)。
- `ruff check copycat tests` PASS;`pyright` 0 errors;`copycat validate` 42/42 PASS。
- frontend:vitest `152 files / 2848 passed`;`tsc -b` OK;`eslint src` OK;`react-doctor --scope changed` No issues。
- 全量 vitest 與全量 pytest **分開跑**(handoff §4 紀律)。

## 6. 事故 / 教訓

- `git add .claude/mod` 把他 session 未追蹤的 `.claude/mod/futures-day-1500/current-state.md` 掃進 chore commit;
  `git show --stat` 對照發現,`git rm --cached` + amend(commit 未推)還原為 untracked。教訓:多 session 並行時
  `git add` 只點名檔案、不用目錄;commit 後看 `--stat`。

## 7. Two-axis review(round 1,fixed point `c37e0401` → `a58e37ee`;兩軸 opus)

- Standards 7 條(1 P2 + 6 P3):S-1 next-time 原標題被蓋(P2)/ S-2 日期 / S-3 行長與簽名 / S-4 前端原始碼讀取重複 /
  S-5 輸出參數 + Primitive Obsession / S-6 `tail=None` 雙語意 / S-7 commit 分類(判斷題)。**6 fixed、1 accepted**。
- Spec 22/22 PASS(每條有 HEAD 落點,逐 byte / `git show` / 實數核過);另 4 條(1 P2 + 3 P3):P-1 CLAUDE.md sparse 句
  沒跟上 F-01(P2)/ P-2「分時自癒窗從這一點開始」不精確 / P-3 out-param / P-4 flake 條目超範圍。**4 fixed**。
- 收修 commit:`2bd63ccc`(🔵 `_ParsedLegs` NamedTuple、`tests/helpers/frontend_source.py`、parametrize 二元組)+
  `1e3dfcbf`(chore:next-time 標題還原 / 日期、CLAUDE.md 兩句、docstring、artifact)。增量由主 agent 機械快篩
  (130 passed + ruff / pyright 0)+ 全量 pytest 重跑(§5)。JSON:`code-review-round-1.json`。
- 教訓:用 `str.replace` 插新章節時 anchor 必須**含在 new 裡**再寫回(S-1 事故:anchor 是原標題,替換後標題消失)。

## 8. 需 user 過目 / 08-28 待驗

- #128 F-01 的「重掛 snapshot 讓現價欄回來」仍是**未實測**推論:08-28 13:36 `curl /api/index/state` 現價欄 vs 時戳核。
- 本輪無 UI 變更、prod 不需為此重啟;但 prod 8721 現為孤兒 SHA `f8232339`,明早開盤前應從 master 重起(handoff §1)。
