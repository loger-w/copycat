import { launch, openPage, openReplay, drag, REVIEW } from
  'file:///C:/side-project/copycat/.claude/worktrees/fix-pr-279-review-followups/.claude/feat/book-replay-changes/evidence/pp_common.mjs';

const browser = await launch({ width: 1500, height: 1050 });
try {
  const { page } = await openPage(browser, REVIEW + 'viewer-cdp.html');
  await openReplay(page, '2305', '2026-09-16');
  await drag(page, 33141572); // 撮合那一則 = 標亮組,它的變動行是淡色
  const r = await page.evaluate(() => {
    const cs = getComputedStyle(document.documentElement);
    const dim = document.querySelector('#rpChg .rp-msg.cur .rp-line.dim');
    const plain = document.querySelector('#rpChg .rp-msg:not(.cur) .rp-line.dim');
    return {
      cur: dim ? getComputedStyle(dim).color : null,
      other: plain ? getComputedStyle(plain).color : null,
      muted: cs.getPropertyValue('--muted').trim(),
      ink2: cs.getPropertyValue('--ink-2').trim(),
      text: dim ? dim.textContent.slice(0, 20) : null,
    };
  });
  console.log(JSON.stringify(r));
  console.log(r.cur && r.other && r.cur !== r.other ? 'PASS 標亮組淡色行已提亮' : 'FAIL 淡色行沒提亮');
} finally {
  await browser.close();
}
