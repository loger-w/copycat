# Phase 1 現況表 — index-board(改動前的樣子)

> 事後重建的精簡版(見 `HANDOFF.md`)。原檔含完整 caller map;此處只留改完之後仍有參考價值的部分。

## Baseline(改動前)

| 項目 | 結果 |
|---|---|
| `pytest -q` | 1368 passed, 1 skipped(47.78s) |
| `npm test -- --run` | 61 檔 / 643 tests(9.64s) |

worktree 依賴依 CLAUDE.md §8 用**複製**(非 junction):`npm ci` 重建 node_modules、
`Copy-Item -Recurse` 複製 `spikes/TCPY`。

## 改動前的 Tab 與大盤頁

- Tab:`TXO 綜合損益 / 個股 / 期貨 / 指數 / 相關係數`,預設 `txo`
- 指數頁:`並排`(加權 / 櫃買兩張卡,分時折線)與 `重疊`(相對昨收 % 疊線)兩模式;
  台指期只有一個純量價 + 對加權價差,**無小台/微台切換、無 K 線**

## Bug 根因(靜態確認,`docs/next-time.md` 2026-07-29 已記為既有 bug)

```python
# copycat/live/aggregate.py:21
_SPOT_PREFIX = "TC.F."          # 整棵期貨樹前綴
def route(self, tick):
    if tick.symbol.startswith(_SPOT_PREFIX):
        self.spot_millipts = tick.price_millipts   # 任何 TC.F.* 都被當成台指現價
        return
```

TXO runtime 的 ZMQ SUB 訂 `""`(收全部推播)→ **同 process 其他引擎訂的所有期貨 tick 都會流進來**:

| 來源引擎 | symbol | 量級 |
|---|---|---|
| `futures_engine` | `TC.F.TWF.{TXF,MXF,TMF}.HOT` + leaf | ≈ 41000 |
| `corr_engine`(六腿) | `TC.F.CME.{YM,ES,NQ}.HOT`、`TC.F.TWF.SXF.HOT`、`TC.F.SGX.TWN.HOT` | YM ≈ 44000 |
| `stock_engine`(期現對照) | 個股期 `TC.F.TWF.<兩碼+F>.HOT`(2317→DHF) | ≈ 232.5 |

`spot_millipts` 被輪流覆寫 = 右上角「台指」亂跳;同一個值也是 `aggregate.py` `spot_pnl` 的輸入
→ **選擇權頁的現貨損益點位一併錯**(user 描述「包含選擇權那邊也是」)。
`live/models.py` `parse_realtime` 另有 `TC.F.` 前綴的零成交量放行特例,放大覆寫頻率。

**正解 symbol**:`models.SPOT_SYMBOL = "TC.F.TWF.TXF.HOT"`(`engine.py` 訂閱用的就是它)。
TC4 REALTIME 的 `Symbol` 欄原樣回訂閱字串(含 `.HOT`)—— 證據:`corr_engine` 以
`_by_symbol[quote["Symbol"]]` 精確比對,六腿 2026-07-30 日盤實證全部命中。

## 當時的硬限制(進 spec 前已確認)

1. **櫃買指數不在 TC4 symbol 樹**(CLAUDE.md §8 掃盡確認)→ 無任何歷史來源,唯一來源是 TWSE MIS 5 秒快照
2. **TC4 無 WK / MK DataType**(官方 wrapper 只有 TICKS/1K/DK)→ 週/月 K 必須由日 K 聚合
3. **`TC.F.TWF.TXF.HOT` 的歷史只能從 futures session 問**(本輪把它升為通則 W-12,加權同理)
4. **user 拍板行情資料一律走達錢 4**(MIS 為 index-board 既有例外)
5. `aggregateBars` 桶界對齊 09:00 原點且跨日不合併
