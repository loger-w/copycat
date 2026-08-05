# phase7 verification — signal-rules(HEAD d40af17)

fresh 證據:六 gate 全綠(automated-verification.md);SC-7 六項截圖 + DOM/API 交叉
(real-env-verification-round-1.json);lens B 的 SC 逐條對應表(code-review-round-1)
已核無缺格。

| SC | 實作檔案 | 自動化測試 | real-env 證據 | regression 抽樣 |
|---|---|---|---|---|
| SC-1 規則模型 | copycat/signal_rules.py | tests/test_signal_rules.py(104+ 條;PARAM_SPECS 字面鎖補入) | fake server 冷啟動遷移實證 | — |
| SC-2 hub 引擎 | signal_hub.py(_RuleSlot/評估迴圈/fanout) | TestPayloadContract/TestRuleEngine/TestDiscordText 等 | — | 既有 62 條 signal_state 測試原封綠 |
| SC-3 熱重載 | upsert/delete + _seed_slot | test_put_edits_in_place_and_hot_reloads(hub+route)/test_upsert_preserves_other_rules_state | SC-7.4 新增即入列(API 同步) | — |
| SC-4 遷移+舊 API 移除 | _load_or_migrate_rules/_legacy_flags;T3b | test_migration_*/TestLegacyEnabledRouteGone | fake server GET rules 四條預設 | — |
| SC-5 刪自選停監聽 | _drop_code 逐 slot+雙 cache | test_watchlist_removal_stops_all_rules | — | user 硬性要求,紅先行鎖 |
| SC-6 REST CRUD | app.py 四 route + handler | TestSignalRulesRoutes(201/400×10/404/500/503/缺欄) | SC-7.4/5 真 HTTP 往返 | 503 清單測試 |
| SC-7 前端規則 UI | SignalRail/SignalRulesDialog/useSignalRules/StockPage | 前端 89 條(rail 3/Dialog 18/hook 9/Page 2 + fix 輪 6) | 五張截圖 + DOM/API 交叉全 PASS + **user 過目待列收尾** | 提示音/允許通知區不變 |
| SC-8 feed 規則名 | SignalRail 並列(fix B1) | 並列共存 + fallback 兩條 | 盤中真訊號 = user 過目層(降級記錄) | — |
| SC-9 零退化 | — | 六 gate 全綠 | — | pytest 1982 全案 |

無 FAIL → 不分流。
