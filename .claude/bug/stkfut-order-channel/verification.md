# verification — stkfut-order-channel

分支:`fix/stkfut-order-channel`(4 commits on f9fff6a0)
執行環境:worktree + 主 tree venv(cwd 釘 worktree;模組路徑錨點已驗)

## Phase 6|自動化 gate(主 session 親跑,非轉錄 implementer 回報)

| gate | 指令 | 結果 | exit |
|---|---|---|---|
| pytest | `.venv python -m pytest -q` | 2407 passed, 1 skipped | 0 |
| ruff | `ruff check copycat tests` | All checks passed! | 0 |
| pyright | `pyright` | 0 errors, 0 warnings | 0 |
| replay×2 | `copycat replay --data-dir <主tree>/data --watchlist four/five_tigers` | 兩份完成(11048 events) | 0 |
| validate | `copycat validate`(對本輪新產物) | 42/42 PASS | 0 |

- 註 1:第一次全套件跑到 `test_index_routes.py::test_ws_streams_index_payload` 紅
  (`twse.p == None`)—— 與本 diff(僅 capital 5 檔)零關聯;單檔重跑綠、
  全套件重跑綠(2407 passed)。判定 flake,記 next-time(ws flake 家族新樣本)。
- 註 2:worktree 無 `data/`,replay 以 `--data-dir` 指主 tree 種子(唯讀),
  產物寫 worktree `out/`,validate 是對本分支 code 的全新產物。

## Phase 7|真實環境驗證(側車 server,零 TC4/ZMQ/真憑證)

harness:scratchpad `capital_side_server.py`(FakeCom + FakeQuoteSource +
`neutralize_external_env()`,port 8899,對映表用版控真檔 stkfut_map.json)。
curl 全文:`evidence/curl-transcript.txt`。

| 情境 | 結果 |
|---|---|
| C-1 happy:POST order/future CDF 202609 limit 1180 | 200;`/debug/com-sent` 記 `('future', {...bstrStockNo:'CDFI6'...}, **False**)` — 走期貨通道 |
| C-2 E1:CDFI6 活單改價 1180.5(1000元段 tick=5) | **400 BAD_TICK**,COM 未收到 |
| C-2 H1:同單改 1185.0 | 200,COM 收到 '1185' |
| C-2 E2:store 查無 seq(R3 逃生口) | 200 放行(斷線仍能刪改單) |
| C-2 E3:TXFI6(指數期)改 23000.37 | 200 放行(scope 限個股期) |
| regression:證券送單 / GET orders | 200 / 200,欄位正常 |

/bug 特有:Phase 1 重現步驟重走 —— `is_option_contract`:CDFI6/QFFI6/TXFI6 →
False、TXO20000I6/TX422000T6 → True、SXFI6(未知純字母)→ False。原重現
(CDF → is_option=True)已消滅。

## Phase 8|反向驗證

見 repro.md 附錄(revert 後紅測試紅回、restore 後綠回)。
