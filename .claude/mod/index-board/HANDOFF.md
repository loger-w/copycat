# index-board 收尾記錄(2026-07-30)

**已 merge 進 master `c409cb1`**(17 commits;離線 fallback local ff-merge,repo 無 remote)。
分支 `mod/index-board` 已刪、worktree 已移除、主 tree 依賴完好(TCPY 17 檔 / node_modules 193 項)。

> ⚠ **本目錄是事後重建的**:原始 artifact 寫在 worktree 內的 `.claude/mod/index-board/`,
> 而 `.claude/` 是 gitignored → `git worktree remove` 連同刪除,從未進版控。內容依對話記錄
> 重建,決策與 finding 齊全,逐字排版可能與原檔略有出入。教訓已寫進 CLAUDE.md §8。

## 三件事

| # | 需求(user 原話) | 結果 |
|---|---|---|
| 1 | tab 順序改為 大盤、個股(期)、選擇權 | SC-1 ✅ |
| 2 | 大盤頁可看 加權 / 櫃買 / 指數三選一 + K 線 1~10/30/60/90 分、日/週/月 | SC-2~SC-7 ✅(櫃買日/週/月為平台硬限制,誠實拒繪) |
| 3 | 右上角指數一直亂跳(選擇權頁同樣) | SC-8 ✅ 根因修畢 + 夜盤實證 |

## 驗證證據

| gate | 結果 |
|---|---|
| `pytest -q` | **1451 passed**(baseline 1368,新增 83 條) |
| `ruff check copycat tests` | All checks passed |
| `pyright` | 0 errors |
| `copycat validate` | 42/42 PASS |
| `npm test -- --run` | **64 檔 / 744 tests**(baseline 61 檔 / 643) |
| `npx tsc -b` / `npx eslint src` / `npm run build` | 全通過 |
| `check_feat_tags.py` | PASS(flow=mod, commits=17) |

### 真實環境(2026-07-30 夜盤,達錢 4 開啟;server port 8731)

| 端點 | bars | source | volume | partial | 冷載入 |
|---|---|---|---|---|---|
| `TWSE?tf=D` | 748(2023-07-03~) | tc4_dk | false | true | 0.022s |
| `TWSE?tf=W` | 159 | tc4_dk | false | true | — |
| `TWSE?tf=M` | 37 | tc4_dk | false | true | — |
| `TWSE?tf=1&days=5` | 1080 / 4 交易日 | tc4_1k | false | — | 0.33s |
| `TXF?tf=D` | 1213(2021-08-02~) | tc4_dk | true | false | 0.026s |
| `TXF?tf=1&days=2` | 600,首根 `08:46`、末根 `13:45` | tc4_1k | true | true | 0.036s |
| `MXF?tf=D` | 1213 | tc4_dk | true | — | — |
| `OTC?tf=D/W/M` | 0 + `refusal=NO_HISTORICAL_SOURCE` | none | — | false | — |
| `OTC?tf=1` | 本機合成 | mis_poll_synth | false | — | — |
| `2330?tf=D` / `TWSE?tf=5` | 400 `BAD_KEY` / `BAD_TF` | — | — | — | — |

**SC-8 反覆量測**(夜盤,corr 六腿 + futures 三檔 + 個股期同時推播):

| 時刻 | IndexBar 台指 | 期貨 tab TXF | TXO spot | 差距 | dropped_foreign |
|---|---|---|---|---|---|
| 22:28 | 41750.0 | 41749.0 | 41750.0 | 1.0 點 | 4057 |
| 22:5x | 41683.0 | 41683.0 | 41683.0 | **0.0 點** | 1350 |

截圖:`docs/specs/index-board/screenshots/`(01 分時 / 02 加權日K / 03 櫃買 disabled / 04 期指 1分K)。

## 待辦(已寫進 docs/next-time.md)

- **UI 對照過目未做**(user 驗收項)。截圖為 rebase 前拍;rebase 後 K 線多了 stock-ui-round5 的
  「視窗高低標」(加法)
- 期指分時走勢、期指夜盤 K 線、櫃買永久歷史庫存、`/api/market/diag`
- 盤後「加權」現價顯示 `-`(既有行為)、期指高/低顯示 `-`(引擎 payload 無該欄位)
- `MARKET_KEYS`(後端)與 `MarketKey`(前端)兩份手動同步的值域

## Review 兩輪

- **spec 階段**(`change-spec-reviewer`):3×P0 / 9×P1 / 7×P2 —— **全數 accepted**,見 `change-spec-review-round-1.json`
- **Phase 5 code review**(medium,雙焦點含白名單對照):6×P1 / 1×P2 彙總,**無 P0** —— 全數 accepted,見 `code-review-round-1.json`
- `self_review_head`: `45bbecf`(rebase 前;rebase 後對應 `01c5f24`)
