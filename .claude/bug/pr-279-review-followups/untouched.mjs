// 收尾抽驗:兩個沒改到的功能(上方主圖 + 逐筆明細分頁)在新頁 / 新日照樣正常。
import { launch, openPage, selectDay, clickTab, REVIEW } from
  'file:///C:/side-project/copycat/.claude/worktrees/fix-pr-279-review-followups/.claude/feat/book-replay-changes/evidence/pp_common.mjs';

const check = (name, ok, detail) => console.log(`${ok ? 'PASS' : 'FAIL'} ${name} :: ${detail}`);
const browser = await launch({ width: 1500, height: 1050 });
try {
  const { page, errors } = await openPage(browser, REVIEW + 'viewer-cdp.html');
  await selectDay(page, '1303', '2026-09-18');
  await page.evaluate(() => new Promise(r => setTimeout(r, 1200)));

  const main = await page.evaluate(() => ({
    svgAll: document.querySelectorAll('svg').length,
    paths: document.querySelectorAll('svg path').length,
    title: (document.querySelector('.head, header, #hdr')?.textContent ?? '').replace(/\s+/g, ' ').slice(0, 70),
  }));
  check('上方主圖有畫出來(9/18 新日)', main.svgAll > 0 && main.paths > 0,
    `svg ${main.svgAll} · path ${main.paths} · 標頭 ${main.title}`);

  await clickTab(page, 'ticks');
  await page.evaluate(() => new Promise(r => setTimeout(r, 1500)));
  const ticks = await page.evaluate(() => {
    const box = document.getElementById('tab-ticks');
    return {
      rows: box ? box.querySelectorAll('tr').length : -1,
      text: (box?.textContent ?? '').replace(/\s+/g, ' ').slice(0, 80),
    };
  });
  check('逐筆明細分頁有列(9/18 新日)', ticks.rows > 1, `tr ${ticks.rows} · ${ticks.text}`);
  check('console 沒有錯誤', errors.length === 0, JSON.stringify(errors).slice(0, 200));
} finally {
  await browser.close();
}
