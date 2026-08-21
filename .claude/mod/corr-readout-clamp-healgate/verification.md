# verification — mod/corr-readout-clamp-healgate(R5)
## 自動化(2026-08-21 18:0x)
| pytest -q | 2833 passed(baseline 2807 → +26)| ruff | All checks passed | pyright | 0 | copycat validate | 42/42 PASS |
| vitest | 136 files / 2489 passed(+1)| tsc 0 | eslint 0 | react-doctor No issues |
## SC
- SC-1 B7:RiverPanel.test 三腿治具 `道瓊 —` 進讀值列、polyline 2、svg 無道瓊、順序 = entries(含空腿在中)、未勾選腿不進讀值列 PASS。
- SC-2 B8:825→826 覆寫、827 起不覆寫(rank 2 邊界)、delta 不帶丟棄值、end 空照寫、夜盤 1740→302、換場後守門、回補留尾 characterization PASS。
- SC-3 B9:週六 01:00 True / 週一 01:00 False / 假日次晨 False / 10:00 既有語意;TXO 05:00:00 True / 05:00:30 False;期貨 05:05 True / 05:06 False(拆腿);05:59 / 06:00 門檻 PASS。
- SC-4 真環境:merge 後重啟 8721 → health sha + 探針三量(見收尾回報);真窗口 08-22 / 08-25 凌晨,不以無 log 判 PASS。前端 B7 過目待 user。
## 白名單 W1 buildOverlayGeometry 未動 / W2 offset_of 全域逐點 0 差異、apply_backfill 未動 / W3 _heal_gate(None) 同物件、_today 六處未動 / W4 其餘工廠接線測試綠。
抽 2 未改:tests/server/test_corr_engine 綠;RiverPanel.memo.test 綠。
## Migration 無。self_review_head = 8c73e939
