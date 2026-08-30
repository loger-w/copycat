import { msUntilNextLocalDate } from "@/lib/trading-calendar";

/** 日 K 的新鮮度政策(bug/futures-daily-bars-rollover → bug/daily-bars-siblings-rollover):
 *  「同一個本機日曆日內不過期、跨午夜 + slack 重抓、失敗 60 s 重試」三顆常數 / 函式的唯一住處。
 *
 *  **不併進 `lib/trading-calendar.ts`**:那邊是純日曆算術(下一個午夜幾毫秒);這邊是 TanStack Query
 *  的 staleTime / refetchInterval 政策(slack、render 重排、error 重試),理由不同、變動理由也不同。
 *  **不留在 `hooks/useFuturesBars.ts`**(08-31 user 拍板,review S-F1 / P-F6):三支日 K hook 平行
 *  import,兩支兄弟不該 runtime 依賴期貨 hook 模組。
 *
 *  讀者:`hooks/useFuturesBars.ts`(日 K,`subscribed: active` 退訂即無計時器)、`hooks/useMarketBars.ts`
 *  (日 / 週 / 月 K,日 K 分支整段不吃 `active`)、`hooks/useStockBars.ts`(日 K,`barsPollInterval` 先判)。
 *  測試在三支 hook 的 `*.test.ts(x)` 跨日 describe(seam = hook;本檔零 React 依賴、無自己的測試檔)。 */

/** 午夜過後再等這麼久才問日 K。**沒有硬依據**:同一台機器上前後端牆鐘無時差,後端
 *  `date.today()` 在 00:00:00 就翻頁;這一分鐘只擋計時器排程誤差與「恰在同一毫秒」那類極端
 *  情況,失效方向安全(最壞是新基準晚一分鐘到)。值由測試釘住(00:00:30 仍不打、00:01:01 打)。
 *  slack 是「界」的一部分、不是加在界之後的等待 —— 推導見 `msUntilDayRollover`。 */
export const DAY_ROLLOVER_SLACK_MS = 60_000;

/** 日 K 的有效期 = **同一個本機日曆日**(bug/futures-daily-bars-rollover):`from` 起算,到
 *  它之後的第一個日曆日 00:00 + `DAY_ROLLOVER_SLACK_MS` 的毫秒數。
 *
 *  讀者三支:`useFuturesBars`、`useMarketBars`(日 / 週 / 月 K)、`useStockBars`(日 K)—— 同一個 bug
 *  形狀(bug/daily-bars-siblings-rollover),症狀與界的由來只寫這一處,兩支兄弟的 doc 指過來。
 *
 *  舊碼 `staleTime: Infinity` + 不輪詢:看盤日常是 preview 整天掛著(CLAUDE.md §1),跨過午夜
 *  那份 cache 永不失效 → 新交易日的 CDP / MA 疊線(`lib/futures-overlay.ts`,基準 = 錨定日前
 *  一交易日)拿的是**昨天早上抓的那份**:昨天的 D bar 停在盤中部分值(或根本還沒有),而
 *  錨定日判準只保證「不畫到未來」,對「停在更早的一天」無感 —— 畫面只是幾條位置不對的線。
 *
 *  **界是日曆午夜,不是 15:00 錨定日翻頁**:後端 `server/bars.py::build_period` 的日 K cache
 *  鍵是 `date.today()`,15:01–24:00 之間再怎麼問都是同一份(那一段留 next-time);午夜一過
 *  後端才有新料。三條路徑同一把尺(界的由來只寫這一處,helper 與測試指過來):
 *  - `refetchInterval`:人一直在 tab 上 → 午夜到了自己打一發(函式形式,每次結果落地後
 *    重算到下一個午夜;不是固定 24 h —— 那會把「掛載時刻」當午夜,20:00 開的分頁整個
 *    次日交易日都用舊基準)。**而且每一次 render 也重算**:react-query 的 `useBaseQuery` 每 render
 *    都 `observer.setOptions(...)`,`QueryObserver.setOptions` 見回值一變就 clear + 重排計時器
 *    (@tanstack/query-core 5.101 核過);`FuturesChart` 每則 WS 訊息重繪一次、夜盤正在跑 —— 所以
 *    (a) 界必須**嚴格在 from 之後**(00:00–00:01 內求值回「到今天 00:01」,不是「到明天」;
 *    pr-151-review F-01:修前那 60 秒內任一重繪就把那一發推到隔天,主情境沒修好);
 *    (b) 要以「現在」算,**不以 `dataUpdatedAt`**:那版跨 render 穩定,但 setInterval 的週期從
 *    「重新武裝的時刻」起算,09:00 抓、20:00 切回會武裝 15 h、11:00 才打(模擬實測);
 *    (c) 回值秒級量化(pr-151-review F-02):同一秒內的重繪回同值,計時器不再每 render 重排。
 *  - `staleTime`:切走的 observer 是退訂(沒計時器)、背景分頁的 interval tick 被 focus 閘
 *    跳過(TQ 預設 `refetchIntervalInBackground: false`)—— 這兩條都靠「這份是昨天抓的」
 *    才能在切回 / 回前景時補上。以 `dataUpdatedAt` 為起點算到它之後的第一個午夜,不是以
 *    現在算(否則每次判定都會把過期點往後推)。
 *  尚無資料不用守:TQ `Query.isStaleByTime` 第一條對 `state.data === undefined` 直接判過期,
 *  `dataUpdatedAt` 要到第三條 `timeUntilStale` 才用到;本 query 無 `initialData` / `setQueryData`,
 *  `data` 有值 ⇔ `dataUpdatedAt > 0`(pr-151-review F-04 改正:不是 `!updatedAt`)。
 *
 *  算法:界 B_k = 日曆日 k 的 00:00 + slack;回「第一個 B_k > from」− from。`from − slack` 到下一個
 *  午夜的距離正好等於 `from` 到下一個 B_k 的距離,且 `msUntilNextLocalDate` 恆 > 0 保證嚴格在後。
 *  再 ceil 到整秒:回值 ≥ 真距離(不會早於界打)、最多晚 1 s;同一秒內重繪回同值。
 *  `staleTime` 吃同一支(以 `dataUpdatedAt` 起算)的連帶:資料若在 00:00–00:01 內落地(error 重試那條路),
 *  stale 點是**今天** 00:01 而不是明天 —— 有界(那一發落地後下一界即明天,不成迴圈)、方向安全(多打一發)。 */
export function msUntilDayRollover(from: number): number {
  const ms = msUntilNextLocalDate(new Date(from - DAY_ROLLOVER_SLACK_MS));
  return Math.ceil(ms / 1000) * 1000;
}

/** 日 K 那一發失敗(`retry: 1` 用完)後的重試節奏。沒有這條的話 interval 會照樣重算成
 *  「到下一個午夜」—— 00:01 那一發碰上 TC4 忙就整個交易日停在昨天的基準,與修前同一個症狀。
 *  與分 K 輪詢 `POLL_MS` 的 60 s **數值相同,但不吃時段閘**(分 K 那條包著 `inFuturesAllDayHours()`),且
 *  `retry: 1` 讓每輪其實是兩發:失效方向選「多打」不選「整天不救」。
 *  **只在 HTTP 非 2xx 才走到這條**(`fetchBars` throw → TQ error):`/api/market/bars` 的 503 只有
 *  `NOT_READY`(index 未就緒);TC4 斷線 / 慢是 200 + `status: disconnected|timeout` 降級 payload,
 *  不進 error,所以「TC4 整個週末沒開」**不會**每分鐘兩發 —— 只有後端沒起來時才會(每個掛著的
 *  日 K query 各兩發 / 分鐘;08-30 記的「期貨 tab 開著 = 每分鐘兩發 503」是那種情況,已知情)。
 *  讀者三支:`useFuturesBars`(退訂即無計時器)、`useMarketBars`(日 / 週 / 月 K,**不吃 `active`**,見該檔)、
 *  `useStockBars`(日 K,本來就無閘)—— bug/daily-bars-siblings-rollover。 */
export const DAY_ERROR_RETRY_MS = 60_000;
