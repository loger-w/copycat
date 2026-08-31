import { msUntilNextLocalDate } from "@/lib/trading-calendar";

/** 日 K 的新鮮度政策(bug/futures-daily-bars-rollover → bug/daily-bars-siblings-rollover):
 *  「同一個本機日曆日內不過期、跨午夜 + slack 重抓、失敗 60 s 重試」——**政策的唯一住處**,
 *  公開面只有 `dayBarsStaleTime` / `dayBarsRefetchInterval` 兩支,hook 只接線(pr-159-review F-02:
 *  先前只收常數、兩行政策運算式仍三支 hook 各一份 —— 「改一支、其他兩支測試照綠」正是
 *  bug/daily-bars-siblings-rollover 的病因,收進來後改政策只改本檔、三支同動)。
 *  常數與 `msUntilDayRollover` 不 export:整個 src/ 零外部讀者(pr-159-review F-06),
 *  測試釘界用牆鐘字面值、不 import 常數(frontend-testing 慣例)。
 *
 *  **不併進 `lib/trading-calendar.ts`**:那邊是純日曆算術(下一個午夜幾毫秒);這邊是 TanStack Query
 *  的 staleTime / refetchInterval 政策(slack、render 重排、error 重試),理由不同、變動理由也不同。
 *  **不留在 `hooks/useFuturesBars.ts`**(08-31 user 拍板,review S-F1 / P-F6):三支日 K hook 平行
 *  import,兩支兄弟不該 runtime 依賴期貨 hook 模組。
 *
 *  讀者(**唯一清單**,下方函式 doc 不重列 —— pr-159-review F-08):
 *  - `hooks/useFuturesBars.ts` 日 K:`subscribed: active`,退訂即無計時器,切回靠 staleTime 補;
 *  - `hooks/useMarketBars.ts` 日 / 週 / 月 K:整段不吃 `active`(tab hidden 保留,理由見該檔);
 *  - `hooks/useStockBars.ts` 日 K:`barsPollInterval` 先判(SC-4 的 20 s 空態重試優先於日界),
 *    它回 false 才進本檔;各 hook 的分 K 輪詢另有**自己的**時段閘(見各檔),不經過本檔。
 *  測試在三支 hook 的 `*.test.ts(x)` 跨日 describe(seam = hook;本檔零 React 依賴、無自己的測試檔)。 */

/** 午夜過後再等這麼久才問日 K。**沒有硬依據**:同一台機器上前後端牆鐘無時差,後端
 *  `date.today()` 在 00:00:00 就翻頁;這一分鐘只擋計時器排程誤差與「恰在同一毫秒」那類極端
 *  情況,失效方向安全(最壞是新基準晚一分鐘到)。值由測試釘住(00:00:30 仍不打、00:01:01 打)。
 *  slack 是「界」的一部分、不是加在界之後的等待 —— 推導見 `msUntilDayRollover`。 */
const DAY_ROLLOVER_SLACK_MS = 60_000;

/** 日 K 的有效期 = **同一個本機日曆日**(bug/futures-daily-bars-rollover):`from` 起算,到
 *  它之後的第一個日曆日 00:00 + `DAY_ROLLOVER_SLACK_MS` 的毫秒數。
 *
 *  讀者見檔頭(同一個 bug 形狀 —— bug/daily-bars-siblings-rollover;症狀與界的由來只寫這一處)。
 *
 *  舊碼 `staleTime: Infinity` + 不輪詢:看盤日常是 preview 整天掛著(CLAUDE.md §1),跨過午夜
 *  那份 cache 永不失效 → 新交易日的 CDP / MA 疊線(`lib/futures-overlay.ts`,基準 = 錨定日前
 *  一交易日)拿的是**昨天早上抓的那份**:昨天的 D bar 停在盤中部分值(或根本還沒有),而
 *  錨定日判準只保證「不畫到未來」,對「停在更早的一天」無感 —— 畫面只是幾條位置不對的線。
 *
 *  **界是日曆午夜,不是 15:00 錨定日翻頁**:一把尺服務三支 hook,而 market / stock 的日 K
 *  沒有錨定日概念。後端自 bug/futures-daily-cache-night 起有 14:00 定稿界(界前快照過界
 *  作廢一次,`server/bars.py::DAILY_FINAL_TIME`),15:00 後再問**拿得到**定稿 —— 但本檔
 *  staleTime 到午夜才過期,掛著不動的期貨分頁 15:01–24:00 仍用早上快照畫 CDP(F5 即正確);
 *  期貨那支要不要另吃 15:00 界是設計題,留 docs/next-time.md 08-31 節。
 *  三條路徑同一把尺(界的由來只寫這一處,helper 與測試指過來):
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
function msUntilDayRollover(from: number): number {
  const ms = msUntilNextLocalDate(new Date(from - DAY_ROLLOVER_SLACK_MS));
  return Math.ceil(ms / 1000) * 1000;
}

/** 日 K 那一發失敗(`retry: 1` 用完)後的重試節奏。沒有這條的話 interval 會照樣重算成
 *  「到下一個午夜」—— 00:01 那一發碰上後端不通就整個交易日停在昨天的基準,與修前同一個症狀。
 *  與三支 hook 各自分 K 輪詢的 60 s 數值相同但**互不同源**(各檔私有 `POLL_MS`),也不吃它們的時段閘;
 *  `retry: 1` 讓每輪其實是兩發:失效方向選「多打」不選「整天不救」。
 *  **只在 HTTP 非 2xx 才走到這條**(各 hook 的 fetch 對非 2xx throw → TQ error;pr-159-review F-07 口徑):
 *  TC4 斷線 / 慢在 `/api/market/bars` 與 `/api/stock/bars` 都是 200 降級 payload、不進 error
 *  (`futures_engine.bars_range` / `stock_engine.bars_range` 吞例外回空);非 2xx 的實際來源 =
 *  引擎未就緒 503、參數類 400(含 stock 的 `BAD_CODE`,永久性錯誤、重試不會自己好,但前端與自選
 *  同一把 `_CODE_RE` 尺、實務罕見)、全域 exception handler 502。「TC4 整個週末沒開」**不會**每分鐘
 *  兩發 —— 只有後端沒起來時才會(每個掛著的日 K query 各兩發 / 分鐘,已知情)。
 *  讀者見檔頭。 */
const DAY_ERROR_RETRY_MS = 60_000;

/** 三支 hook 的 `staleTime` / `refetchInterval` 都以 TQ 的 Query 物件呼叫;這裡只讀用得到的兩格,
 *  結構型別、不 import TQ 泛型(呼叫端的 `Query<MarketBars>` / `Query<BarsPayload>` 皆可指派)。 */
interface DayBarsQuery {
  state: {
    status: "pending" | "error" | "success";
    dataUpdatedAt: number;
    data?: { bars: readonly unknown[] } | undefined;
  };
}

/** 日 K `staleTime`:以「上次落地時刻」算到它之後的第一個午夜。以 `dataUpdatedAt` 起算而不是
 *  「現在」的理由、與 refetchInterval 恰好相反的理由,都在 `msUntilDayRollover` doc。 */
export function dayBarsStaleTime(q: DayBarsQuery): number {
  return msUntilDayRollover(q.state.dataUpdatedAt);
}

/** 日 K `refetchInterval`:失敗 → 60 s 重試(`DAY_ERROR_RETRY_MS`);否則到下一個午夜——以「現在」算、
 *  **不吃 `dataUpdatedAt`**(鐵律 (b),推導見 `msUntilDayRollover`)。
 *  refetch 失敗時 TQ 保留舊 data 但 status 轉 error(v5 RefetchErrorResult)。
 *
 *  `retryEmpty`(pr-159-review F-01,user 拍板 1a):**200 + 空 bars 要不要視同失敗**。
 *  market / futures 的 D(/W/M)路徑後端未三態化 —— TC4 不可用時回 200 + 空 bars 不 raise,
 *  TQ 判 success、空快照蓋掉好資料,而下一發已排到明天、staleTime 整天不過期、回焦 refetch 被
 *  `isStaleByTime` 擋 → 圖空白一整天、零自救。兩支傳 `true`:空 = 「拿了等於沒拿」,吃同一個
 *  60 s 節奏(資料非空即回到「下一個午夜」,不成迴圈;成本上界 = TC4 整天不可用時每分鐘一發,
 *  與 error 重試同級)。`useStockBars` 傳 `false`:它的空態語意由 `status` 三態 + `barsPollInterval`
 *  接手(空 + 非 ok → 20 s 已在本函式之前先判;空 + ok = 「真無資料」的刻意不輪詢,SC-4),
 *  在這裡再開 60 s 會把「真無資料」變成整天空轉 —— 兩種空不是同一種空。 */
export function dayBarsRefetchInterval(q: DayBarsQuery, opts: { retryEmpty: boolean }): number {
  if (q.state.status === "error") return DAY_ERROR_RETRY_MS;
  const data = q.state.data;
  if (opts.retryEmpty && data !== undefined && data.bars.length === 0) return DAY_ERROR_RETRY_MS;
  return msUntilDayRollover(Date.now());
}
