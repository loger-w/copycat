// #270 截圖:重播分頁控制列各狀態 + 深色 + 390 寬(同時量是否有水平捲動)。
// 用法:node screens.mjs <輸出資料夾>
import { launch, openPage, openReplay, setFull, drag, readState, sleep, NEW_PAGE } from './pp_common.mjs';

const DIR = process.argv[2].replace(/\\/g, '/').replace(/\/$/, '');
const DAY = '2026-09-16';
const shot = async (page, name) => {
  const el = await page.$('section.bottom');
  await el.screenshot({ path: `${DIR}/${name}.png` });
};
const out = {};
const browser = await launch({ width: 1400, height: 1000 });
const { page, errors } = await openPage(browser, NEW_PAGE);
await page.emulateMediaFeatures([{ name: 'prefers-color-scheme', value: 'light' }]); // headless 會沿用系統深色偏好,淺色要明講
await openReplay(page, '2426', DAY);
await setFull(page, false);
await drag(page, 39764025); await page.keyboard.press('ArrowLeft');
out.step2 = await readState(page, false); await shot(page, 'replay-2426-110244-step2');
await page.click('#tab-replay [data-speed="5"]'); await drag(page, 39760000); await page.click('#rpPlay'); await sleep(700);
out.playing = await readState(page, false); await shot(page, 'replay-2426-playing-5x');
await page.click('#rpLock'); out.lock = await readState(page, false); await shot(page, 'replay-2426-lock');
await openReplay(page, '2344', DAY); out.nolock = await readState(page, false); await shot(page, 'replay-2344-nolock');
await page.emulateMediaFeatures([{ name: 'prefers-color-scheme', value: 'dark' }]);
await openReplay(page, '2426', DAY); await page.click('#rpLock'); await shot(page, 'replay-2426-lock-dark');
await page.emulateMediaFeatures([{ name: 'prefers-color-scheme', value: 'light' }]);
await page.setViewport({ width: 390, height: 900 }); await sleep(500);
out.narrow = await page.evaluate(() => ({ scrollWidth: document.documentElement.scrollWidth, clientWidth: document.documentElement.clientWidth, innerWidth: window.innerWidth,
  ctrlRight: Math.round(document.querySelector('.rp-ctrl').getBoundingClientRect().right), ctrlHeight: Math.round(document.querySelector('.rp-ctrl').getBoundingClientRect().height) }));
await shot(page, 'replay-2426-narrow-390');
await browser.close();
console.log(JSON.stringify({ step2: [out.step2.idx, out.step2.lab], playing: [out.playing.play, out.playing.playText, out.playing.speed], lock: [out.lock.idx, out.lock.lab, out.lock.play], nolock: [out.nolock.lockText, out.nolock.lockDis], narrow: out.narrow, errors }, null, 1));
