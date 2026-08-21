# SC-5' 前後對照(2026-08-21,headless Chrome)
before = preview 4173(master 2b0b3c3e build),after = dev 5173(本分支)。同 localStorage 初始態(host 寫入)。
PIL ImageChops 像素差異:
- 1600 stock:bbox (513,22)-(1263,540) = header 即時指數 + 走勢圖/五檔活資料;1600 index/fut/rail-orders:僅 header 指數 (1096,22)-(1166,48)。
- 1536 stock/index/rail-orders:僅 header 指數;1536 fut:header + 五檔量條寬度(活資料)。
→ pill 列(交易別 / 檢視 / 商品 / 週期 / 圖表模式)、分頁列、側欄列**零像素差異**。
