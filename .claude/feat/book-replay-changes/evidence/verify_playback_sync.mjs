// #269 播放:(A) 同一刻 —— 2426 09-16 從 11:02:00 播到首次鎖漲停(第 61,737 則),每次重畫(#rpIdx 變動的 MutationObserver,
//     在 rpDraw 整段同步改完 DOM 之後觸發)讀中間欄 60 則與成交明細 20 列,逐一比播放段標準答案(rp269_segment_expected.py);
//     1x 與 10x 各播一次。
// (B) 流暢度 —— 同段、不掛讀取,照 #270 的量法(包住 requestAnimationFrame 量每幀回呼、幀間隔、每秒總耗時、長框 > 50 ms),
//     一般 / 展開 × 1x / 10x,另量逐則步進 798 次的同步更新耗時(含強制 layout),與 #270 表格同口徑可比。
// 用法:node verify_playback_sync.mjs <segment.json> <out.json>
import { readFileSync, writeFileSync } from 'node:fs';
import { launch, openPage, openReplay, setFull, drag, NEW_PAGE, REVIEW } from './pp_common.mjs';
// 環境變數 RP_PAGE = 改開回看頁資料夾裡的另一個頁面(量測變體用);RP_SKIP_SYNC=1 = 只量流暢度
const PAGE = process.env.RP_PAGE ? REVIEW + process.env.RP_PAGE : NEW_PAGE;

const [segPath, OUT] = process.argv.slice(2);
const seg = JSON.parse(readFileSync(segPath, 'utf8'));
const T110200 = 11 * 3600000 + 2 * 60000, LOCK_IDX = 61737;
const same = (a, b) => JSON.stringify(a) === JSON.stringify(b);
const q = (arr, p) => { const s = [...arr].sort((x, y) => x - y); return s.length ? s[Math.min(s.length - 1, Math.floor(s.length * p))] : null; };
const summary = arr => ({ n: arr.length, p50: q(arr, 0.5), p95: q(arr, 0.95), p99: q(arr, 0.99), max: arr.length ? Math.max(...arr) : null });

const browser = await launch({ width: 1400, height: 1000 });
const out = { sync: {}, perf: {} };
try {
  const { page, errors } = await openPage(browser, PAGE);
  await openReplay(page, '2426', '2026-09-16');
  const speedBtn = s => page.evaluate(s => document.querySelector(`#tab-replay [data-speed="${s}"]`).click(), s);

  // ---------- (A) 同一刻 ----------
  for (const speed of process.env.RP_SKIP_SYNC ? [] : [1, 10]) {
    await setFull(page, false); await speedBtn(speed); await drag(page, T110200);
    const caps = await page.evaluate(async (LOCK_IDX) => {
      const idxEl = document.getElementById('rpIdx'), caps = [];
      const read = () => ({
        idx: Number(idxEl.textContent.replace(/[^0-9]/g, '')),
        msgs: [...document.querySelectorAll('#rpChg .rp-msg')].map(m => ({ cur: m.classList.contains('cur'), head: [...m.querySelectorAll('.rp-msg-h > span')].map(s => s.textContent), lines: [...m.querySelectorAll('.rp-line')].map(l => ({ dim: l.classList.contains('dim'), text: l.textContent })) })),
        tape: [...document.querySelectorAll('#rpTape tr')].map(tr => ({ cur: tr.classList.contains('cur'), cells: [...tr.children].map(td => td.textContent) })),
      });
      const mo = new MutationObserver(() => caps.push(read())); mo.observe(idxEl, { childList: true, characterData: true, subtree: true });
      const t0 = performance.now(); document.getElementById('rpPlay').click();
      while (Number(idxEl.textContent.replace(/[^0-9]/g, '')) < LOCK_IDX && performance.now() - t0 < 90000) await new Promise(r => setTimeout(r, 50));
      document.getElementById('rpPlay').click(); mo.disconnect();
      return caps;
    }, LOCK_IDX);
    let bad = 0, checked = 0; const firstBad = [];
    for (const c of caps) {
      const e = seg.frames[String(c.idx - 1)];
      if (!e) continue;
      checked++;
      if (!same(c.msgs, e.msgs) || !same(c.tape, e.tape)) { bad++; if (firstBad.length < 3) firstBad.push(c.idx); }
    }
    out.sync[`${speed}x`] = { draws: caps.length, checked, mismatches: bad, firstBad, distinctFrames: new Set(caps.map(c => c.idx)).size, lastIdx: caps.at(-1)?.idx };
    console.log(`同一刻 ${speed}x:重畫 ${caps.length} 次、比對 ${checked}、不符 ${bad}`);
  }

  // ---------- (B) 流暢度 ----------
  for (const full of [false, true]) {
    await setFull(page, full); await drag(page, T110200);
    const r = await page.evaluate(() => {
      const next = document.getElementById('rpNext'), lad = document.getElementById('rpLadder'), costs = [];
      for (let k = 0; k < 798; k++) { const s = performance.now(); next.click(); void lad.offsetHeight; costs.push(performance.now() - s); }
      return { costs, endIdx: document.getElementById('rpIdx').textContent };
    });
    out.perf[`逐則同步更新_${full ? '展開' : '一般'}`] = { ...summary(r.costs), endIdx: r.endIdx };
  }
  await page.evaluate(() => {
    const orig = window.__origRAF = window.requestAnimationFrame.bind(window);
    window.__cb = [];
    window.requestAnimationFrame = cb => orig(ts => { const s = performance.now(); try { cb(ts); } finally { window.__cb.push([s, performance.now() - s]); } });
    window.__loaf = [];
    try { new PerformanceObserver(l => { for (const e of l.getEntries()) window.__loaf.push({ start: e.startTime, dur: e.duration }); }).observe({ type: 'long-animation-frame' }); window.__loafOK = true; } catch (e) { window.__loafOK = false; }
  });
  for (const [full, speed] of [[false, 1], [true, 1], [false, 10], [true, 10]]) {
    await setFull(page, full); await speedBtn(speed); await drag(page, T110200);
    const r = await page.evaluate(async (LOCK_IDX) => {
      window.__cb = []; window.__loaf = [];
      const orig = window.__origRAF, frames = [], idxEl = document.getElementById('rpIdx'), updates = [];
      const mo = new MutationObserver(() => updates.push(performance.now())); mo.observe(idxEl, { childList: true, characterData: true, subtree: true });
      let run = true; const loop = ts => { frames.push(ts); if (run) orig(loop); }; orig(loop);
      const t0 = performance.now(); document.getElementById('rpPlay').click();
      while (Number(idxEl.textContent.replace(/[^0-9]/g, '')) < LOCK_IDX && performance.now() - t0 < 90000) await new Promise(r => setTimeout(r, 50));
      const t1 = performance.now(); document.getElementById('rpPlay').click(); run = false; mo.disconnect();
      const iv = frames.slice(1).map((f, k) => f - frames[k]);
      const cb = window.__cb.filter(([s]) => s >= t0 && s <= t1).map(([, d]) => d);
      const perSec = {}; for (const [s, d] of window.__cb) if (s >= t0 && s <= t1) { const k = Math.floor((s - t0) / 1000); perSec[k] = (perSec[k] || 0) + d; }
      return { ms: Math.round(t1 - t0), cb, iv, perSec: Object.values(perSec), updates: updates.length, loaf: window.__loaf.filter(e => e.start >= t0 && e.start <= t1), loafOK: window.__loafOK };
    }, LOCK_IDX);
    out.perf[`播放_${speed}x_${full ? '展開' : '一般'}`] = { realMs: r.ms, updates: r.updates, 每幀回呼耗時ms: summary(r.cb), 幀間隔ms: summary(r.iv), 每秒回呼總耗時ms: summary(r.perSec), 長框_50ms以上: r.loaf.length, loafSupported: r.loafOK, loafMaxMs: r.loaf.length ? Math.max(...r.loaf.map(e => e.dur)) : 0 };
    console.log(`播放 ${speed}x ${full ? '展開' : '一般'}`, r.ms, 'ms');
  }
  out.consoleErrors = errors;
} finally {
  await browser.close();
}
writeFileSync(OUT, JSON.stringify(out, null, 1));
console.log(JSON.stringify(out, null, 1));
