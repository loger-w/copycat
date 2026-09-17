// #270 逐則步進 / 跳鎖板 / 鍵盤 對 Python 標準答案(rp_step_expected.py 的輸出)。
// 每個抽樣則 i:拖到它的收到時刻(驗落點 = 收到時刻 ≤ t 的最後一則 j)→ 按「前一則」j − i 次 → 逐欄比對;
// 每 4 則抽一則用真鍵盤 → ← 驗步進(焦點輪流放時間軸 / 頁面本體)且日期不變;展開模式下全價位比對階梯。
// 用法:node verify_steps.mjs <expected.json> <out.json>
import { readFileSync, writeFileSync } from 'node:fs';
import { launch, openPage, openReplay, setFull, drag, readState, num, sleep, NEW_PAGE } from './pp_common.mjs';

const EXP = JSON.parse(readFileSync(process.argv[2], 'utf8'));
const OUT = process.argv[3];
const DAY = EXP.day;
const fails = [];
const stats = { samples: 0, keyboard: 0, drags: 0, locks: 0, rowsCompared: 0 };
const fail = (code, what, got, want) => fails.push({ code, what, got, want });

function compareSample(code, s, st) {
  if (num(st.idx) !== s.idx) fail(code, `i=${s.i} 第幾則`, st.idx, s.idx);
  if (st.lab !== s.lab) fail(code, `i=${s.i} 標籤`, st.lab, s.lab);
  if (st.kind !== s.kind) fail(code, `i=${s.i} 成交則文字`, st.kind, s.kind);
  if (st.recv !== s.recv_text) fail(code, `i=${s.i} 收到`, st.recv, s.recv_text);
  if (st.px !== s.px) fail(code, `i=${s.i} 現價`, st.px, s.px);
  if (st.mkt !== s.mkt) fail(code, `i=${s.i} 市價佇列`, st.mkt, s.mkt);
  if (st.range !== s.recv) fail(code, `i=${s.i} 時間軸值`, st.range, s.recv);
  const pageBuy = {}, pageSell = {}, rowSet = new Set();
  for (const [p, b, a] of st.rows) { rowSet.add(p); if (b !== '') pageBuy[p] = num(b); if (a !== '') pageSell[p] = num(a); }
  for (const [side, want, got] of [['買', s.buy, pageBuy], ['賣', s.sell, pageSell]]) {
    for (const [p, q] of Object.entries(want)) {
      if (!rowSet.has(p)) fail(code, `i=${s.i} ${side} ${p} 不在階梯`, null, q);
      else if (q != null && got[p] !== q) fail(code, `i=${s.i} ${side} ${p}`, got[p] ?? '', q);
    }
    for (const [p, q] of Object.entries(got)) if (want[p] == null) fail(code, `i=${s.i} ${side} ${p} 多出`, q, null);
  }
  stats.rowsCompared += st.rows.length;
}

const browser = await launch();
const { page, errors } = await openPage(browser, NEW_PAGE);
const t0 = Date.now();
for (const [code, E] of Object.entries(EXP.codes)) {
  await openReplay(page, code, DAY);
  await setFull(page, true);
  let st = await readState(page, false);
  if (st.lockText !== E.lock_text) fail(code, '鎖板鈕文字', st.lockText, E.lock_text);
  if (st.lockDis !== (E.lock < 0)) fail(code, '鎖板鈕停用', st.lockDis, E.lock < 0);
  const byI = new Map(E.samples.map(s => [s.i, s]));
  for (const [k, s] of E.samples.entries()) {
    await drag(page, s.recv);
    st = await readState(page, false);
    if (num(st.idx) !== s.j + 1) fail(code, `拖到 ${s.recv_text} 落點`, st.idx, s.j + 1);
    for (let b = s.j - s.i; b > 0; b--) await page.click('#rpPrev');
    st = await readState(page);
    compareSample(code, s, st);
    stats.samples++;
    if (st.prevDis !== (s.i === 0)) fail(code, `i=${s.i} 前一則停用`, st.prevDis, s.i === 0);
    if (st.nextDis !== (s.i === E.n - 1)) fail(code, `i=${s.i} 後一則停用`, st.nextDis, s.i === E.n - 1);
    if (st.playDis !== (s.i === E.n - 1)) fail(code, `i=${s.i} 播放停用`, st.playDis, s.i === E.n - 1);
    if (k % 4 === 0) { // 真鍵盤:焦點輪流放時間軸 / 頁面本體
      if (k % 8 === 0) await page.focus('#rpRange'); else await page.evaluate(() => document.activeElement && document.activeElement.blur());
      if (s.i < E.n - 1) {
        await page.keyboard.press('ArrowRight');
        const r = await readState(page, false);
        const nx = byI.get(s.i + 1);
        if (num(r.idx) !== s.i + 2) fail(code, `i=${s.i} → 後第幾則`, r.idx, s.i + 2);
        if (nx && r.lab !== nx.lab) fail(code, `i=${s.i} → 標籤`, r.lab, nx.lab);
        if (r.date !== DAY) fail(code, `i=${s.i} → 換了日期`, r.date, DAY);
        await page.keyboard.press('ArrowLeft');
      }
      if (s.i > 0) {
        await page.keyboard.press('ArrowLeft');
        const r = await readState(page, false);
        if (num(r.idx) !== s.i) fail(code, `i=${s.i} ← 後第幾則`, r.idx, s.i);
        if (r.date !== DAY) fail(code, `i=${s.i} ← 換了日期`, r.date, DAY);
        await page.keyboard.press('ArrowRight');
      }
      compareSample(code, s, await readState(page)); // 來回一次後畫面回到原則
      stats.keyboard++;
    }
  }
  for (const d of E.drags) {
    await drag(page, d.t);
    st = await readState(page, false);
    if (num(st.idx) !== d.j + 1) fail(code, `拖到 ${d.t} 落點`, st.idx, d.j + 1);
    stats.drags++;
  }
  if (E.lock >= 0) {
    await drag(page, E.recv_first);
    await page.click('#rpPlay');
    await sleep(150);
    await page.click('#rpLock');
    st = await readState(page);
    if (st.play !== 'false') fail(code, '跳鎖板後仍在播放', st.play, 'false');
    compareSample(code, byI.get(E.lock), st);
    stats.locks++;
  }
}

// 2426 驗收段:11:02:44.025 同毫秒兩則逐則走過;重繪(視窗縮放 / 圖例開關)不從時刻回推
const A = EXP.codes['2426'];
const acc = {};
await openReplay(page, '2426', DAY);
await setFull(page, false);
await drag(page, 39764025);
acc.drag_110244025 = await readState(page, false);
await page.keyboard.press('ArrowLeft'); acc.left1 = await readState(page, false);
const row991 = () => page.evaluate(() => document.querySelector('#rpLadder .rp-row[data-p="99100"] .rp-q.buy .rp-n')?.textContent ?? '');
acc.left1_991 = await row991();
await page.evaluate(() => window.dispatchEvent(new Event('resize')));
await sleep(600);
acc.after_resize = await readState(page, false);
await page.evaluate(() => document.querySelector('#legend .chip').click());
await sleep(200);
acc.after_legend = await readState(page, false);
await page.evaluate(() => document.querySelector('#legend .chip').click());
// review P-02:停在同毫秒第 2 則 → 換檔 / 換到沒有簿檔的日子 / 連換 4 檔擠掉解碼快取(只留 3 份)→ 切回來仍是第 2 則
await openReplay(page, '3441', DAY); await openReplay(page, '2426', DAY);
acc.after_code_switch = await readState(page, false);
await page.evaluate(() => { const ds = document.getElementById('dateSel'); ds.value = '2026-09-15'; ds.dispatchEvent(new Event('change')); });
await page.waitForFunction(() => /這天沒有這檔的簿重播檔/.test(document.getElementById('tab-replay').textContent), { timeout: 20000 });
await openReplay(page, '2426', DAY);
acc.after_nofile_day = await readState(page, false);
for (const c of ['1815', '8064', '2344', '6770']) await openReplay(page, c, DAY);
await openReplay(page, '2426', DAY);
acc.after_cache_evict = await readState(page, false);
if (num(acc.after_code_switch.idx) !== 61599) fail('2426', '換檔再切回被回推', acc.after_code_switch.idx, 61599);
if (num(acc.after_nofile_day.idx) !== 61599) fail('2426', '換到無簿檔日再切回被回推', acc.after_nofile_day.idx, 61599);
if (num(acc.after_cache_evict.idx) !== 61599) fail('2426', '擠掉快取再切回被回推', acc.after_cache_evict.idx, 61599);
await page.keyboard.press('ArrowLeft'); acc.left2 = await readState(page, false); acc.left2_991 = await row991();
await page.keyboard.press('ArrowRight'); await page.keyboard.press('ArrowRight'); acc.back = await readState(page, false); acc.back_991 = await row991();
const s61598 = A.samples.find(s => s.i === 61598);
if (num(acc.drag_110244025.idx) !== 61600) fail('2426', '驗收 拖到 11:02:44.025', acc.drag_110244025.idx, 61600);
if (num(acc.left1.idx) !== 61599 || acc.left1.lab !== s61598.lab || acc.left1_991 !== '187') fail('2426', '驗收 ← 到第 2 則', [acc.left1.idx, acc.left1.lab, acc.left1_991], [61599, s61598.lab, '187']);
if (num(acc.after_resize.idx) !== 61599) fail('2426', '縮放視窗後被回推', acc.after_resize.idx, 61599);
if (num(acc.after_legend.idx) !== 61599) fail('2426', '開關圖例後被回推', acc.after_legend.idx, 61599);

await browser.close();
const result = { stats, fails: fails.length, failList: fails.slice(0, 50), consoleErrors: errors, acceptance: acc, seconds: Math.round((Date.now() - t0) / 1000) };
writeFileSync(OUT, JSON.stringify(result, null, 1));
console.log(JSON.stringify({ stats, fails: fails.length, consoleErrors: errors.length, seconds: result.seconds, first: fails.slice(0, 5) }));
