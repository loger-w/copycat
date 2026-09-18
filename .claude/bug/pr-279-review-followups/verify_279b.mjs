// 補兩條:2305 撮合後下一筆吃回自己;v2 外掛檔往下相容(頁面指到 v2 備份資料夾)。
import { launch, openPage, openReplay, drag, readReplay, REVIEW } from
  'file:///C:/side-project/copycat/.claude/worktrees/fix-pr-279-review-followups/.claude/feat/book-replay-changes/evidence/pp_common.mjs';

const check = (name, ok, detail) => console.log(`${ok ? 'PASS' : 'FAIL'} ${name} :: ${detail}`);
async function gotoIndex(page, target, recvMs) {
  await drag(page, recvMs);
  for (let k = 0; k < 60; k++) {
    const idx = await page.evaluate(() => Number(document.getElementById('rpIdx').textContent.replace(/,/g, '')));
    if (idx === target + 1) return true;
    await page.evaluate(b => document.getElementById(b).click(), idx > target + 1 ? 'rpPrev' : 'rpNext');
    await page.evaluate(() => new Promise(r => requestAnimationFrame(() => requestAnimationFrame(r))));
  }
  return false;
}

const browser = await launch({ width: 1500, height: 1100 });
try {
  // (1) 正式頁:2305 09-16 第 12,961 則(撮合後下一筆 16 張)
  const a = await openPage(browser, REVIEW + 'viewer-cdp.html');
  await openReplay(a.page, '2305', '2026-09-16');
  const ok = await gotoIndex(a.page, 12960, 33141587);
  const st = await readReplay(a.page);
  const t16 = st.tape.find(r => r.cells[2] === '16');
  check('2305 撮合後下一筆 16 張吃回自己', ok && !!t16 && /吃 賣1 · −16/.test(t16.cells[4]), t16 ? t16.cells.join(' | ') : '(無)');
  const cur = st.msgs.find(m => m.cur);
  check('2305 第 12,961 則變動 = 賣 49.10 −16 成交', !!cur && cur.lines[0].text.includes('成交'), cur ? cur.lines.map(l => l.text).join(' / ') : '(無)');

  // (2) v2 往下相容:同一份頁面指到 v2 備份外掛檔
  const b = await openPage(browser, REVIEW + 'viewer-cdp.v2compat.html');
  await openReplay(b.page, '2305', '2026-09-16');
  const st2 = await readReplay(b.page);
  const bad = b.errors.filter(e => /外掛檔格式不符|版本/.test(e));
  check('v2 外掛檔照樣讀得到(往下相容)', st2.msgs.length > 0 && bad.length === 0,
    `則 ${st2.idx} / 變動列 ${st2.msgs.length} / 成交明細 ${st2.tape.length} / 版本錯誤 ${bad.length}`);
  const auctionLine = st2.msgs.some(m => m.lines.some(l => l.text.includes('集合競價撮合')));
  check('v2 檔沒有集合競價標記(新欄位當沒有)', !auctionLine, auctionLine ? '(舊檔竟出現標記)' : '如預期沒有');
  check('v2 頁 console 沒有錯誤', b.errors.length === 0, JSON.stringify(b.errors).slice(0, 200));
} finally {
  await browser.close();
}
