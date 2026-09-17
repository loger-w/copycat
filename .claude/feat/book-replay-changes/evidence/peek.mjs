// #269 快速目視:測試頁 2426 09-16 拖到 09:48:35.269(買 98.0 回到五檔),印中間欄 / 成交明細、截圖。
import { launch, openPage, openReplay, drag, readReplay, NEW_PAGE } from './pp_common.mjs';

const out = process.argv[2] ?? 'peek.png';
const browser = await launch({ width: 1400, height: 1100 });
try {
  const { page, errors } = await openPage(browser, NEW_PAGE);
  await openReplay(page, '2426', '2026-09-16');
  await drag(page, 9 * 3600000 + 48 * 60000 + 35269);
  const st = await readReplay(page);
  console.log(JSON.stringify({ idx: st.idx, lab: st.lab, recv: st.recv }, null, 0));
  for (const m of st.msgs.slice(0, 4)) console.log((m.cur ? '▶ ' : '  ') + m.head.join(' | ') + '\n    ' + m.lines.map(l => (l.dim ? '(dim) ' : '') + l.text).join('\n    '));
  for (const r of st.tape.slice(0, 5)) console.log((r.cur ? '▶ ' : '  ') + r.cells.join(' | '));
  const el = await page.$('#tab-replay');
  await el.screenshot({ path: out });
  console.log('errors', JSON.stringify(errors));
} finally {
  await browser.close();
}
