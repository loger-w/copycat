# verification — mod/calendar-poll-tape-omitted

| gate | 結果 |
|---|---|
| vitest 全套 | 137 files / 2530 passed(+lock 後 stock-accum 再 +1) |
| tsc -b / eslint src | 0 / 0 |
| react-doctor --scope changed | 9 files, No issues |
| mutation | StockPage 拿掉 `loading` prop → 1 failed;還原 59 passed |

真實環境:SC-1 跨午夜膠囊需長跑分頁 + 午夜窗(08-23 00:00 後 preview 分頁看「日曆判今日休市」膠囊是否 5 分鐘內出現 —— 週日為非交易日,膠囊語意 = calendar_trade_date≠today 且非週末 → 週日不亮;真窗口 = 下一個錯標平日,待 user);
SC-3/4 群組→單檔首 paint「載入明細…」窗口次秒級,headless 截不到,以 StockPage/TickTape 測試代證 + user 過目。
