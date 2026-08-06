# phase7 verification — group-grid(HEAD cfd2f86)

fresh 證據:六 gate 全綠(automated-verification.md;pytest 2096/vitest 1423);
SC-3 五項截圖 + DOM 交叉(real-env round-1);lens B 的 SC/edge 對照表核無缺格。

| SC | 實作檔案 | 自動化測試 | real-env 證據 | regression 抽樣 |
|---|---|---|---|---|
| SC-1 同群摘要 | signal_hub._group_suffix/_send_discord | TestGroupSuffix 13+ 條(格式逐字/edge 1-4/7/兩層送出) | 盤中 Discord 實發 = user 過目層(降級記錄) | notify gate/節流不受影響測試 |
| SC-2 hub 接線 | app.py 兩 fn + engine.quotes + _refresh_groups | TestQuotes/TestSignalHubGroupWiring/B3-a 只改群組名端到端 | fake server 冷啟動接線實證(摘要鏈路活) | 既有訊號 fanout 測試綠 |
| SC-3 群組檢視 | StockPage pill/GroupGridView/MiniIntradayChart | StockPage 群組 6 條 + GridView 15+ 條 + mini 11+ 條 | 五張截圖全 PASS + **user 過目待列收尾** | 單檔檢視既有測試零改動 |
| SC-4 資料鏈 | group_snapshot(light)+ route + useGroupSnapshots | TestGroupSnapshot(含 B2 no_data 半邊)/route 六態/hook 6 條/liveP 接線(B1) | payload 量測 59KB/5 檔;回補中→出圖實測 | backfill guard 新契約 + 主圖回補測試;tc4_status 隔離(A2) |
| SC-5 零退化 | — | 六 gate 全綠(flake triage 記錄) | — | pytest 2096 全案 |

無 FAIL → 不分流。SC-1 real-env 欄 = 降級(盤中實發待 user,brainstorm 驗證窗口條款);
SC-3 = 截圖 + user 過目。
