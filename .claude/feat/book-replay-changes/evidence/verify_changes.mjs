// #269:測試頁逐則比對標準答案(rp269_expected.py 產的 JSON)—— 中間欄 60 則、成交明細 20 列、目前這則標亮。
// 走到第 i 則 = 拖到它的收到時刻(落在同毫秒最後一則)再按「前一則」退回;另竄改標準答案 3 處確認比對抓得到。
// 用法:node verify_changes.mjs <expected.json> <result.json>
import { readFileSync, writeFileSync } from 'node:fs';
import { launch, openPage, openReplay, goIndex, readReplay, NEW_PAGE } from './pp_common.mjs';

const [expPath, outPath] = process.argv.slice(2);
const { cases } = JSON.parse(readFileSync(expPath, 'utf8'));
const qty = n => n.toLocaleString('en-US');
const same = (a, b) => JSON.stringify(a) === JSON.stringify(b);

// 竄改標準答案 3 處(比對腳本必須抓到)
const tamper = [0, Math.floor(cases.length / 2), cases.length - 1];
const tampered = new Set(tamper.map(k => `${cases[k].date}|${cases[k].code}|${cases[k].i}`));
const exp = cases.map((c, k) => {
  if (!tamper.includes(k)) return c;
  const d = JSON.parse(JSON.stringify(c));
  if (k === tamper[0]) d.msgs[0].head[0] += '(竄改)';
  else if (k === tamper[1]) d.tape[0].cells[d.tape[0].cells.length - 1] += '(竄改)';
  else d.msgs[d.msgs.length - 1].lines[0].dim = !d.msgs[d.msgs.length - 1].lines[0].dim;
  return d;
});

// pr-279 review F-26:被竄改的 3 則原本只拿竄改版比,只要有任何不符就算「抓到竄改」,
// 從沒對照過原始標準答案 —— 如果那一則同時真的有 bug,會被竄改的差異蓋掉、不會進 mismatches。
// 改成每一則都先比原始 cases[k](真不符才進 mismatches),被竄改的 3 則另外再比竄改版確認抓得到。
function diffAgainst(st, ref) {
  const problems = [];
  if (st.idx !== qty(ref.i + 1)) problems.push(`則號 ${st.idx} ≠ ${qty(ref.i + 1)}`);
  if (!same(st.msgs, ref.msgs)) {
    const k = ref.msgs.findIndex((m, n) => !same(m, st.msgs[n]));
    problems.push(`中間欄第 ${k} 組不同:頁面 ${JSON.stringify(st.msgs[k])} / 標準 ${JSON.stringify(ref.msgs[k])}`);
  }
  if (!same(st.tape, ref.tape)) {
    const k = ref.tape.findIndex((r, n) => !same(r, st.tape[n]));
    problems.push(`成交明細第 ${k} 列不同:頁面 ${JSON.stringify(st.tape[k])} / 標準 ${JSON.stringify(ref.tape[k])}`);
  }
  return problems;
}

const browser = await launch({ width: 1400, height: 1000 });
const result = { total: 0, mismatches: [], tampered_caught: [], errors: [] };
try {
  const { page, errors } = await openPage(browser, NEW_PAGE);
  let opened = '';
  for (let k = 0; k < exp.length; k++) {
    const c = exp[k];
    const orig = cases[k];
    const key = `${c.code}|${c.date}`;
    if (key !== opened) { await openReplay(page, c.code, c.date); opened = key; }
    await goIndex(page, c.i, c.recv, c.land);
    const st = await readReplay(page);
    result.total++;
    const id = `${c.date}|${c.code}|${c.i}`;
    const realProblems = diffAgainst(st, orig);
    if (realProblems.length) result.mismatches.push({ id, problems: realProblems });
    if (tampered.has(id)) {
      const tamperProblems = diffAgainst(st, c);
      if (tamperProblems.length) result.tampered_caught.push(id);
    }
  }
  result.errors = errors;
} finally {
  await browser.close();
}
writeFileSync(outPath, JSON.stringify(result, null, 1));
console.log(`比對 ${result.total} 則,不符 ${result.mismatches.length},竄改抓到 ${result.tampered_caught.length}/3,console 錯誤 ${result.errors.length}`);
for (const m of result.mismatches.slice(0, 5)) console.log(m.id, m.problems.join(' || ').slice(0, 600));
