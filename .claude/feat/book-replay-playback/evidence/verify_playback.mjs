// #270 播放控制:功能判準 + 流暢度量測(2426 09-16)。
// 功能:倍速準確度(頁內 performance.now 對時間軸推進)、暫停鍵、切分頁 / 換檔暫停且速度沿用、播到最後一則自動停、
//       播放中拖曳續播、播放中步進暫停、非重播分頁 ← → 照舊換日、沒有簿檔的日子 ← → 不換日。
// 量測:(A) 逐則同步更新耗時(點「後一則」+ 強制 layout,11:02:00–11:02:50 共 798 次,一般 / 展開兩模式);
//       (B) 1x 從 11:02:00 播到 11:02:50 鎖板(一般 / 展開各一次)與 10x 同段:包住 requestAnimationFrame 量每幀
//           回呼耗時(播放迴圈 + 重畫)、幀間隔、Long Animation Frame(> 50 ms)、每秒更新次數與每秒回呼總耗時。
// 用法:node verify_playback.mjs <out.json>
import { writeFileSync } from 'node:fs';
import { launch, openPage, openReplay, setFull, drag, readState, clickTab, selectDay, num, sleep, NEW_PAGE } from './pp_common.mjs';

const OUT = process.argv[2];
const DAY = '2026-09-16';
const T110200 = 39720000, LOCK_RECV = 39770829, LOCK_IDX = 61737; // 首次鎖漲停 = 第 61,737 則,收到 11:02:50.829
const checks = [];
const check = (name, ok, detail) => { checks.push({ name, ok: !!ok, detail }); };
const pct = (a, p) => { const s = [...a].sort((x, y) => x - y); return s.length ? +s[Math.min(s.length - 1, Math.floor(p / 100 * s.length))].toFixed(3) : null; };
const summary = a => ({ n: a.length, p50: pct(a, 50), p95: pct(a, 95), p99: pct(a, 99), max: a.length ? +Math.max(...a).toFixed(3) : null });

const browser = await launch();
const { page, errors } = await openPage(browser, NEW_PAGE);
await openReplay(page, '2426', DAY);
await setFull(page, false);

// ---------- 功能 ----------
const speedBtn = s => page.click(`#tab-replay [data-speed="${s}"]`);
// 倍速準確度:頁內同時記 performance.now 與時間軸值
for (const sp of [1, 2, 5, 10]) {
  await drag(page, 39600000); // 11:00:00
  await speedBtn(sp);
  const r = await page.evaluate(async () => {
    const range = document.getElementById('rpRange'); const v0 = Number(range.value);
    document.getElementById('rpPlay').click(); const t0 = performance.now();
    await new Promise(res => setTimeout(res, 2000));
    const v1 = Number(range.value), t1 = performance.now(); document.getElementById('rpPlay').click();
    return { dv: v1 - v0, dt: t1 - t0 };
  });
  const ratio = r.dv / r.dt;
  check(`倍速 ${sp}x:時間軸推進 / 真實經過`, Math.abs(ratio / sp - 1) < 0.1, { ...r, ratio: +ratio.toFixed(3) });
}
await speedBtn(1);
// 暫停後不再推進
await drag(page, 39600000);
await page.click('#rpPlay'); await sleep(400); await page.click('#rpPlay');
let a = await readState(page, false); await sleep(600); let b = await readState(page, false);
check('暫停鍵:暫停後時間軸不動、按鈕回到播放', a.range === b.range && b.play === 'false' && b.playText === '▶ 播放', { a: a.range, b: b.range, play: b.play, text: b.playText });
// 播放中按鈕狀態
await page.click('#rpPlay'); await sleep(100); a = await readState(page, false);
check('播放中按鈕 = 暫停、aria-pressed true', a.play === 'true' && a.playText === '❚❚ 暫停', { play: a.play, text: a.playText });
// 播放中拖曳 → 從新位置接著播
await drag(page, 39000000); await sleep(600); a = await readState(page, false);
check('播放中拖曳:仍在播放且從新位置往後走', a.play === 'true' && a.range > 39000000 && a.range < 39002000, { range: a.range, play: a.play });
// 播放中步進 → 暫停
await page.click('#rpNext'); a = await readState(page, false); await sleep(300); b = await readState(page, false);
check('播放中按後一則:暫停且停在那一則', a.play === 'false' && a.range === b.range && a.idx === b.idx, { a: [a.idx, a.range, a.play], b: [b.idx, b.range] });
// 播放中鍵盤 → → 暫停
await page.click('#rpPlay'); await sleep(200); await page.keyboard.press('ArrowRight'); a = await readState(page, false);
check('播放中按 →:暫停', a.play === 'false' && a.date === DAY, { play: a.play, date: a.date });
// 切到別的分頁 → 暫停;切回來不續播、時間軸沒在背景跑
await speedBtn(10); await drag(page, 39600000); await page.click('#rpPlay'); await sleep(300);
a = await readState(page, false); await clickTab(page, 'ticks'); await sleep(1500); await clickTab(page, 'replay'); await sleep(100);
b = await readState(page, false);
check('切到逐筆分頁再切回:已暫停、背景沒推進', b.play === 'false' && b.range - a.range < 1000, { before: a.range, after: b.range, play: b.play });
// 換檔 → 暫停,速度沿用
await page.click('#rpPlay'); await sleep(200);
await openReplay(page, '3441', DAY); a = await readState(page, false);
check('播放中換檔:新檔已暫停、速度沿用 10x', a.play === 'false' && a.speed.join() === '10', { play: a.play, speed: a.speed, key: a.key });
await openReplay(page, '2426', DAY);
// 換日 → 暫停(只有 09-16 有簿檔:播放中換到 09-15 再換回來)
await page.click('#rpPlay'); await sleep(200); a = await readState(page, false);
await selectDay(page, '2426', '2026-09-15');
await page.waitForFunction(() => /這天沒有這檔的簿重播檔/.test(document.getElementById('tab-replay').textContent), { timeout: 20000 });
await sleep(500); await openReplay(page, '2426', DAY); b = await readState(page, false);
check('播放中換日(09-16 → 09-15 → 09-16):已暫停、時間軸沒在背景推進、速度沿用 10x', a.play === 'true' && b.play === 'false' && b.range - a.range < 1000 && b.speed.join() === '10', { before: [a.play, a.range], after: [b.play, b.range, b.speed] });
// 播到最後一則自動停
const lastRecv = await page.evaluate(() => Number(document.getElementById('rpRange').max));
await drag(page, lastRecv - 300); await page.click('#rpPlay'); await sleep(900); a = await readState(page, false);
check('播到最後一則自動停:播放停用、後一則停用', a.play === 'false' && num(a.idx) === 64512 && a.nextDis && a.playDis && a.range === lastRecv, { idx: a.idx, range: a.range, playDis: a.playDis, nextDis: a.nextDis });
// 跳鎖板
await page.click('#rpLock'); a = await readState(page, false);
check('跳到首次鎖漲停:第 61,737 則、收到 11:02:50.829', num(a.idx) === LOCK_IDX && a.recv === '11:02:50.829' && a.range === LOCK_RECV, { idx: a.idx, recv: a.recv, lab: a.lab, kind: a.kind });
// 10x 從 11:02:00 播到鎖板:真實耗時與過程
await drag(page, T110200);
const run10 = await page.evaluate(async (LOCK_IDX) => {
  const idxEl = document.getElementById('rpIdx'); const t0 = performance.now(); const seen = new Set();
  document.getElementById('rpPlay').click();
  while (Number(idxEl.textContent.replace(/[^0-9]/g, '')) < LOCK_IDX && performance.now() - t0 < 15000) { seen.add(idxEl.textContent); await new Promise(r => requestAnimationFrame(r)); }
  const t1 = performance.now(); document.getElementById('rpPlay').click();
  return { ms: Math.round(t1 - t0), distinctIdx: seen.size, recv: document.getElementById('rpRecv').textContent };
}, LOCK_IDX);
check('10x 從 11:02:00 播到 11:02:50 鎖板約 5 秒', run10.ms > 4000 && run10.ms < 6500, run10);
// 非重播分頁 ← → 照舊換日
await clickTab(page, 'ticks'); await page.evaluate(() => document.activeElement && document.activeElement.blur());
await page.keyboard.press('ArrowLeft'); a = await page.evaluate(() => document.getElementById('dateSel').value);
await page.keyboard.press('ArrowRight'); b = await page.evaluate(() => document.getElementById('dateSel').value);
check('逐筆分頁 ← → 照舊換日', a === '2026-09-15' && b === DAY, { left: a, right: b });
// 沒有簿檔的日子:重播分頁說明找不到檔,← → 不換日
await selectDay(page, '2426', '2026-09-15'); await clickTab(page, 'replay');
await page.waitForFunction(() => /這天沒有這檔的簿重播檔/.test(document.getElementById('tab-replay').textContent), { timeout: 20000 });
await page.keyboard.press('ArrowRight'); a = await page.evaluate(() => document.getElementById('dateSel').value);
check('沒有簿檔的日子:重播分頁 → 不換日', a === '2026-09-15', { date: a });
await openReplay(page, '2426', DAY);

// ---------- 量測 ----------
const perf = {};
async function syncSteps(full) {
  await setFull(page, full); await drag(page, T110200);
  return page.evaluate(() => {
    const next = document.getElementById('rpNext'), lad = document.getElementById('rpLadder'), costs = [];
    for (let k = 0; k < 798; k++) { const s = performance.now(); next.click(); void lad.offsetHeight; costs.push(performance.now() - s); }
    return { costs, endIdx: document.getElementById('rpIdx').textContent };
  });
}
for (const full of [false, true]) {
  const r = await syncSteps(full);
  perf[`逐則同步更新_${full ? '展開' : '一般'}`] = { ...summary(r.costs), endIdx: r.endIdx };
}
await page.evaluate(() => {
  const orig = window.__origRAF = window.requestAnimationFrame.bind(window);
  window.__cb = [];
  window.requestAnimationFrame = cb => orig(ts => { const s = performance.now(); try { cb(ts); } finally { window.__cb.push([s, performance.now() - s]); } });
  window.__loaf = [];
  try { new PerformanceObserver(l => { for (const e of l.getEntries()) window.__loaf.push({ start: e.startTime, dur: e.duration, block: e.blockingDuration }); }).observe({ type: 'long-animation-frame' }); window.__loafOK = true; } catch (e) { window.__loafOK = false; }
});
async function playRun(full, speed) {
  await setFull(page, full); await speedBtn(speed); await drag(page, T110200);
  return page.evaluate(async (LOCK_IDX) => {
    window.__cb = []; window.__loaf = [];
    const orig = window.__origRAF, frames = [], idxEl = document.getElementById('rpIdx'), updates = [];
    const mo = new MutationObserver(() => updates.push(performance.now())); mo.observe(idxEl, { childList: true, characterData: true, subtree: true });
    let run = true; const loop = ts => { frames.push(ts); if (run) orig(loop); }; orig(loop);
    const t0 = performance.now(); document.getElementById('rpPlay').click();
    while (Number(idxEl.textContent.replace(/[^0-9]/g, '')) < LOCK_IDX && performance.now() - t0 < 70000) await new Promise(r => setTimeout(r, 50));
    const t1 = performance.now(); document.getElementById('rpPlay').click(); run = false; mo.disconnect();
    const iv = frames.slice(1).map((f, k) => f - frames[k]);
    const cb = window.__cb.filter(([s]) => s >= t0 && s <= t1).map(([, d]) => d);
    const perSec = {}; for (const [s, d] of window.__cb) if (s >= t0 && s <= t1) { const k = Math.floor((s - t0) / 1000); perSec[k] = (perSec[k] || 0) + d; }
    const updPerSec = {}; for (const u of updates) { const k = Math.floor((u - t0) / 1000); updPerSec[k] = (updPerSec[k] || 0) + 1; }
    return { ms: Math.round(t1 - t0), cb, iv, perSec: Object.values(perSec), updPerSec: Object.values(updPerSec), updates: updates.length, loaf: window.__loaf.filter(e => e.start >= t0 && e.start <= t1), loafOK: window.__loafOK, recv: document.getElementById('rpRecv').textContent };
  }, LOCK_IDX);
}
for (const [full, speed] of [[false, 1], [true, 1], [false, 10], [true, 10]]) {
  const r = await playRun(full, speed);
  perf[`播放_${speed}x_${full ? '展開' : '一般'}`] = {
    realMs: r.ms, endRecv: r.recv, updates: r.updates, 每幀回呼耗時ms: summary(r.cb), 幀間隔ms: summary(r.iv),
    每秒回呼總耗時ms: summary(r.perSec), 每秒更新次數: summary(r.updPerSec), 長框_50ms以上: r.loaf.length, loafSupported: r.loafOK, loafMaxMs: r.loaf.length ? Math.max(...r.loaf.map(e => e.dur)) : 0,
  };
  console.log(`播放 ${speed}x ${full ? '展開' : '一般'} 完成`, r.ms, 'ms');
}
await browser.close();
const out = { checks, failed: checks.filter(c => !c.ok).length, perf, consoleErrors: errors };
writeFileSync(OUT, JSON.stringify(out, null, 1));
console.log(JSON.stringify({ failed: out.failed, consoleErrors: errors.length, checks: checks.map(c => (c.ok ? 'PASS ' : 'FAIL ') + c.name) }, null, 1));
console.log(JSON.stringify(perf, null, 1));
