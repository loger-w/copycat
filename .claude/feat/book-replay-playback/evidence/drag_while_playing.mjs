// #270 review P-03:播放中用真滑鼠按住時間軸拉把拖曳 / 停住,量拉把值是否在「指標位置」與「播放推進」之間抖動。
// 每幀取樣 range.value,換算成拉把像素位置;停住期間(沒有 mousemove)看值怎麼走,移動期間看相鄰幀像素跳動。
// 用法:node drag_while_playing.mjs <out.json>
import { writeFileSync } from 'node:fs';
import { launch, openPage, openReplay, setFull, drag, readState, sleep, NEW_PAGE } from './pp_common.mjs';

const OUT = process.argv[2];
const browser = await launch({ width: 1400, height: 1000 });
const { page, errors } = await openPage(browser, NEW_PAGE);
const res = {};
for (const speed of [1, 10]) {
  await openReplay(page, '2426', '2026-09-16');
  await setFull(page, false);
  await page.click(`#tab-replay [data-speed="${speed}"]`);
  await drag(page, 39600000);
  await page.click('#rpPlay');
  await sleep(300);
  const box = await (await page.$('#rpRange')).boundingBox();
  const geo = await page.evaluate(() => { const r = document.getElementById('rpRange'); return { min: Number(r.min), max: Number(r.max), v: Number(r.value) }; });
  const xOf = v => box.x + 8 + (v - geo.min) / (geo.max - geo.min) * (box.width - 16); // 拉把寬約 16px
  const y = box.y + box.height / 2;
  await page.evaluate(() => { window.__samples = []; const r = document.getElementById('rpRange'); const loop = () => { window.__samples.push([performance.now(), Number(r.value)]); if (window.__sampling) requestAnimationFrame(loop); }; window.__sampling = true; requestAnimationFrame(loop); });
  const x0 = xOf(geo.v + 400 * speed);
  await page.mouse.move(x0, y); await page.mouse.down();
  const tDown = await page.evaluate(() => performance.now());
  for (let k = 1; k <= 20; k++) { await page.mouse.move(x0 + k * 3, y); await sleep(16); }
  const tHold = await page.evaluate(() => performance.now());
  await sleep(1500);
  const tUp = await page.evaluate(() => performance.now());
  await page.mouse.up();
  await sleep(300);
  const after = await readState(page, false);
  const samples = await page.evaluate(() => { window.__sampling = false; return window.__samples; });
  await page.click('#rpPlay');
  const pxPerMs = (box.width - 16) / (geo.max - geo.min);
  const moving = samples.filter(([t]) => t >= tDown && t < tHold).map(([, v]) => v);
  const holding = samples.filter(([t]) => t >= tHold + 50 && t < tUp).map(([, v]) => v);
  const jumps = a => a.slice(1).map((v, i) => Math.abs(v - a[i]) * pxPerMs);
  const backSteps = a => a.slice(1).filter((v, i) => v < a[i]).length;
  res[`${speed}x`] = {
    pxPerMs: +pxPerMs.toExponential(3),
    移動中_相鄰幀拉把位移px_max: moving.length > 1 ? +Math.max(...jumps(moving)).toFixed(3) : null,
    停住_期間值推進ms: holding.length ? holding[holding.length - 1] - holding[0] : null,
    停住_期間拉把位移px: holding.length ? +((holding[holding.length - 1] - holding[0]) * pxPerMs).toFixed(4) : null,
    停住_倒退次數: backSteps(holding), 停住_樣本數: holding.length,
    放開後仍在播放: after.play === 'true',
  };
}
await browser.close();
writeFileSync(OUT, JSON.stringify({ res, errors }, null, 1));
console.log(JSON.stringify({ res, errors }, null, 1));
