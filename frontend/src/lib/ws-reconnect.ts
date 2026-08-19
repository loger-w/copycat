/** 8 條 WS hook 共用的「連線 + 自動重連 + 靜默 watchdog」骨架(mod/ws-app-heartbeat)。
 *
 * 骨架本體是 8 份同款 `ws / timer / backoff / alive / connect` 的抽出(FE-1 逐字複刻),
 * 之上加了三件半死連線需要的事:
 *  - `onConnecting` 承接各 hook 原本寫在 `connect()` 本體的 `setWsStatus("connecting")`
 *    (含首次與每次重連);
 *  - backoff 三分支(SC-4;`onopen` **不歸零**,歸零由 onclose 的「存活 ≥ minUptime」分支達成):
 *    存活 ≥ 5 s 斷線 → 回初值 1 s;有 open 但短命(accept-then-close)→ 倍增 cap 5 s;
 *    從未 open(握手失敗)→ 倍增 cap 30 s;
 *  - `{type:"ping"}` 後端心跳在本層過濾(SC-3),不進 `onMessage`,但會武裝 / 餵 watchdog;
 *  - 靜默 watchdog(SC-2):**收到第一則 ping 才武裝**,之後 `silenceTimeout` 內零訊息就
 *    卸掉舊 socket 的 handler、`close()`、走與 onclose 相同的重連路徑(不等 onclose —
 *    Chromium closing handshake 逾時 60 s)。不送 ping 的舊後端永不武裝 = 行為同現況;
 *  - `onerror` 關**自身** socket(SC-5);`onclose` 只由 `stopped` 守門,不做世代比對
 *    (被 watchdog 放棄的那代已經卸掉 handler,遲到事件進不來);
 *  - `close()` 停止重連、清 watchdog、關掉當下的 socket,之後所有回呼不再觸發。
 *
 * 心跳間隔的產生點在後端 `copycat/server/ws.py::WS_HEARTBEAT_SECS`(10 s),
 * `WS_SILENCE_TIMEOUT_MS` 必須遠大於它(CLAUDE.md §4「WS 心跳契約」)。
 */

export const WS_BACKOFF_START_MS = 1_000;
export const WS_BACKOFF_CAP_MS = 30_000;
/** 連線存活 ≥ 此值才算「健康過」,斷線後退避歸零回初值(SC-4 (i))。 */
export const WS_MIN_UPTIME_MS = 5_000;
/** 有 open 但短命(accept-then-close)時的退避上限(SC-4 (ii))。 */
export const WS_SHORT_LIVED_CAP_MS = 5_000;
/** 自最後一則訊息(含 ping)起多久沒動靜視為半死;必須 > 後端心跳間隔(SC-2)。 */
export const WS_SILENCE_TIMEOUT_MS = 30_000;
/** watchdog 巡檢間隔;偵測延遲 = timeout ~ timeout + tick。 */
export const WS_WATCHDOG_TICK_MS = 5_000;

/** 記住「這個 URL 的 server 會送 ping」:某一代收過之後,同 URL 的後續世代 onopen 即武裝
 *  (封住「新連線在首則 ping 抵達前就半死」的盲區;spec §4.2 sticky)。 */
const pingingUrls = new Set<string>();

/** 測試用:清掉 sticky 記憶,讓各測試互不影響。 */
export function resetWsPingMemory(): void {
  pingingUrls.clear();
}

export interface WsHandlers {
  /** 每次建 socket 前呼叫(含首次與每次重連)。 */
  onConnecting?(): void;
  onOpen?(): void;
  /** 收到的是 `JSON.parse` 後的值;parse 失敗只 warn 不呼叫,`{type:"ping"}` 心跳被過濾。
   *  本身拋例外也只 warn(逐字複刻抽出前的吞法),不會打斷連線或後續訊息。 */
  onMessage(msg: unknown): void;
  onClose?(): void;
}

export interface WsOptions {
  /** `console.warn` 前綴(各 hook 沿用原本的字樣)。 */
  label?: string;
  backoffStartMs?: number;
  backoffCapMs?: number;
  minUptimeMs?: number;
  shortLivedCapMs?: number;
  silenceTimeoutMs?: number;
  watchdogTickMs?: number;
}

/** 後端 `relay()` 的應用層心跳(`copycat/server/ws.py::PING`)。 */
function isPing(value: unknown): boolean {
  return (
    typeof value === "object" && value !== null && (value as { type?: unknown }).type === "ping"
  );
}

export interface WsHandle {
  /** 停止重連 + 關 socket,之後所有回呼不再觸發。 */
  close(): void;
}

/** 建立 WS 連線並在斷線後以指數退避重連。`url` 傳函式 = 每次重連當下重算。 */
export function connectWithRetry(
  url: string | (() => string),
  handlers: WsHandlers,
  opts: WsOptions = {},
): WsHandle {
  const label = opts.label ?? "ws";
  const startMs = opts.backoffStartMs ?? WS_BACKOFF_START_MS;
  const capMs = opts.backoffCapMs ?? WS_BACKOFF_CAP_MS;
  const minUptimeMs = opts.minUptimeMs ?? WS_MIN_UPTIME_MS;
  const shortLivedCapMs = opts.shortLivedCapMs ?? WS_SHORT_LIVED_CAP_MS;
  const silenceTimeoutMs = opts.silenceTimeoutMs ?? WS_SILENCE_TIMEOUT_MS;
  const tickMs = opts.watchdogTickMs ?? WS_WATCHDOG_TICK_MS;

  let current: WebSocket | null = null;
  let timer: number | undefined;
  let backoff = startMs;
  let stopped = false;
  /** 當代連線的 open 時刻(每次 `connect()` 重設,只有 `onopen` 寫)。 */
  let openedAt: number | null = null;
  /** 停掉「當下這代」的 watchdog(每次 `connect()` 換新的;`handle.close()` 用)。 */
  let stopWatchdog = (): void => {};

  /** 斷線後排程重連並依「這代活多久」決定退避(SC-4 三分支)。 */
  const scheduleReconnect = (): void => {
    handlers.onClose?.();
    const lived = openedAt !== null ? Date.now() - openedAt : null;
    const delay = lived !== null && lived >= minUptimeMs ? startMs : backoff;
    timer = window.setTimeout(connect, delay);
    backoff = Math.min(delay * 2, lived !== null ? shortLivedCapMs : capMs);
  };

  const connect = (): void => {
    openedAt = null;
    handlers.onConnecting?.();
    const target = typeof url === "string" ? url : url();
    const sock = new WebSocket(target);
    current = sock;

    // --- 以下全部綁在「這一代」socket 的閉包上,舊世代不可能碰到新世代的狀態 ---
    let watchdog: number | undefined;
    let lastMsgAt = 0;
    let lastTickAt = 0;

    const clearWatchdog = (): void => {
      if (watchdog === undefined) return;
      window.clearInterval(watchdog);
      watchdog = undefined;
    };

    /** 半死判定:自最後一則訊息起靜默超過 timeout 就放棄這條連線。 */
    const tick = (): void => {
      const now = Date.now();
      const sinceTick = now - lastTickAt;
      lastTickAt = now;
      if (sinceTick > tickMs * 2) {
        // 主執行緒長阻塞 / 機器睡醒:server 的 ping 不是沒送,是沒被處理 → 只重置基準。
        lastMsgAt = now;
        return;
      }
      if (now - lastMsgAt <= silenceTimeoutMs) return;

      console.warn(`${label}: ${Math.round((now - lastMsgAt) / 1000)} s 無訊息,重連`);
      sock.onmessage = null; // 先卸 handler:被放棄的 socket 之後的事件一律進不來
      sock.onclose = null;
      sock.onerror = null;
      clearWatchdog();
      sock.close(); // 不等 onclose(Chromium closing handshake 逾時 60 s)
      if (stopped) return;
      scheduleReconnect();
    };

    /** 武裝:單一 setInterval 巡檢(onmessage 只寫時間戳,個股 tick 洪流下零 timer churn)。 */
    const arm = (): void => {
      if (watchdog !== undefined || stopped) return;
      lastMsgAt = Date.now();
      lastTickAt = lastMsgAt;
      watchdog = window.setInterval(tick, tickMs);
    };
    stopWatchdog = clearWatchdog;

    sock.onopen = () => {
      openedAt = Date.now();
      if (pingingUrls.has(target)) arm(); // sticky:寬限 = 完整 silenceTimeout
      handlers.onOpen?.();
    };
    sock.onmessage = (ev: MessageEvent<string>) => {
      lastMsgAt = Date.now();
      let value: unknown;
      try {
        value = JSON.parse(ev.data);
      } catch (err) {
        console.warn(`${label}: 無法解析訊息`, err);
        return;
      }
      if (isPing(value)) {
        pingingUrls.add(target);
        arm();
        return; // SC-3:心跳不進 hook,免得覆蓋 state
      }
      try {
        handlers.onMessage(value);
      } catch (err) {
        // 逐字複刻:抽出前 8 hook 的 onMessage 本體全在 parse 的 try 內,handler 例外一樣被
        // 這個 catch 吞掉(只 warn)。🔵 抽出時把 try 收窄成只包 JSON.parse,對等性靠這裡補回;
        // 標籤與 parse 失敗可區分,免得兩種故障在 console 混成一種。
        console.warn(`${label}: 訊息處理失敗`, err);
      }
    };
    sock.onclose = () => {
      clearWatchdog();
      if (stopped) return;
      scheduleReconnect();
    };
    sock.onerror = () => {
      // SC-5:關自身 socket。舊版關的是閉包共用的 `current`(alias),StrictMode 下
      // 舊 socket 晚到的 error 會把剛建好的新 socket 一起關掉。
      sock.close();
    };
  };

  connect();

  return {
    close: (): void => {
      stopped = true;
      window.clearTimeout(timer);
      stopWatchdog();
      current?.close();
    },
  };
}
