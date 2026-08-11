# /doctor — codebase 體檢(唯讀,不改任何檔案)

跑兩邊的健康掃描,彙整成一份「真實訊號」報告。純觀察,不 fix、不 commit。

## 步驟

1. **Frontend**:在 `frontend/` 跑 `npm run doctor`(= `npx react-doctor@latest`,react-doctor 已是 devDependency)。
2. **Backend**:在 repo root 跑 `ruff check copycat tests --select ALL --statistics`(刻意不掃 `spikes/` — 實驗碼不算病)。

## 回報判準

- 兩邊分開回報,只列「值得行動」的類別,每類附件數 + 一句為什麼值得看。
- Backend 已知噪音直接過濾不報:S101(測試 assert)、D 系(docstring)、ANN 系(type annotation 全覆蓋)、COM812 等純格式規則——除非某類數字比上次報告明顯暴增。
- 重點盯的真訊號家族:DTZ(裸 `datetime.now()` / `date.today()`,台股時間敏感專案的真 bug 類)、BLE / S110 / S112(吞錯誤嫌疑,對照鐵則 E 逐一判)、ASYNC 系(async 裡阻塞呼叫)。
- 歷史基線:上次體檢結論如有留檔在 `docs/doctor/`,對照著報增減;沒有就報當次絕對值。
- 發現值得排的待辦 → 建議寫進待辦清單(徵得同意或依當時指示),不順手改 code。
