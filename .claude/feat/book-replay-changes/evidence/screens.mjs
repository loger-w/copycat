// #269 截圖(測試頁 viewer-cdp.269.html):驗收樣本與版面,淺色 / 深色 / 中等寬(兩欄)/ 390 寬(單欄)。
// headless 會沿用系統深色(#270 教訓),淺色要 emulateMediaFeatures 明講。
import { fileURLToPath } from 'node:url';
import { launch, openPage, openReplay, goIndex, readReplay, NEW_PAGE } from './pp_common.mjs';

const SHOTS = [
  // [檔名, 代號, 日期, 則號(0 起), 收到時刻, 落點則號, 主題, 視窗寬]
  ['replay269-2426-0948-reappear-light.png', '2426', '2026-09-16', 41956, 35315269, 41957, 'light', 1400],
  ['replay269-2426-0948-reappear-dark.png', '2426', '2026-09-16', 41956, 35315269, 41957, 'dark', 1400],
  ['replay269-2305-0907-pushed-out-light.png', '2305', '2026-09-16', 10149, 32867410, 10149, 'light', 1400],
  ['replay269-2489-1004-sweep-eats-light.png', '2489', '2026-09-16', 11608, 36271212, 11608, 'light', 1400],
  ['replay269-2305-0905-cleared-light.png', '2305', '2026-09-16', 6865, 32701174, 6865, 'light', 1400],
  ['replay269-2305-0905-cleared-dark.png', '2305', '2026-09-16', 6865, 32701174, 6865, 'dark', 1400], // 深色也要有淡色行可驗
  ['replay269-2426-medium-1100.png', '2426', '2026-09-16', 41956, 35315269, 41957, 'light', 1100],
  ['replay269-2426-narrow-390.png', '2426', '2026-09-16', 41956, 35315269, 41957, 'light', 390],
];

const result = [];
for (const [file, code, date, i, recv, land, theme, width] of SHOTS) {
  const browser = await launch({ width, height: 1000 });
  try {
    const { page, errors } = await openPage(browser, NEW_PAGE);
    await page.emulateMediaFeatures([{ name: 'prefers-color-scheme', value: theme }]);
    // 元素截圖會捲動拼接,sticky 頁頭會被拍進長圖中間(非版面問題);只為截圖把頁頭改成不黏
    await page.addStyleTag({ content: '.top{position:static !important}' });
    await openReplay(page, code, date);
    await goIndex(page, i, recv, land);
    const st = await readReplay(page);
    const layout = await page.evaluate(() => {
      const body = document.querySelector('.rp-body');
      const cols = getComputedStyle(body).gridTemplateColumns.split(' ').length;
      return { cols, scrollWidth: document.documentElement.scrollWidth, clientWidth: document.documentElement.clientWidth };
    });
    const el = await page.$('#tab-replay');
    await el.screenshot({ path: fileURLToPath(new URL(file, import.meta.url)) }); // 截圖落在本檔同資料夾(不看工作目錄)
    result.push({ file, idx: st.idx, lab: st.lab, cur: st.msgs[0], tapeTop: st.tape.slice(0, 3), layout, errors });
  } finally {
    await browser.close();
  }
}
console.log(JSON.stringify(result, null, 1));
