/** 8 條 WS hook 共用的「連線 + 自動重連」骨架(mod/ws-app-heartbeat FE-1)。
 *
 * 本檔是 8 份同款骨架(`ws / timer / backoff / alive / connect`)的**逐字複刻**抽出,
 * **零行為改動**:
 *  - `onConnecting` 承接各 hook 原本寫在 `connect()` 本體的 `setWsStatus("connecting")`
 *    (含首次與每次重連);
 *  - backoff 三分支(SC-4;`onopen` **不歸零**,歸零由 onclose 的「存活 ≥ minUptime」分支達成):
 *    存活 ≥ 5 s 斷線 → 回初值 1 s;有 open 但短命(accept-then-close)→ 倍增 cap 5 s;
 *    從未 open(握手失敗)→ 倍增 cap 30 s;
 *  - `onerror` 關**自身** socket(SC-5;原 alias 缺陷「舊 socket 的 error 關掉新 socket」已修);
 *  - `onclose` **只由 `stopped` 守門**(= 現行 `if (!alive) return`),不做世代比對;
 *  - `close()` 停止重連並關掉當下的 socket,之後所有回呼不再觸發。
 *
 * 上述兩條「現況缺陷」由下一個 🔴 commit 翻轉(spec §7),`ws-reconnect.test.ts` 內以
 * `[該變]` 註記事前標明。watchdog / ping 過濾 / 三分支 backoff **不在本檔**。
 */

export const WS_BACKOFF_START_MS = 1_000;
export const WS_BACKOFF_CAP_MS = 30_000;
/** 連線存活 ≥ 此值才算「健康過」,斷線後退避歸零回初值(SC-4 (i))。 */
export const WS_MIN_UPTIME_MS = 5_000;
/** 有 open 但短命(accept-then-close)時的退避上限(SC-4 (ii))。 */
export const WS_SHORT_LIVED_CAP_MS = 5_000;

export interface WsHandlers {
  /** 每次建 socket 前呼叫(含首次與每次重連)。 */
  onConnecting?(): void;
  onOpen?(): void;
  /** 收到的是 `JSON.parse` 後的值;parse 失敗只 warn 不呼叫。 */
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

  let current: WebSocket | null = null;
  let timer: number | undefined;
  let backoff = startMs;
  let stopped = false;
  /** 當代連線的 open 時刻(每次 `connect()` 重設,只有 `onopen` 寫)。 */
  let openedAt: number | null = null;

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
    const sock = new WebSocket(typeof url === "string" ? url : url());
    current = sock;
    sock.onopen = () => {
      openedAt = Date.now();
      handlers.onOpen?.();
    };
    sock.onmessage = (ev: MessageEvent<string>) => {
      try {
        handlers.onMessage(JSON.parse(ev.data));
      } catch (err) {
        console.warn(`${label}: 無法解析訊息`, err);
      }
    };
    sock.onclose = () => {
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
      current?.close();
    },
  };
}
