/** 8 條 WS hook 共用的「連線 + 自動重連」骨架(mod/ws-app-heartbeat FE-1)。
 *
 * 本檔是 8 份同款骨架(`ws / timer / backoff / alive / connect`)的**逐字複刻**抽出,
 * **零行為改動**:
 *  - `onConnecting` 承接各 hook 原本寫在 `connect()` 本體的 `setWsStatus("connecting")`
 *    (含首次與每次重連);
 *  - `onopen` **歸零 backoff**(現行語意,accept-then-close 會因此 1 Hz 重連);
 *  - `onerror` 關的是閉包共用的 `current`(= 現行 8 處的 `ws?.close()`,**含 alias 缺陷**:
 *    StrictMode 下舊 socket 晚到的 error 會關掉新 socket);
 *  - `onclose` **只由 `stopped` 守門**(= 現行 `if (!alive) return`),不做世代比對;
 *  - `close()` 停止重連並關掉當下的 socket,之後所有回呼不再觸發。
 *
 * 上述兩條「現況缺陷」由下一個 🔴 commit 翻轉(spec §7),`ws-reconnect.test.ts` 內以
 * `[該變]` 註記事前標明。watchdog / ping 過濾 / 三分支 backoff **不在本檔**。
 */

export const WS_BACKOFF_START_MS = 1_000;
export const WS_BACKOFF_CAP_MS = 30_000;

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

  let current: WebSocket | null = null;
  let timer: number | undefined;
  let backoff = startMs;
  let stopped = false;

  const connect = (): void => {
    handlers.onConnecting?.();
    const sock = new WebSocket(typeof url === "string" ? url : url());
    current = sock;
    sock.onopen = () => {
      backoff = startMs;
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
      handlers.onClose?.();
      timer = window.setTimeout(connect, backoff);
      backoff = Math.min(backoff * 2, capMs);
    };
    sock.onerror = () => {
      // 逐字複刻:關的是閉包共用的 `current`,不是 `sock`(FE-WS-ONERROR-ALIAS)。
      current?.close();
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
