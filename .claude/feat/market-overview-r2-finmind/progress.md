# Progress ledger — market-overview-r2-finmind

Plan: `.claude/feat/market-overview-r2-finmind/implementation/PLAN.md`(v2)

依賴序:T1 獨立;T2 → T3;T4/T5 獨立;T6 依 T2-T5;T7 依 T1+T6;T8 依 T7;T9 依 T8;T10 隨時。

> 注:Phase 8 tag 機驗抓到 parity oracle commit 掛了無配對 [green],rebase reword 去 tag
> (5329d52 → e32c6ef;內容零差異,`git diff` 空)。**5329d52 之後的表列 sha 已全數位移**,
> 對照請以 `git log --grep` 訊息比對;review 結論不受影響(self_review_head 已更新)。

| Task | 狀態 | commit 範圍 | review gate |
|---|---|---|---|
| T1 finmind_token 抽出(🔵) | done | 9e892a9 | PASS(scope 5 檔 / tag ✓ / 26+全套綠;唯一紅 = 既有 ws_disconnect flake) |
| T2 market.py 毫元 limit | done | d201be6..d349cd6 | PASS(red→green 配對 ✓ / 9 passed / pyright 0) |
| T3 market_breadth 純函式 | done | 280356c..5329d52 | PASS(28 passed / parity oracle 盤中錄製 limit 桶 21↑3↓ / pyright 0)。發現:stock_info 實錄 4300 列 → R14 門檻 5000 誤估,已改 3000(PLAN/design 同步) |
| T4 breadth_config | done | fdf041c..1988d61 | PASS(6 passed) |
| T5 breadth_fetch | done | 6e5fc4c..2710007 | PASS(11 passed / query+Bearer 斷言 / pyright 0) |
| T6 breadth_engine | done | ef05fef..1f155c6 | PASS(26 passed / 全套 2122 / pyright 0)。偏離 3 點已記 commit body(_monotonic 縫 / TTL 斷言修正 / 空 stock_info 視同失敗) |
| T7 app 接線 | done | 2b8c475..5d06225 | PASS(12 passed / 全套 2128 / pyright 0)。偏離:--verify 落檔隔離 data/market-verify/(好判斷,防 fake 污染 prod 檔;test_main_wiring 鎖住) |
| T8 型別 + useBreadth | done | 9b399e2..56a8a20 | PASS(全套 1384 / tsc 0 / vacuity check 過) |
| T9 前端元件 + 版面 | done | 9ddf8fe..82b2ec1 | PASS(全套 1406 / tsc 0 / eslint 0;偏離 2 項合理:fill-* SVG 正寫、跟既有不用 useContainerSize) |
| T10 文件債 | done | bb22743 | PASS(grep 三驗全中,只動 CLAUDE.md) |
