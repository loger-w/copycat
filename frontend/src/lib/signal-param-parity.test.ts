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
 *  用 `node:fs` 讀而不是 `import` JSON:tsconfig 沒開 `resolveJsonModule`(同
 *  `vp-parity.test.ts` / `overlay-parity.test.ts` 的理由)。 */
import { readFileSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

import { describe, expect, it } from "vitest";

import { PARAM_FIELDS } from "@/lib/signal-params";

interface Fixture {
  specs: Record<string, Record<string, [number, number]>>;
}

// `import.meta.url` 而不是 `__dirname`:vitest 把測試檔轉成 ESM,`__dirname` 不保證存在
const HERE = path.dirname(fileURLToPath(import.meta.url));
const FIXTURE_PATH = path.resolve(HERE, "../../../tests/fixtures/signal_param_specs.json");

describe("訊號規則參數值域 parity(共用 fixture,pytest 側斷言同一份)", () => {
  const fixture = JSON.parse(readFileSync(FIXTURE_PATH, "utf-8")) as Fixture;

  it("fixture 自身健檢:四種 kind 齊全、含零參數的 limit_lock", () => {
    // 沒有這條的話 fixture 被改瘦(只剩一個 kind)時 parity 仍然全綠 = 空談
    expect(Object.keys(fixture.specs).sort()).toEqual([
      "cdp_cross",
      "limit_lock",
      "surge_crash",
      "vol_burst",
    ]);
    expect(fixture.specs.limit_lock).toEqual({});
  });

  it("前端 PARAM_FIELDS 的鍵集與 min/max === fixture", () => {
    const actual: Record<string, Record<string, [number, number]>> = {};
    for (const [kind, fields] of Object.entries(PARAM_FIELDS)) {
      actual[kind] = Object.fromEntries(fields.map((f) => [f.key, [f.min, f.max]]));
    }
    expect(actual).toEqual(fixture.specs);
  });
});
