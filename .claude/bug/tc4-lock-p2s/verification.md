# verification — tc4-lock-p2s(quintet review X-2a/X-2b/X-3 三條 P2)

分支:`fix/tc4-lock-p2s`(6 commits 三組紅綠對 + 收尾 review 補 3 commits;
收尾時 rebase 到 bd422d7a)

## 自動化 gate(收尾 review 補齊後主 session 親跑,2026-08-11)

| gate | 結果 | exit |
|---|---|---|
| pytest -q | **2580 passed**(rebase 後 2577 + review 補 3 條) | 0 |
| ruff check copycat tests | All checks passed! | 0 |
| pyright | 0 errors, 0 warnings | 0 |
| replay four/five + copycat validate | **42/42 PASS** | 0 |

## 收尾 review(/code-review medium,一輪)

32 候選 → 6 CONFIRMED / 1 PLAUSIBLE / 2 REFUTED,無 P0/P1(見
code-review-round-1.json)。處置:R-4/5/6(retry timer 生命週期三處)當場修
(紅先行,紅樣態實測:孤兒 timer 5 次呼叫 / 移出後 cache 復活 / handle 未清);
R-1/2/3 docstring 與實際上界對齊;R-1 深修(_pool_lock convoy)+ R-7/8 入
docs/next-time.md。

零 frontend diff,前端 gate 免跑。

## 真實環境驗證

三條都是併發/時序結構修復,穩定重現 = 紅測試(受控時序;fake 慢 REQ /
raise-then-succeed daily_bars / 慢 subscribe fake + 亂序 seq),盤中不可
deterministic 重現。prod 生效待下次自然重啟(health `git_sha` 判法)。

- X-2a:`lock_timeout` 12.0 > `_REQ_TIMEOUT_MS` 10s,以不等式契約測試鎖住
  (不寫死 12);dispose-on-timeout 毒鎖防護行為測試保持綠。
- X-2b:CDP 基準例外有限重試(≤2 次、30s delay、`_stale` 尺擋跨日殘留);
  空 bars 資料面維持不重試。
- X-3:watchlist `_commit` 落檔+定序留鎖內、訂閱移鎖外,engine `set_watchlist`
  seq 定序 last-writer-wins;亂序測試鎖住舊名單不蓋新名單。

## 反向驗證

TDD 紅先行:三組 commit 皆 [red]→[green] 成對(`git log --grep` 可機械驗證),
紅測試在無修復碼時已各自驗紅(受控時序命中原 bug 樣態)。

## 留尾巴

- X-2a 偵測 KeepAlive 毒鎖的延遲由 5s 升至 12s(拍板接受的代價)。
- repro.md「實驗記錄」節:X-2a 不等式與 X-3 鎖凸出為結構事實,執行證據 = 紅測試。
