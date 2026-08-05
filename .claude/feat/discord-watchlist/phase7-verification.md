# phase7 verification — discord-watchlist(HEAD 342f7a7)

fresh 證據(本 session 親跑):全案 pytest 1822 passed / ruff 0 / pyright 0;
五個相關測試檔合跑 **246 passed**;consumer script 實跑輸出
`evidence/SC-1237_real-env-consumer-output.txt`。

| SC | 實作檔案:行號 | 自動化測試 | real-env 證據 | regression 抽樣 |
|---|---|---|---|---|
| SC-1 groups 含空群組+未分組數 | discord_bot.py:277(handle_groups)/:289(_format_groups) | test_discord_bot.py TestHandleGroups 四態(246 passed 合跑內) | consumer 輸出:`【觀察】0 檔`、`未分組 1 檔(衍生,非群組)`、雙分支 | /watch list 舊格式(consumer)不變 |
| SC-2 group add/remove/rename + GROUP_NOT_FOUND | watchlist_service.py:103/:118/:128;discord_bot.py:311/:331/:350 | test_watchlist_service TestCreateGroup/TestDeleteGroup/TestRenameGroup + handler 層(同上合跑) | consumer:建群/改名/`找不到該群組`/壞檔零寫 | apply 同內容零寫早退(consumer)✓ |
| SC-3 ungroup 仍在自選 | watchlist_service.py:144;discord_bot.py:374 | TestUngroup(service+handler) | consumer:`已自群組 電子 移出:2317 鴻海(仍在自選)` | — |
| SC-4 autocomplete(子字串/≤25/降級) | discord_bot.py:394(group_choices);create_bot 四掛點 :558+ | TestGroupChoices 六態 + TestRealDiscordWiring qualified-name 集合(真跑非 skip) | consumer:`['半導體','觀察']`;**Discord 實發:待 user 過目**(brainstorm SC-4 窗口條款降級,證據已備) | — |
| SC-5 軟白名單警告 | discord_bot.py:206(handle_add hint) | test_handle_add_unknown_code_warning | consumer:`已加入自選:9999(查無此檔名稱,請確認代碼)` | — |
| SC-6 保留名 gate + 讀時遷移 | stock_watchlist.py:46/:75-83/:98 | test_stock_watchlist TestNormalize/TestWatchlistPersistence(26 passed 檔級) | consumer:group add 未分組 →`群組名稱不合法`;prod 檔檢查 groups=[玻璃,石英] 無中毒 | v1/v2/v3 讀路測試鎖 |
| SC-7 回覆差異化 | discord_bot.py:206/:230(changed flag 分文案) | test_handle_add_noop_text / test_handle_remove_noop_text + 文案逐字鎖 | consumer:`已在自選:9999(無變更)(查無…)` | — |
| SC-8 零退化 | — | 全案 pytest 1822 passed / ruff 0 / pyright 0(automated-verification-round-1.json) | — | R9 守門:同 codes 零 SUB/UNSUB(engine+signal_hub 兩側)|

無 FAIL 項 → 不觸發四分流。SC-4 real-env 欄依規則使用允許例外
(`截圖`級證據以 consumer 輸出 + 單元測試代替,Discord 實發 = user 過目,
對應 brainstorm SC-4 明文降級條款,非 N/A)。
