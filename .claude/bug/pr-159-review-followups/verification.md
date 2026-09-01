# verification — fix/pr-159-review-followups(2026-08-31)

worktree `C:/side-project/copycat-wt-pr159-followups`,自 origin/master dfc3cdf2。純前端(零 .py diff)。
來源 = `/pr-review 159` 報告(`docs/superpowers/specs/pr-159-review.md`)8 條 findings;user 拍板:F-01 選 (a)、F-02 選 (a)、F-03~F-08 + 報告收檔直接做。

## 自動化 gate(auto-verify;全部在 worktree 跑)

| gate | 指令(工作目錄) | 結果 | exit |
|---|---|---|---|
| 🔵 收線後(dbc334e0) | `npx vitest run` 三支 hook 測試(frontend/) | 63 passed、測試零改(僅刪巢狀 afterEach) | 0 |
| 紅迴圈(修前) | 同上 market + futures 兩檔 | 2 failed(`expected 2 to be 3` —— 60 s 後沒有重試)| 1 |
| 紅迴圈(修後,8fd5f53f) | 三檔 hook 測試 | 65 passed | 0 |
| 反向驗證 | `git revert --no-commit 8fd5f53f` → vitest → `git reset --hard HEAD` → vitest | 還原後 2 failed / 39 passed;復原後 41 passed | 紅回來 → 綠回去 PASS |
| 突變體(全 commit 後跑;還原 `git checkout --` 安全) | M-a 拔空態閘 / M-b stock 誤開 retryEmpty / M-c market 誤關 / M-d futures 誤關 | 4/4 KILLED(各紅在對應測試;M-b 紅在「tf=D 空 + ok 前進 60s 仍只打一次」= SC-4 白名單鎖) | 紅(殺) |
| tsc / eslint | `npx tsc -b` / `npx eslint src` | 無輸出 / 無輸出 | 0 / 0 |
| vitest 全量 | `npm test` | 153 files / 2914 passed | 0 |
| react-doctor | `--scope changed`(7 files) | No issues found! | 0 |
| pytest / ruff / pyright / validate | — | 未跑:零 .py / configs diff | skipped(理由如左) |

## 白名單核對

- 分 K 路徑三支逐字不變(diff 只動日 K 分支與 import);既有跨日測試 13+ 條全綠。
- `useStockBars` 空 + ok 不輪詢(SC-4)由 `retryEmpty: false` 保住,M-b 突變體證明測試釘得住。
- **assertion 事前標該變(僅一處)**:useFuturesBars.test「日 K 不輪詢」fixture 是空 bars —— F-01 拍板 (a) 的直接後果;
  該條真契約 = 「非空日 K 不輪詢」,fixture 換一根完成 bar、名字改口,斷言本體不變(記入 🔴 commit message)。

## 真實環境

同 #159:無法在真時間內跨午夜。判準併入既有清單(`.claude/bug/daily-bars-siblings-rollover/verification.md` 1–5 條)再加一條:
6. 後端開著、達錢 4 關著跨 00:00 → 00:01 拿到空回應後,Network 每 60 s 一發 `tf=D` 直到達錢 4 開起來;
   開起來後下一發即載回完整日 K,之後回到「下一個午夜」節奏(不再每 60 s)。

### 09-01 真環境實測結果(preview 4173 prod bundle + claude-in-chrome 實錄)

| # | 判準 | 結果 |
|---|---|---|
| 2 | 末根 = 當日 | **PASS(個股/期指)**:盤中 2330 與 TXF 末根即 09-01(期指夜盤歸次一交易日口徑正確)。加權盤中(08:57 冷啟動的 server)整個上午末根 08-31、15:15 重啟後末根 09-01 —— **成因未分辨**(`market_bars` 無 `refresh` 參數、無法跳 cache:是日曆日 cache 鎖住 08:57 快照、還是 TC4 指數 DK 盤中不給部分日 bar,兩可),歸 #165 `DAILY_FINAL_TIME` 線對帳,非本 PR 範圍(前端拿到 200+非空即照規矩今晚 00:01 再問) |
| 3 | 切 tab 不重抓 | **PASS**:日 K 載入後兩輪切換(→個股→回→期貨→回),`tf=D` 全程 1 發 |
| 5 | 後端關 → 60 s 重試 | **PASS**:F5 冷 mount 後 66 s 窗恰 4 發 500 = t0 一對(本體+retry:1)+ 60 s 後一對 |
| 6 | 達錢 4 關 → 空態 60 s 輪替 → 自癒 | **PASS(全鏈)**:user 真殺達錢 4 process + run.ps1 冷啟動 → 後端 200+空(`source: unavailable`)→ 前端「無 K 線資料」空態 → 60 s 輪替(74 s 窗恰 2 發 200)→ user 開回達錢 4 → 後端 15:51:00 TC4 reconnected → 前端載回完整日 K(末根 09-01)→ **之後 70 s 零新請求(輪詢停)**。唯一縫:「輪詢中不重載自動撿到資料」那一刻未實錄(觀測分頁中途被切走),該環節由 hook 測試 + 突變體 M-a~M-d 釘住 |
| 1 / 4 | 00:01 準時那發(+ 個股頁跨午夜照打) | **判準 1 PASS(節流變體;09-02 00:16 排程 session 實錄)**:server-20260901-1531.log L3812 `GET /api/market/bars/TWSE?tf=D` 恰一發,錨定 [00:06:18 .. 00:08:44] —— 比 00:01±1 晚 5–7 分,分頁整晚掛著但螢幕鎖定/遮蔽,歸因 Chrome occluded 視窗計時器節流(推定,未另實證);設計目標全達成:跨日恰一輪、翻日重問、**全夜零 60 s 連發**(log 唯一 tf=D 連發段 = 15:32–15:52 判準 6 實驗,已知)。同鄰域 L3813 `TMF?tf=D` 亦恰一發 = `useFuturesBars` 同鉤同法 —— **順帶收掉 #151/#155 的「某晚掛過 00:01 翌晨 grep」跨午夜窗口**(TMF 實錄,TXF 同 hook)。**判準 4 未上演**:全 log 零 `stock/bars/*?tf=D` —— 分頁整晚停在期貨 tab(00:06 的 TMF 發即證據),且個股頁日 K query 要「單檔 + 日 K 模式」才掛(22:19 個股頁預設江波圖零發)。續驗 = 某晚個股單檔切日 K 掛過午夜;或接受 hook 測試 + 突變體覆蓋結案 —— 留 user 拍板 |

實測撈到的操作事實(已入 ops-discipline):關達錢 4 視窗不殺 process 家族;TQ hidden 分頁全暫停(觀測必須可見);bash nohup 起的測試 server 收不到 console Ctrl+C。

## Review round 1(two-axis,fixed point dfc3cdf2;12 條,見 `code-review-round-1.json`)

Spec 軸:F-01~F-08 + 報告收檔 9/9 全 DONE;降私有擴及判 F-02 閉包非 creep;四個可疑點(undefined 誤判 /
stock SC-4 / W/M 同吃 / 60 s 在拍板區間)全 PASS;一條 P-LOW 知情(空快照下切回 tab 等最多 60 s interval,
staleTime 半邊無空態閘 —— 上界 60 s、方向安全)。
Standards 軸:接受 S-F2 / S-F4 / S-F7(收修 commit c45c6d0f 測試衛生 + 5e40f44e docs)、S-F5(隨 5e40f44e);
反駁 S-F1(「10 突變體」正確 —— M1–M9 + round-1 節的 M4b,同檔 gate 表明載 10/10 KILLED,grep '^| M' 只數到
第一張表)、S-F6(retryEmpty 命名:必填 options 已是 flag-argument 緩解、直述行為);S-F3 由本檔滿足(對象
錯位:review 當下本 artifact 尚未 cp 進 worktree);S-F8 知情(🔵 內含 F-04 測試刪行,message 已揭露)。

| 收修後 gate | 結果 | exit |
|---|---|---|
| `npx vitest run` futures + stock 兩檔 | 47 passed(斷言零改,S-F4 只換取數 helper) | 0 |

**流程事故(記 ops-discipline 候選)**:S-F4 收修腳本斷言炸掉只套一半、隨後 `git commit --amend` 打錯目標
(HEAD 在 docs commit 上)把測試改動折進 docs —— 以 `git reset --soft` 拆開重組,終態 c45c6d0f 純測試 /
5e40f44e 純 docs(`git show --stat` 逐筆核過)。教訓:amend 前先 `git log -1` 核對 HEAD。
