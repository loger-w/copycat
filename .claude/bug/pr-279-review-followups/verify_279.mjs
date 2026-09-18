// PR #279 收修的真實環境驗證:正式回看頁(重建後)+ 正式外掛檔(v3)。
// 用法:RP_NEW_PAGE=viewer-cdp.html node verify_279.mjs
import { launch, openPage, openReplay, drag, readReplay, NEW_PAGE } from
  'file:///C:/side-project/copycat/.claude/worktrees/fix-pr-279-review-followups/.claude/feat/book-replay-changes/evidence/pp_common.mjs';

const results = [];
const check = (name, ok, detail) => { results.push({ name, ok, detail }); console.log(`${ok ? 'PASS' : 'FAIL'} ${name} :: ${detail}`); };

async function gotoIndex(page, target, recvMs) {
  await drag(page, recvMs);
  for (let k = 0; k < 60; k++) {
    const idx = await page.evaluate(() => Number(document.getElementById('rpIdx').textContent.replace(/,/g, '')));
    if (idx === target + 1) return true;
    const btn = idx > target + 1 ? 'rpPrev' : 'rpNext';
    await page.evaluate(b => document.getElementById(b).click(), btn);
    await page.evaluate(() => new Promise(r => requestAnimationFrame(() => requestAnimationFrame(r))));
  }
  return false;
}
const msgOf = (st, label) => st.msgs.find(m => m.head.some(h => h.includes(label)));

const browser = await launch({ width: 1500, height: 1100 });
try {
  const { page, errors } = await openPage(browser, NEW_PAGE);

  const dates = await page.evaluate(() => [...document.getElementById('dateSel').options].map(o => o.value));
  check('9/18 進日期選單', dates.includes('2026-09-18'), `最後三天 ${dates.slice(-3).join(', ')}`);

  // 1) 2305 09-16 暫緩撮合結束那一筆:整則不拆 + 吃檔空
  await openReplay(page, '2305', '2026-09-16');
  let ok = await gotoIndex(page, 12959, 33141572);
  let st = await readReplay(page);
  const auction = msgOf(st, '第 12,960 則');
  check('2305 撮合那一則標集合競價撮合', ok && !!auction && auction.lines[0].text.includes('集合競價撮合'),
    auction ? auction.lines.map(l => l.text).join(' / ') : '(找不到該則)');
  const tape772 = st.tape.find(r => r.cells.some(c => c.includes('772')));
  check('2305 撮合那一筆吃檔留空', !!tape772 && tape772.cells[4].trim() === '—', tape772 ? tape772.cells.join(' | ') : '(無)');
  await page.evaluate(() => document.getElementById('rpNext').click());   // 走到下一則(撮合後那筆 16 張)
  await page.evaluate(() => new Promise(r => requestAnimationFrame(() => requestAnimationFrame(r))));
  const st2305b = await readReplay(page);
  const tape16 = st2305b.tape.find(r => r.cells[2] === '16');
  check('2305 下一筆 16 張吃回自己', !!tape16 && /吃 賣1 · −16/.test(tape16.cells[4]), tape16 ? tape16.cells.join(' | ') : '(無)');

  // 2) 5314 09-17 開盤後兩則:撤單而不是成交
  await openReplay(page, '5314', '2026-09-17');
  ok = await gotoIndex(page, 5, 32412664);
  st = await readReplay(page);
  const m6 = msgOf(st, '第 6 則'), m5 = msgOf(st, '第 5 則');
  check('5314 第 6 則 −20 撤單', ok && !!m6 && m6.lines[0].text.includes('撤單') && m6.lines[0].text.includes('20'),
    m6 ? m6.lines.map(l => l.text).join(' / ') : '(無)');
  check('5314 第 5 則 −110 撤單', !!m5 && m5.lines[0].text.includes('撤單') && m5.lines[0].text.includes('110'),
    m5 ? m5.lines.map(l => l.text).join(' / ') : '(無)');
  const tapeOpen = st.tape.find(r => r.cells[2].includes('11,090'));
  check('5314 開盤那筆吃檔「—」', !!tapeOpen && tapeOpen.cells[4].trim() === '—', tapeOpen ? tapeOpen.cells.join(' | ') : '(無)');
  check('5314 價格寫法一致(階梯式固定小數)', !!tapeOpen && tapeOpen.cells[1] === '27.75', tapeOpen ? tapeOpen.cells[1] : '(無)');

  // 3) 3481 09-16:296 張記回自己那筆 + 吃檔中點
  await openReplay(page, '3481', '2026-09-16');
  ok = await gotoIndex(page, 7, 32401495);
  st = await readReplay(page);
  const tape296 = st.tape.find(r => r.cells[2] === '296');
  check('3481 296 張吃回自己 + 中點', !!tape296 && /吃 賣1 · −296/.test(tape296.cells[4]), tape296 ? tape296.cells.join(' | ') : '(無)');
  const tape1690 = st.tape.find(r => r.cells[2].includes('1,690'));
  check('3481 開盤那筆吃檔「—」', !!tape1690 && tape1690.cells[4].trim() === '—', tape1690 ? tape1690.cells.join(' | ') : '(無)');

  // 4) 版面:三欄 + 分隔線對齊(同一組內每行三欄的左緣一致)
  const layout = await page.evaluate(() => {
    const lines = [...document.querySelectorAll('#rpChg .rp-msg .rp-line.rp-cols')];
    if (!lines.length) return { n: 0 };
    const xs = lines.slice(0, 12).map(l => [...l.children].map(c => Math.round(c.getBoundingClientRect().left)));
    const first = JSON.stringify(xs[0]);
    const dim = document.querySelector('#rpChg .rp-msg.cur .rp-line.dim');
    return { n: lines.length, aligned: xs.every(x => JSON.stringify(x) === first), cols: xs[0],
      dimColor: dim ? getComputedStyle(dim).color : null, sample: lines[0].textContent };
  });
  check('變動行三欄 + 欄位左緣對齊', layout.n > 0 && layout.aligned, `n=${layout.n} 欄左緣 ${JSON.stringify(layout.cols)}`);

  check('console 沒有錯誤', errors.length === 0, JSON.stringify(errors).slice(0, 300));
  console.log('\n合計 ' + results.filter(r => r.ok).length + '/' + results.length + ' PASS');
} finally {
  await browser.close();
}
