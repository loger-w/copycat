# fix/dk-frozen-snapshot 驗證(2026-09-01)

## 自動化 gate(worktree C:\side-project\copycat-wt-dk-frozen-snapshot,commit cf9e1fa6 = review 收修後)

| Gate | 指令 | 結果 | Exit |
|---|---|---|---|
| pytest 全量 | `.venv\Scripts\python -m pytest -q` | 3266 passed, 1 skipped(3967fe54);收修後 3267 passed(受影響四檔 203 passed 先行核) | 0 |
| ruff | `.venv\Scripts\python -m ruff check copycat tests` | All checks passed! | 0 |
| pyright | `.venv\Scripts\python -m pyright` | 0 errors, 0 warnings | 0 |
| validate | `.venv\Scripts\python -m copycat validate` | 42/42 PASS(four/five replay 先跑;主 tree — 改動不觸 replay 鏈,data/ 只在主 tree) | 0 |

frontend 未動 → npm 系 gate 不適用。

## 紅先行 / 反向驗證

- 紅先行:e03ed9e6 時點 8 failed, 3 passed(TestDkWindowVariant ×2 檔 + TestFrozenRefetchSignal)。
- 修後:同組 11 passed;受影響三檔 123 passed。
- 反向驗證:`git stash push -- copycat/...` 還原修復 → 同組 **8 failed 紅回來** → `git stash pop` → 11 passed。
- 既有測試唯一紅:`test_only_the_1k_fallback_window_shrinks_and_only_for_small_n`(N024)——
  斷言「同 src 重查 DK 同窗」與新行為正面衝突,屬事前標記該變;改法 = 歸零序號取 variant 0,
  base 窗尺寸斷言逐字保留。

## 真實環境(TC4 15:50 session,TXF 夜盤)

1. **Phase 1 紅迴圈(修前病灶)**:`evidence/dk_frozen_probe.py` → `evidence/dk_frozen_probe_1.json`
   - W1 16:33:04 vs W2 16:35:34 同窗兩查:09-02 bar 逐字節同(v=7875)、elapsed 0.001s、重送 SUBQUOTE 回 Fail → **凍結(紅)**
   - V1 同時刻 start−1 日:v=8138 → variant 逃逸成立;U1 UNSUB 後同窗重訂:仍 v=7875 → UNSUB 不逃逸
2. **修後 end-to-end(worktree code 直連 TC4)**:`evidence/dk_fix_realenv.py` → `evidence/dk_fix_realenv_1.log`
   - fetch1 16:52:05 09-02 bar c=46818 v=9401;**同參數** fetch2 16:54:35 c=46863 v=9619 → **PASS**(頭部過濾同時斷言成立)
3. 未改功能抽查:1K 路徑窗字串不變(`test_1k_refetch_keeps_window`);全量 pytest 蓋其餘。

## 剩餘判準(prod 重啟後,交接 user / 次一交易日)

- 交易日 server 早上起、不重啟跨 14:00:14:00 後首刷 `/api/market/bars/TXF?tf=D` 末根 = 日盤收盤
  (09-01 15:02 FAIL 的那條)。
- 凍結若再現(TC4 行為變):`grep 值未前進` 命中 ——「**界前快照已含今日 bar**」的情形
  才蓋得到(pr-171-review F-04 限定):「今日 bar 整天缺席」型凍結(現貨 / 加權盤前
  開機建立的 key)此判準不鳴,症狀 = 當日 D bar 整天不出現,要靠看盤目視。


## 09-02 14:03 主場景第一次真實上演(排程 session 實錄)—— PASS,全案結案

- server 09:01:01 起(8e794d2d,含 #171/#172)、TC4 同 session 未重啟撐過 14:00;13:42 拍板
  安全窗全不動(墊背 / NK225M 延後),保本場景純淨。
- 14:03 首刷 `/api/market/bars/TXF?tf=D`:09-02 末根 `c 46189000` **= 1K 日盤 13:45 收盤
  `c 46189000` 逐字相等**(o 47201 / h 47343 = 夜盤+日盤全段,15:00 錨定口徑正確)。
  09-01 15:02 的病(凍在早上值)未再現 —— 修法主判準 PASS。
- `grep 值未前進` = **0 命中**(TC4 行為未變);`grep 墊背舊快照` = 0(TC4 開著,正確的零)。
