/** 訊號規則參數值域的跨語言 parity(CLAUDE.md §4 跨檔契約)。
 *
 *  產生點 `copycat/signal_rules.py::PARAM_SPECS`(唯一擋人的地方:出界 → INVALID_RULE);
 *  本檔測的是前端鏡像 `lib/signal-params.ts::PARAM_FIELDS` 的 `min`/`max`(N055 起前端
 *  也擋值域,好讓使用者知道是哪一格、界在哪)。
 *
 *  兩份表各自漂移的失效樣態**沒有錯誤訊號**:前端界比後端寬 → 使用者拿回一句泛用的
 *  「規則設定不合法」(N055 修的就是這個);前端界比後端窄 → 明明後端收得下的值被
 *  前端擋掉,而畫面上的說明還振振有詞地寫著錯的界。所以以共用 fixture
 *  `tests/fixtures/signal_param_specs.json` 釘住:pytest 側
 *  `tests/test_signal_rules.py::test_param_specs_parity_with_frontend` 與本檔各自對它
 *  斷言,改壞任一邊就只有那一邊紅。
 *
 *  review A8(#101 parity 補完)把契約補齊成同一張:整數鍵(後端 `INT_PARAM_KEYS`)、
 *  冷卻界(`COOLDOWN_MIN/MAX`),以及**前端自己的**「新規則」預設值必須落在值域內、
 *  整數鍵為整數 —— 預設值不合法的失效樣態是「按新增 → 表單空白 / 直接被擋」,正是 N055
 *  要消滅的樣態。
 *
 *  用 `node:fs` 讀而不是 `import` JSON:tsconfig 沒開 `resolveJsonModule`(同
 *  `vp-parity.test.ts` / `overlay-parity.test.ts` 的理由)。 */
import { readFileSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

import { describe, expect, it } from "vitest";

import { COOLDOWN_MAX, COOLDOWN_MIN, PARAM_FIELDS } from "@/lib/signal-params";

interface Fixture {
  specs: Record<string, Record<string, [number, number]>>;
  int_keys: string[];
  cooldown: [number, number];
}

// `import.meta.url` 而不是 `__dirname`:vitest 把測試檔轉成 ESM,`__dirname` 不保證存在
const HERE = path.dirname(fileURLToPath(import.meta.url));
const FIXTURE_PATH = path.resolve(HERE, "../../../tests/fixtures/signal_param_specs.json");

describe("訊號規則參數值域 parity(共用 fixture,pytest 側斷言同一份)", () => {
  const fixture = JSON.parse(readFileSync(FIXTURE_PATH, "utf-8")) as Fixture;

  it("fixture 自身健檢:四種 kind 齊全、含零參數的 limit_lock、int_keys 都是真鍵", () => {
    // 沒有這條的話 fixture 被改瘦(只剩一個 kind)時 parity 仍然全綠 = 空談
    expect(Object.keys(fixture.specs).sort()).toEqual([
      "cdp_cross",
      "limit_lock",
      "surge_crash",
      "vol_burst",
    ]);
    expect(fixture.specs.limit_lock).toEqual({});
    const allKeys = new Set(Object.values(fixture.specs).flatMap((f) => Object.keys(f)));
    for (const key of fixture.int_keys) expect(allKeys.has(key)).toBe(true);
  });

  it("前端 PARAM_FIELDS 的鍵集與 min/max === fixture", () => {
    const actual: Record<string, Record<string, [number, number]>> = {};
    for (const [kind, fields] of Object.entries(PARAM_FIELDS)) {
      actual[kind] = Object.fromEntries(fields.map((f) => [f.key, [f.min, f.max]]));
    }
    expect(actual).toEqual(fixture.specs);
  });

  it("整數鍵集合 === fixture.int_keys(後端拒非整數的鍵,前端要在送出前擋)", () => {
    const actual = Object.values(PARAM_FIELDS)
      .flatMap((fields) => fields.filter((f) => f.integer).map((f) => f.key))
      .sort();
    expect(actual).toEqual([...new Set(fixture.int_keys)].sort());
  });

  it("冷卻界 === fixture.cooldown", () => {
    expect([COOLDOWN_MIN, COOLDOWN_MAX]).toEqual(fixture.cooldown);
  });

  it("每個欄位的預設值落在自己的 [min, max] 內;整數鍵的預設值是整數", () => {
    for (const fields of Object.values(PARAM_FIELDS)) {
      for (const f of fields) {
        const v = Number(f.default);
        expect(Number.isFinite(v), `${f.key} 預設值不是數字:${f.default}`).toBe(true);
        expect(v >= f.min && v <= f.max, `${f.key} 預設值 ${v} 不在 [${f.min}, ${f.max}]`).toBe(true);
        if (f.integer) expect(Number.isInteger(v), `${f.key} 是整數鍵但預設值 ${v}`).toBe(true);
      }
    }
  });
});
