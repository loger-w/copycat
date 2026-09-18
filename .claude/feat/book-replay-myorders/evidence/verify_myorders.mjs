// #272 我的委託 / 成交:把回看頁重播分頁的階梯逐格與 Python 標準答案(rp272_expected.json)比對,
// 另驗一個開關、跳到上一筆 / 下一筆我的成交、tooltip、市價單不畫。
// 用法: RP_NEW_PAGE=viewer-cdp.html node verify_myorders.mjs
import { readFileSync, writeFileSync } from 'node:fs';
import { launch, openPage, openReplay, setFull, drag, NEW_PAGE } from './pp_common.mjs';

const CASES = JSON.parse(readFileSync(new URL('./rp272_expected.json', import.meta.url), 'utf8'));
const out = { page: NEW_PAGE, cases: [], checks: [], errors: [] };
let asserts = 0;
const eq = (what, got, want) => { asserts++; if (JSON.stringify(got) !== JSON.stringify(want)) fail(what, got, want); };
const fail = (what, got, want) => out.checks.push({ ok: false, what, got, want });
const pass = (what, note) => out.checks.push({ ok: true, what, note });

// 階梯逐格:data-p(毫元)→ {買量, 賣量, 買委, 買成, 賣委, 賣成, 列外框}
async function readLadder(page) {
  return page.evaluate(() => {
    const tag = (cell, kind) => {
      const e = cell && cell.querySelector('.rp-me.' + kind);
      return e ? { text: e.textContent, title: e.getAttribute('title') || '', unk: e.classList.contains('unk') } : null;
    };
    const num = cell => { const e = cell && cell.querySelector('.rp-n'); return e ? Number(e.textContent.replace(/,/g, '')) : null; };
    const rows = {};
    for (const r of document.querySelectorAll('#rpLadder .rp-row[data-p]')) {
      const b = r.querySelector('.rp-q.buy'), s = r.querySelector('.rp-q.sell');
      rows[r.dataset.p] = { bq: num(b), sq: num(s), bo: tag(b, 'ord'), bf: tag(b, 'fill'), so: tag(s, 'ord'), sf: tag(s, 'fill'), me: r.classList.contains('me') };
    }
    return rows;
  });
}

const browser = await launch();
try {
  const { page, errors } = await openPage(browser, NEW_PAGE);
  out.errors = errors;

  for (const c of CASES) {
    await openReplay(page, c.code, c.date);
    await setFull(page, true);                       // 展開漲停–跌停:我的委託不論離現價多遠都在 DOM 裡
    await drag(page, c.recv);
    const idx = await page.evaluate(() => document.getElementById('rpIdx').textContent);
    eq(`${c.code} ${c.date} ${c.at} 落點則號`, idx, (c.i + 1).toLocaleString('en-US'));
    const rows = await readLadder(page);

    // 1. 期望的每一格「委 / 成」都在,數字與虛線(未知)相符
    const seen = new Set();
    for (const [key, want] of Object.entries(c.me)) {
      const [side, px] = key.split('@');
      seen.add(key);
      const r = rows[px];
      if (!r) { fail(`${c.code} ${c.at} ${key} 該價位不在階梯上`, null, want); continue; }
      const ord = side === 'buy' ? r.bo : r.so, fl = side === 'buy' ? r.bf : r.sf;
      const wantOrd = want.ord ? `委${want.unk ? '?' : ''} ${want.ord}` : null;
      const wantFill = want.fill ? `成 ${want.fill}` : null;
      eq(`${c.code} ${c.at} ${key} 委託標記`, ord ? ord.text : null, wantOrd);
      eq(`${c.code} ${c.at} ${key} 成交標記`, fl ? fl.text : null, wantFill);
      if (wantOrd && ord) { eq(`${c.code} ${c.at} ${key} 委託 tooltip 行數`, ord.title.split(String.fromCharCode(10)).length, want.seq.length);
        for (const sq of want.seq) eq(`${c.code} ${c.at} ${key} 委託 tooltip 帶委託序號 ${sq}`, ord.title.includes(`(委託序號 ${sq})`), true); }
      if (wantFill && fl && !fl.title.includes('成交 ')) fail(`${c.code} ${c.at} ${key} 成交 tooltip`, fl.title, '含「成交 」');
      if (wantOrd && ord) eq(`${c.code} ${c.at} ${key} 虛線(未知)`, ord.unk, want.unk > 0);
      eq(`${c.code} ${c.at} ${key} 整列外框`, r.me, true);
    }
    // 2. 沒期望的格子一個標記都不能有(市價單、已刪 / 已成交的委託都在這裡被抓)
    for (const [px, r] of Object.entries(rows)) {
      for (const [side, o, f] of [['buy', r.bo, r.bf], ['sell', r.so, r.sf]]) {
        const key = `${side}@${px}`;
        if (!seen.has(key)) eq(`${c.code} ${c.at} ${key} 不該有標記`, (o ? o.text : '') + (f ? f.text : ''), '');
      }
    }
    // 3. 五檔量本身沒被標記擠掉
    for (const [pxText, q] of Object.entries(c.buy)) {
      const px = String(Math.round(Number(pxText) * 1000));
      eq(`${c.code} ${c.at} 買 ${pxText} 量`, rows[px] ? rows[px].bq : null, q);
    }
    for (const [pxText, q] of Object.entries(c.sell)) {
      const px = String(Math.round(Number(pxText) * 1000));
      eq(`${c.code} ${c.at} 賣 ${pxText} 量`, rows[px] ? rows[px].sq : null, q);
    }
    // 4. 說明列的市價單句子
    const note = await page.evaluate(() => document.querySelector('.rp-note').textContent);
    const wantMkt = c.mkt ? `另有 ${c.mkt} 筆市價委託沒畫在格子上` : null;
    if (wantMkt && !note.includes(wantMkt)) fail(`${c.code} ${c.at} 說明列市價單`, note.slice(-120), wantMkt);
    if (!c.mkt && note.includes('筆市價委託')) fail(`${c.code} ${c.at} 說明列不該提市價單`, note.slice(-120), '無');
    out.cases.push({ code: c.code, date: c.date, at: c.at, why: c.why, idx, me: c.me, mkt: c.mkt });
  }

  // 5. 一個開關:關掉 → 階梯零標記 + 上方圖零成交標記;開回來 → 回復
  const c0 = CASES[3]; // 3441 09:06:00:同時有成交標記與掛著的委託
  await openReplay(page, c0.code, c0.date);
  await setFull(page, true);
  await drag(page, c0.recv);
  const before = await readLadder(page);
  const chartBefore = await page.evaluate(() => document.querySelectorAll('svg polygon').length);
  const tagsOf = rows => Object.values(rows).filter(r => r.bo || r.bf || r.so || r.sf).length;
  await page.evaluate(() => [...document.querySelectorAll('#legend .chip')].find(b => b.textContent.includes('你的委託 / 成交')).click());
  const off = await readLadder(page);
  const chartOff = await page.evaluate(() => document.querySelectorAll('svg polygon').length);
  if (tagsOf(off) !== 0) fail('開關關掉後階梯標記數', tagsOf(off), 0);
  if (Object.values(off).some(r => r.me)) fail('開關關掉後仍有整列外框', true, false);
  if (chartOff >= chartBefore) fail('開關關掉後上方圖的成交標記變少', { chartBefore, chartOff }, 'chartOff < chartBefore');
  await page.evaluate(() => [...document.querySelectorAll('#legend .chip')].find(b => b.textContent.includes('你的委託 / 成交')).click());
  const back = await readLadder(page);
  if (JSON.stringify(back) !== JSON.stringify(before)) fail('開關開回來後階梯不同', tagsOf(back), tagsOf(before));
  else pass('一個開關同時關掉委託 + 成交(階梯 + 上方圖),開回來逐格相同', { 階梯標記: tagsOf(before), 圖標記: chartBefore - chartOff });

  // 6. 跳到上一筆 / 下一筆我的成交
  for (const code of ['3441', '2426']) {
    const c = CASES.find(x => x.code === code && x.date === (code === '3441' ? '2026-09-16' : '2026-09-16'));
    await openReplay(page, c.code, c.date);
    await drag(page, 0);                               // 回到第一則
    const got = [];
    for (let k = 0; k < c.fill_idx.length + 1; k++) {
      const dis = await page.evaluate(() => document.getElementById('rpFNext').disabled);
      if (dis) break;
      await page.evaluate(() => document.getElementById('rpFNext').click());
      got.push(Number((await page.evaluate(() => document.getElementById('rpIdx').textContent)).replace(/,/g, '')));
    }
    const want = c.fill_idx.map(i => i + 1);
    if (JSON.stringify(got) !== JSON.stringify(want)) fail(`${code} 下一筆我的成交(由第一則連按)`, got, want);
    else pass(`${code} 下一筆我的成交連按落在 ${want.join(' / ')} 則`);
    const backTo = [];
    for (let k = 0; k < want.length + 1; k++) {
      const dis = await page.evaluate(() => document.getElementById('rpFPrev').disabled);
      if (dis) break;
      await page.evaluate(() => document.getElementById('rpFPrev').click());
      backTo.push(Number((await page.evaluate(() => document.getElementById('rpIdx').textContent)).replace(/,/g, '')));
    }
    const wantBack = want.slice(0, -1).reverse();
    if (JSON.stringify(backTo) !== JSON.stringify(wantBack)) fail(`${code} 上一筆我的成交`, backTo, wantBack);
    else pass(`${code} 上一筆我的成交回到 ${wantBack.join(' / ') || '(只有一筆,第一次就停用)'}`);
  }
  // 沒有成交的日子兩顆都停用
  await openReplay(page, '2426', '2026-09-18');
  await drag(page, CASES.find(x => x.code === '2426' && x.date === '2026-09-18').recv);
  const dis = await page.evaluate(() => ({ p: document.getElementById('rpFPrev').disabled, n: document.getElementById('rpFNext').disabled }));
  if (!dis.p || !dis.n) fail('沒有我的成交時兩顆跳成交按鈕停用', dis, { p: true, n: true });
  else pass('2426 09-18 沒有我的成交 → 兩顆跳成交按鈕停用');

  // 7. 播放中按跳成交會先暫停(與跳鎖板同)
  await openReplay(page, '3441', '2026-09-16');
  await drag(page, 0);
  await page.evaluate(() => document.getElementById('rpPlay').click());
  const playing = await page.evaluate(() => document.getElementById('rpPlay').getAttribute('aria-pressed'));
  await page.evaluate(() => document.getElementById('rpFNext').click());
  const after = await page.evaluate(() => document.getElementById('rpPlay').getAttribute('aria-pressed'));
  if (playing !== 'true' || after !== 'false') fail('播放中跳成交要先暫停', { playing, after }, { playing: 'true', after: 'false' });
  else pass('播放中按「下一筆我的成交」會先暫停');

  // 8. 關掉「你的委託 / 成交」→ 兩顆跳成交按鈕也停用(隱藏 = 連導航一起停)
  await openReplay(page, '3441', '2026-09-16');
  await drag(page, 0);
  const onState = await page.evaluate(() => ({ p: document.getElementById('rpFPrev').disabled, n: document.getElementById('rpFNext').disabled }));
  await page.evaluate(() => [...document.querySelectorAll('#legend .chip')].find(b => b.textContent.includes('你的委託 / 成交')).click());
  const offState = await page.evaluate(() => ({ p: document.getElementById('rpFPrev').disabled, n: document.getElementById('rpFNext').disabled }));
  await page.evaluate(() => [...document.querySelectorAll('#legend .chip')].find(b => b.textContent.includes('你的委託 / 成交')).click());
  const backState = await page.evaluate(() => ({ p: document.getElementById('rpFPrev').disabled, n: document.getElementById('rpFNext').disabled }));
  eq('開關開著時「下一筆我的成交」可按', onState, { p: true, n: false });
  eq('開關關掉時兩顆跳成交按鈕停用', offState, { p: true, n: true });
  eq('開關開回來後恢復', backState, { p: true, n: false });
} finally {
  await browser.close();
}
out.summary = { asserts, checks: out.checks.length, fail: out.checks.filter(c => !c.ok).length, errors: out.errors.length };
writeFileSync(new URL('./result_myorders.json', import.meta.url), JSON.stringify(out, null, 1), 'utf8');
console.log(JSON.stringify(out.summary));
for (const c of out.checks.filter(c => !c.ok)) console.log('FAIL', JSON.stringify(c));
for (const e of out.errors) console.log('PAGE', e);
