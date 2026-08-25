/** `window.localStorage` 的**唯一出口**(N022)。
 *
 *  **為什麼要有這一層**:localStorage 有兩個會拋的失效面,而呼叫點幾乎都落在 render
 *  路徑上(`useState` 的 lazy initializer)或事件處理器裡 ——
 *  (a) Safari 私密視窗 / 企業政策鎖 storage 時,**光是存取**就拋 `SecurityError`;
 *  (b) 配額滿時 `setItem` 拋 `QuotaExceededError`。
 *  全 frontend 零 ErrorBoundary → 任何一處漏包 try/catch 就是**整頁白屏**,而且零錯誤
 *  訊號。同一套 try/catch 原本在 14 個檔各抄一次(2026-08-24 grep 45 處,其中 27 處
 *  裸奔),漏抄的那一份沒有人會發現 —— 所以收成一個出口,新呼叫點不必再想這件事。
 *
 *  **失敗語意**:
 *  - 讀失敗 → 回 `null`(與「這把鍵沒設過」同一條退路,呼叫端只有一種處理方式);
 *  - 寫 / 刪失敗 → 回 `false`、**不拋、不重試**。回傳布林不是裝飾:有兩個呼叫端要
 *    分辨成敗(`App.tsx` 的舊 key 遷移「setItem 成功才 removeItem」、
 *    `lib/fee-discount.ts` 的「寫失敗就沒有新值可通知」)。
 *  - 兩者各 `console.warn` **一次**(module 級旗標)。不吞成完全靜默(鐵則 E),但也
 *    不能每次都印 —— 讀取端住在 render 路徑上,一秒可以被呼叫幾十次。
 *
 *  **不做 in-memory fallback**:寫不進去就是這次不記住。假裝寫成功會讓「同分頁看起來
 *  記住了、重開就沒了」比乾脆不記住更難解釋,而且會多一份與 storage 不同步的真相。
 *
 *  **key 一律從 `lib/constants.ts` 取**(本檔刻意不 import 它:出口不該知道有哪些鍵,
 *  而 `constants.ts` 的 `purgeOrphanKeys` 反過來要用本檔的 `removeLocal`)。
 *
 *  ---
 *  **react-doctor `no-event-handler` 對本層是誤報**(`App.tsx` 的 `MAIN_CODE_KEY` effect
 *  掛了一行 disable,是 repo 內第三處 —— 既有 `StockPage.tsx` / `useStockStream.ts` 各一處同款)。實測證據:同一個 effect 把 `writeLocal(...)`
 *  換回字面的 `window.localStorage.setItem(...)`,finding 就消失 —— 規則把「字面上的
 *  localStorage 成員呼叫」認成合法的 external-store 同步,卻看不穿一層具名函式。
 *  規則建議的「搬進觸發它的事件處理器」在那裡是反向的:`stockCode` 有多個寫者(自選列 /
 *  圖牆點卡 / 漲跌停跳轉 / 搜尋),逐一補一份寫入正是 N022 的病灶本身;而且「掛載時由
 *  存檔還原的那一次回寫」也會一併消失。**整條規則不關**(它在別處抓得到真東西),
 *  只關那一行 —— 日後有人在別的 effect 裡用 `writeLocal` 而被同一條規則擋下時,
 *  先回來看這段,別直接把規則寫進 `doctor.config.json`。
 */

// 四個旗標各自獨立:讀不到 / 寫不進去 / 刪不掉 / 資料壞了是四種不同的故障
// (政策鎖 vs 配額滿 vs 殘值清不掉 vs 舊值格式壞),共用旗標會讓先發生的那個把其餘的
// 永久靜音。宣告與賦值同在本檔(formatter prefer-const 陷阱)。
let warnedRead = false;
let warnedWrite = false;
let warnedRemove = false;

/** 壞 JSON 的旗標是 **per-key**(review ST1):共用一個的話,第一把壞掉的鍵會讓其餘
 *  四個 JSON 呼叫點(圖表疊線 / 漲跌停篩選 / 自選折疊 / 江波圖腿位)永遠不出聲 ——
 *  而它們是各自獨立的資料,壞了要各自看得到。 */
const warnedParseKeys = new Set<string>();

function warnRead(err: unknown): void {
  if (warnedRead) return;
  warnedRead = true;
  console.warn("storage: localStorage 讀取失敗(私密視窗 / 政策鎖?),偏好設定改走預設值", err);
}

function warnWrite(err: unknown): void {
  if (warnedWrite) return;
  warnedWrite = true;
  console.warn("storage: localStorage 寫入失敗(配額滿 / 政策鎖?),本次偏好設定不落檔", err);
}

/** 刪除失敗與寫入失敗刻意分開(review ST3):兩者的後果不同 —— 寫失敗是「這次不記住」,
 *  刪失敗是「殘值留著、下次啟動再清」,套同一句話是錯敘述。 */
function warnRemove(err: unknown): void {
  if (warnedRemove) return;
  warnedRemove = true;
  console.warn("storage: localStorage 刪除失敗(政策鎖?),殘值留著,下次啟動再清", err);
}

/** 讀。契約與 `getItem` 逐字相同(沒設過 = `null`),多的只是**讀不到也回 `null`**。 */
export function readLocal(key: string): string | null {
  try {
    return window.localStorage.getItem(key);
  } catch (err) {
    warnRead(err);
    return null;
  }
}

/** 寫。回 `true` = 真的落檔了。 */
export function writeLocal(key: string, value: string): boolean {
  try {
    window.localStorage.setItem(key, value);
    return true;
  } catch (err) {
    warnWrite(err);
    return false;
  }
}

/** 刪。回 `true` = 真的刪掉了(對不存在的鍵也是 `true` —— `removeItem` 是冪等 no-op)。 */
export function removeLocal(key: string): boolean {
  try {
    window.localStorage.removeItem(key);
    return true;
  } catch (err) {
    warnRemove(err);
    return false;
  }
}

/** 讀 + `JSON.parse`。
 *
 *  **未設 / 空字串 / 壞 JSON / 存取即拋,一律回 `null`** —— 呼叫端因此只有一條退預設
 *  的路徑。壞 JSON 單獨算一種故障(那是資料壞了不是 storage 壞了),故獨立的 per-key 旗標。
 *
 *  **空字串走「無資料」而不是丟給 `JSON.parse`**(review ST1):舊碼一律是
 *  `if (!raw) return DEFAULT` —— 沒存過與存了空字串都是**正常路徑**,靜默退預設。
 *  丟給 `JSON.parse("")` 會拋,於是被算成「資料壞了」而印一則不成立的警告,
 *  還吃掉那把鍵唯一一次的警告額度。
 *
 *  回 `unknown` 而不是泛型:存進去的是使用者瀏覽器裡的舊資料,`as T` 會讓「schema 變了」
 *  這件事在型別上消失。呼叫端一律自己驗形狀(既有四個呼叫點都已經這麼做)。 */
export function readLocalJson(key: string): unknown {
  const raw = readLocal(key);
  if (raw === null || raw === "") return null;
  try {
    return JSON.parse(raw) as unknown;
  } catch (err) {
    if (!warnedParseKeys.has(key)) {
      warnedParseKeys.add(key);
      console.warn(`storage: ${key} 的內容不是合法 JSON,改走預設值`, err);
    }
    return null;
  }
}
