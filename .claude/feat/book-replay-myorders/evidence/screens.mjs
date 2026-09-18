// #272 截圖(現用頁 viewer-cdp.html):驗收樣本 3441 09-16、成交標記、未知(委?)、市價單說明、窄版。
// headless 會沿用系統深色(#270 教訓),淺色要 emulateMediaFeatures 明講。
import { fileURLToPath } from 'node:url';
import { writeFileSync } from 'node:fs';
import { launch, openPage, openReplay, setFull, drag, NEW_PAGE } from './pp_common.mjs';

const SHOTS = [
  // [檔名, 代號, 日期, 收到時刻(ms), 展開, 主題, 視窗寬, 主題說明]
  ['my272-3441-0903-order-light.png', '3441', '2026-09-16', 32612500, false, 'light', 1400, '驗收:09:03:32 掛買 181.0 一張,委 1 在 181 那一格'],
  ['my272-3441-0903-order-dark.png', '3441', '2026-09-16', 32612500, false, 'dark', 1400, '同上(深色)'],
  ['my272-3441-0904-100lots-light.png', '3441', '2026-09-16', 32682385, false, 'light', 1400, '驗收:09:04:42.385 買 181.0 = 100 張,成 1 還在同一格'],
  ['my272-3441-0906-resting-light.png', '3441', '2026-09-16', 32760000, false, 'light', 1400, '賣 181.5 掛著(09:06:48 才刪);買 181.0 已成交'],
  ['my272-3441-0909-locked-light.png', '3441', '2026-09-16', 32970000, true, 'light', 1400, '鎖漲停後(展開):買 181 成 1、賣 182.5 成 1'],
  ['my272-2426-0918-unknown-light.png', '2426', '2026-09-18', 37800000, false, 'light', 1400, '當日成交還沒補 → 虛線「委? 2」'],
  ['my272-6179-0918-market-light.png', '6179', '2026-09-18', 43200000, false, 'light', 1400, '市價單不畫在格子上,說明列寫幾筆'],
  ['my272-3441-narrow-390.png', '3441', '2026-09-16', 32760000, false, 'light', 390, '窄版單欄'],
];

const result = [];
for (const [file, code, date, recv, full, theme, width, why] of SHOTS) {
  const browser = await launch({ width, height: 1000 });
  try {
    const { page, errors } = await openPage(browser, NEW_PAGE);
    await page.emulateMediaFeatures([{ name: 'prefers-color-scheme', value: theme }]);
    // headless 的 prefers-color-scheme 模擬在本機沒讓兩張不同(#270 教訓的反面),改直接下頁面自己的 data-theme
    await page.evaluate(theme => { document.documentElement.dataset.theme = theme; }, theme);
    await page.addStyleTag({ content: '.top{position:static !important}' });
    await openReplay(page, code, date);
    await setFull(page, full);
    await drag(page, recv);
    const st = await page.evaluate(() => ({
      idx: document.getElementById('rpIdx').textContent,
      lab: document.getElementById('rpClock').textContent,
      note: document.querySelector('.rp-note').textContent.slice(-160),
      tags: [...document.querySelectorAll('#rpLadder .rp-me')].map(e => ({ cls: e.className, text: e.textContent, title: e.getAttribute('title') })),
      layout: { cols: getComputedStyle(document.querySelector('.rp-body')).gridTemplateColumns.split(' ').length, scrollWidth: document.documentElement.scrollWidth, clientWidth: document.documentElement.clientWidth },
    }));
    const el = await page.$('#tab-replay');
    await el.screenshot({ path: fileURLToPath(new URL(file, import.meta.url)) });
    result.push({ file, why, idx: st.idx, lab: st.lab, tags: st.tags, note: st.note, layout: st.layout, errors });
    console.log(file, st.idx, JSON.stringify(st.tags));
  } finally {
    await browser.close();
  }
}
writeFileSync(new URL('./result_screens.json', import.meta.url), JSON.stringify(result, null, 1), 'utf8');
