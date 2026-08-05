# brainstorm — Discord 自選補齊(題 4)

規格來源:`.claude/feat/stock-quintet-discussion/brainstorm.md` 題 4(2026-08-05 user 逐題拍板)
→ /auto 預核准替代條件成立(user 拍板文件),grilling 拷問已於討論輪完成。

分流判定:**已成形方案** — 條件 1 中(指令集 / autocomplete / gate 落點全指名)、
條件 2 中(仍有實作層決策點,見 [auto-default] 標記)。

## 目標

Discord `/watch` 從「add/remove/list 三指令」補齊為完整自選 + 群組管理面,
回答 user 的核心問題「新增股票時怎麼知道加進哪個群組」(→ autocomplete)。

## 現況(2026-08-05 master a858dec 實讀)

- `copycat/server/discord_bot.py`:`/watch add|remove|list`,純 handler + duck-typed
  interaction,`_ERROR_TEXT` 三碼,`_format_watchlist` 空群組不列(:204-219)
- `copycat/server/watchlist_service.py`:單鎖 add/remove/apply/current,`_commit`
  canonical 零寫早退(呼叫端分不出 no-op)
- `copycat/stock_watchlist.py`:normalize 單一定義(群組名驗證 :81-84);
  「未分組」保留名只有前端擋(`WatchlistManagerDialog.tsx`),後端不擋
- 上限:codes 聯集 30;群組數 / 名長無上限
- 測試:`tests/server/test_discord_bot.py`、`tests/server/test_watchlist_service.py`、
  `tests/test_stock_watchlist.py`(相應擴充)

## 成功條件(SC)

- **SC-1** `/watch groups`:列出**全部**群組(**含空群組**)+ 各群成員數 + 未分組數。
  驗證:pytest `tests/server/test_discord_bot.py::test_handle_groups*`(anytime)
- **SC-2** `/watch group add <name>` / `group remove <name>` / `group rename <old> <new>`:
  建空群組;刪群組(成員留在自選、落回未分組);改名(成員關係不變)。
  刪/改不存在的群組 → 新 error code `GROUP_NOT_FOUND` → 文案「找不到該群組」。
  驗證:pytest(service 層 + handler 層各自斷言)(anytime)
- **SC-3** `/watch ungroup <code> <group>`:僅自該群組移出,code 仍在自選;
  code 不在該群組 → no-op 文案區分。驗證:pytest(anytime)
- **SC-4** group 參數 autocomplete:`/watch add`、`/watch ungroup`、`/watch group
  remove|rename` 的群組參數即時列出現有群組名(子字串過濾、≤25 個、service 未就緒 /
  讀取逾時回空)。[amendment 2026-08-05: design review R8 — 前綴改子字串(中文名無
  前綴語意)+ R1 補逾時降級][auto-default: 子字串過濾 | reason: 中文群組名無前綴語意]
  驗證:autocomplete callback 抽成純 async 函式 pytest;Discord 實發窗口 = user 過目
  (窗口外降級:單元測試 + user 事後實發)
- **SC-5** 軟白名單:`/watch add` 的 code 不在 `stock_names.json` → 照常加入但回覆
  帶警告(「查無此檔名稱,請確認代碼」)。驗證:pytest(anytime)
- **SC-6** 「未分組」保留名後端 gate:`normalize` 拒絕群組名 =「未分組」(strip 後)
  → `BAD_GROUP`;bot 與前端 PUT 兩路同時被擋。驗證:pytest
  `tests/test_stock_watchlist.py::test_normalize_rejects_reserved_name`(anytime)
- **SC-7** 回覆差異化:add 已存在 →「已在自選」;remove 不存在 →「不在自選」;
  與真變更文案不同。驗證:pytest(anytime)
- **SC-8** 既有行為零退化:全 suite `pytest -q` 綠 + `ruff` + `pyright` 過。
  驗證:gate 指令輸出(anytime)

## Edge cases

1. ungroup 最後一個成員 → 群組變空但**保留**(SC-1 可見)
2. rename 撞既有群組名 → normalize 重複名 → `BAD_GROUP`
3. rename 前後同名(strip 後相同)→ no-op 文案
4. `/watch add 2330 未分組` → SC-6 擋 `BAD_GROUP`
5. autocomplete 時 service 未就緒 / watchlist 壞檔 → 回空清單不炸
6. `/watch groups` 零群組 →「尚無群組」
7. 群組名前後空白 → normalize strip 後處理(既有行為,不變)
8. 舊檔已存在名為「未分組」的群組(理論可能)→ load 不炸;下次任何寫入
   normalize 才拒 → 需決策(見 [auto-default])

## 決策記錄

- `[auto-default: 群組指令用巢狀 subgroup(/watch group add …) | reason: discord.py
  app_commands.Group 支援一層巢狀,語意清楚;攤平成 group-add 會讓 /watch 頂層塞 8 個指令]`
- `[auto-default: 刪群組成員留自選(落回未分組) | reason: groups 只記成員關係的資料模型
  (stock_watchlist docstring),與前端 Manager Dialog 刪群行為一致]`
- `[auto-default: GROUP_NOT_FOUND 新 error code 僅 bot 消費,前端 errText 不加 |
  reason: 前端 PUT 是整份取代語意,永遠不會觸發此碼;避免無意義的雙檔同步]`
- `[auto-default: no-op 偵測用 service 回傳 changed flag(add/remove/ungroup 回
  tuple[Watchlist, bool]) | reason: _commit 早退分支已知道答案,handler 雙讀有 TOCTOU;
  Protocol 是內部契約(bot + tests),blast radius 小]`
- `[auto-default: edge 8(舊檔已含「未分組」群組)不做遷移,首次寫入時報 BAD_GROUP |
  reason: 該狀態只能由手改檔或舊 bot 路徑造成,實際檔案不存在此狀態;報錯比靜默改資料誠實]`
- `[auto-default: 群組數/名長上限本輪不加 | reason: quintet 共識未列;權限已拍板不設,
  上限屬另一題;記 next-time]`

## Out of scope

- 批次多代碼 add、`/watch clear`(共識未列)
- 權限控管(user 拍板:不設)
- `/signals` Discord 指令(題 1 範疇)
- 前端 UI 改動(零前端檔;`GROUP_NOT_FOUND` 不進前端)
- 群組數量 / 名稱長度上限(→ next-time)

## 規模分流

**M**(3 檔 code:discord_bot.py / watchlist_service.py / stock_watchlist.py + 測試;
動共用 util `stock_watchlist.normalize` — 不可 S)→ Phase 1 完整走。

## 驗證窗口

全 SC anytime(pytest);SC-4 的 Discord 實發層 = user 過目(prod 重啟後),
窗口外降級已寫入 SC-4。
