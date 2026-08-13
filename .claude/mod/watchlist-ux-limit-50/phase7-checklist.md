# §7 回頭核 goal — 逐條打勾(重讀 change-spec.md,非憑記憶)

## 成功條件

| SC | 判定 | 證據 |
|---|---|---|
| SC-1 上限 50(PUT 50→200/51→400;group-state 50→200/51→400) | ✅ | 實作 `stock_watchlist.py:37`;測試 `test_put_at_limit_ok` / `test_put_over_limit_400` / `test_group_state_at_limit_ok` / `test_too_many_codes_400`(紅→綠 bfbfd222→d36900d0);real-env `evidence/SC-1_api-boundary.txt` 六條全符 |
| SC-2 文案全通道一致 + 常數推導 | ✅ | `errText` 模板字串 + bot f-string;測試三處字面 50;grep 殘餘命中皆明列無關 30(包 1 回報 + lens A 全庫複核);parity oracle(e4e3082a)機械鎖雙邊同值 |
| SC-3 群組標題列可指認差異 | ✅(user 過目待) | classList 測試 4 支(83700f26→b768c691);截圖 `evidence/SC-3_group-header-band.png` + computed style(標題列 #10161f/fw500 vs 個股列 transparent/fw400) |
| SC-4 全部展開/收合 + 持久化 + EMPTY_WL gate | ✅(user 過目待) | 測試 6 支(3ba160c3→2eafc41d + B-1 序列 lock 085ef998,mutation-verified);截圖 `SC-4_collapsed.png` / `SC-4_expanded.png`;F5 重整收合保留(截圖 agent 實測);未載入 gate 測試 + wlReady 單一判斷 |
| SC-5 效能盤點 + 必要調參 | ✅ | current-state.md §B B-1~B-9 逐項(含 review 補的 B-9 basis worker、B-1 穩態);結論零調參;next-time :408/:1033/:62/:676 數字同步 + 退出準則 |

## 白名單(11 條)

lens A 逐條對照全數保留(code-review-round-1.json `whitelist_check`);其中:
1 applyCollapsed 三步 ✅(toggleAll 走同一寫入點 + B-1 lock);2 key 名/值格式 ✅;
3 拖曳幾何/hover 守衛 ✅(B-2 拖曳態測試補鎖);4 a11y ✅;5 error 契約 ✅(real-env
BAD_CODE/BAD_CODES/WATCHLIST_FULL 實測);6 W-22 零 PUT ✅(未觸及);7 先去重再驗數 ✅
(real-env 51 重複碼→200);8 signal hub 30/分 ✅(測試綠);9 讀時遷移 ✅(未觸及);
10 其餘文案 ✅;11 _REPLY_LIMIT ✅(未觸及)。

## Migration 可逆

30→50 純放寬零 migration;回退 50→30 時 >30 檔存檔落入既有「可讀但不可 normalize」態
(讀路不炸,PUT 報 WATCHLIST_FULL)— spec §E 已文件化,非新風險。✅

## 未關事項

- SC-3/SC-4 user 過目(雙層驗收的第二層,收尾回報列操作路徑)。
- 側車(8721)+ vite dev(5173)仍開著供過目。
