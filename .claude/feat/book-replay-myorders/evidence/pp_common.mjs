// #269 驗證共用(沿 #270 pp_common):chrome-devtools-mcp 內嵌的 puppeteer 開獨立暫存 profile 的 headless Chrome,
// file:// 開回看頁;每個頁面各自一個 browser context。
// 新頁 = 測試頁 viewer-cdp.269.html(工作模板 + 現用資料 blob,外掛檔讀 viewer-cdp-book-269 的 v2);
// 舊頁 = 現用 viewer-cdp.html 的複本 viewer-cdp.pre269.html(讀 viewer-cdp-book 的 v1)。兩頁資料 blob 相同 ——
// 測試頁由 build_stage_page.py 取「當下」現用頁的 blob,所以現用頁被重建過就要一起重新複製舊頁(09-17 15:36 另一個 session 重建過)。
// 環境變數 RP_NEW_PAGE / RP_OLD_PAGE = 改開回看頁資料夾裡的其他頁(切換後驗正式頁用)。
//
// pr-279 review F-28:不給 userDataDir(不用 mkdtemp 自建)—— 同一份 puppeteer bundle 實測過,不給時
// 會自建 %TEMP%\puppeteer_dev_chrome_profile-* 暫存 profile 且 close() 後幾秒內自動刪掉;自己給的話
// close() 不會清,%TEMP% 下 rp269- / rp270- 開頭的暫存資料夾一路累積到 47 個、687 MB。
// 每次 launch() 呼叫仍各自拿到一份獨立的暫存 profile,只是改由 puppeteer 自己管理生命週期。
import { puppeteer } from 'file:///C:/Users/USER/AppData/Local/npm-cache/_npx/70a308a69d028c4a/node_modules/chrome-devtools-mcp/build/src/third_party/index.js';

export const REVIEW = 'file:///C:/Users/USER/Documents/copycat-trading-review/';
export const NEW_PAGE = REVIEW + (process.env.RP_NEW_PAGE || 'viewer-cdp.269.html');
export const OLD_PAGE = REVIEW + (process.env.RP_OLD_PAGE || 'viewer-cdp.pre269.html');

export async function launch(viewport = { width: 1400, height: 1000 }) {
  return puppeteer.launch({
    executablePath: 'C:/Program Files/Google/Chrome/Application/chrome.exe',
    headless: true,
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

export async function openReplay(page, code, date) {
  await selectDay(page, code, date);
  await clickTab(page, 'replay');
  await page.waitForFunction(key => {
    const box = document.getElementById('tab-replay'), clock = document.getElementById('rpClock');
    return box.dataset.key === key && clock && clock.textContent !== '';
  }, { timeout: 90000 }, `${code}|${date}`);
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

// 走到第 index 則(0 起算):先拖到該則收到時刻(落在同毫秒最後一則),再按「前一則」退回
export async function goIndex(page, index, recvMs, lastSameMs) {
  await drag(page, recvMs);
  for (let k = lastSameMs; k > index; k--) {
    await page.evaluate(() => document.getElementById('rpPrev').click());
  }
  await page.evaluate(() => new Promise(res => requestAnimationFrame(() => requestAnimationFrame(res))));
}

export async function readReplay(page) {
  return page.evaluate(() => {
    const q = id => document.getElementById(id);
    const msgs = [...document.querySelectorAll('#rpChg .rp-msg')].map(m => ({
      cur: m.classList.contains('cur'),
      head: [...m.querySelectorAll('.rp-msg-h > span')].map(s => s.textContent),
      lines: [...m.querySelectorAll('.rp-line')].map(l => ({ dim: l.classList.contains('dim'), text: l.textContent })),
    }));
    const tape = [...document.querySelectorAll('#rpTape tr')].map(tr => ({
      cur: tr.classList.contains('cur'), cells: [...tr.children].map(td => td.textContent),
    }));
    return { idx: q('rpIdx').textContent, lab: q('rpClock').textContent, recv: q('rpRecv').textContent, msgs, tape };
  });
}

export const sleep = ms => new Promise(r => setTimeout(r, ms));
