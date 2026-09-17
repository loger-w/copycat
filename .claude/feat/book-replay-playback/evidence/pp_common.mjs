// #270 驗證共用:以 chrome-devtools-mcp 內嵌的 puppeteer 開獨立暫存 profile 的 headless Chrome(DevTools MCP 的預設 profile
// 被另一個 session 的瀏覽器占用),file:// 直接開回看頁;每個頁面各自一個 browser context(localStorage 不互通)。
import { puppeteer } from 'file:///C:/Users/USER/AppData/Local/npm-cache/_npx/70a308a69d028c4a/node_modules/chrome-devtools-mcp/build/src/third_party/index.js';
import { mkdtempSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';

export const REVIEW = 'file:///C:/Users/USER/Documents/copycat-trading-review/';
export const NEW_PAGE = REVIEW + 'viewer-cdp.html';
export const OLD_PAGE = REVIEW + 'viewer-cdp.pre270.html'; // 改前備份 .bak-20260917-pre270 複製成 .html(.bak 副檔名 Chrome 當純文字開)

export async function launch(viewport = { width: 1400, height: 1000 }) {
  return puppeteer.launch({
    executablePath: 'C:/Program Files/Google/Chrome/Application/chrome.exe',
    headless: true,
    userDataDir: mkdtempSync(join(tmpdir(), 'rp270-')),
    defaultViewport: viewport,
  });
}

export async function openPage(browser, url) {
  const ctx = await browser.createBrowserContext();
  const page = await ctx.newPage();
  const errors = [];
  page.on('pageerror', e => errors.push('pageerror: ' + String(e)));
  page.on('console', m => { if (m.type() === 'error' || m.type() === 'warn') errors.push(m.type() + ': ' + m.text()); });
  page.on('requestfailed', r => errors.push('requestfailed: ' + decodeURI(r.url()).replace(REVIEW, '') + ' ' + (r.failure()?.errorText ?? '')));
  await page.goto(url, { waitUntil: 'load' });
  await page.waitForFunction(() => document.querySelector('#codeList .code'), { timeout: 60000 });
  return { page, errors };
}

export async function selectDay(page, code, date) {
  await page.evaluate((code, date) => {
    const ds = document.getElementById('dateSel'), cs = document.getElementById('codeSel');
    if (ds.value !== date) { ds.value = date; ds.dispatchEvent(new Event('change')); }
    if (cs.value !== code) { cs.value = code; cs.dispatchEvent(new Event('change')); }
  }, code, date);
}

export async function clickTab(page, tab) {
  await page.evaluate(tab => document.querySelector(`.tabs button[data-tab="${tab}"]`).click(), tab);
}

// 開重播分頁並等掛載完成(tab-replay 的 data-key = 代號|日期 且標籤已填;標籤新舊頁都有,舊頁沒有「第幾則」)
export async function openReplay(page, code, date) {
  await selectDay(page, code, date);
  await clickTab(page, 'replay');
  await page.waitForFunction(key => {
    const box = document.getElementById('tab-replay'), clock = document.getElementById('rpClock');
    return box.dataset.key === key && clock && clock.textContent !== '';
  }, { timeout: 60000 }, `${code}|${date}`);
}

export async function setFull(page, on) {
  await page.evaluate(on => {
    const b = document.getElementById('rpFull');
    if ((b.textContent === '展開漲停–跌停') === on) b.click();
  }, on);
}

// 拖曳時間軸 = 設值 + input 事件;重畫排在下一個 animation frame,等兩幀再讀
export async function drag(page, t) {
  await page.evaluate(t => {
    const r = document.getElementById('rpRange');
    r.value = String(t);
    r.dispatchEvent(new Event('input', { bubbles: true }));
    return new Promise(res => requestAnimationFrame(() => requestAnimationFrame(res)));
  }, t);
}

export async function readState(page, withRows = true) {
  return page.evaluate(withRows => {
    const q = id => document.getElementById(id);
    const pxB = q('rpPx').querySelector('b');
    return {
      idx: q('rpIdx').textContent, lab: q('rpClock').textContent, kind: q('rpKind').textContent, recv: q('rpRecv').textContent,
      px: pxB ? pxB.textContent : null, mkt: q('rpMkt').textContent, range: Number(q('rpRange').value),
      play: q('rpPlay').getAttribute('aria-pressed'), playText: q('rpPlay').textContent, playDis: q('rpPlay').disabled,
      prevDis: q('rpPrev').disabled, nextDis: q('rpNext').disabled, lockText: q('rpLock').textContent, lockDis: q('rpLock').disabled,
      speed: [...document.querySelectorAll('#tab-replay [data-speed]')].filter(b => b.getAttribute('aria-pressed') === 'true').map(b => b.dataset.speed),
      date: q('dateSel').value, code: q('codeSel').value, key: q('tab-replay').dataset.key,
      rows: withRows ? [...document.querySelectorAll('#rpLadder .rp-row[data-p]')].map(r => [r.dataset.p,
        r.querySelector('.rp-q.buy .rp-n')?.textContent ?? '', r.querySelector('.rp-q.sell .rp-n')?.textContent ?? '']) : null,
    };
  }, withRows);
}

export const num = s => Number(String(s).replace(/[^0-9]/g, ''));
export const sleep = ms => new Promise(r => setTimeout(r, ms));
