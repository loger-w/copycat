import { useState } from "react";

import { GroupGridView } from "@/components/stock/GroupGridView";
import { OrderBook } from "@/components/stock/OrderBook";
import { SignalRail } from "@/components/stock/SignalRail";
import { SignalRulesDialog } from "@/components/stock/SignalRulesDialog";
import { StockChart } from "@/components/stock/StockChart";
import { TickTape } from "@/components/stock/TickTape";
import { WatchlistSidebar } from "@/components/stock/WatchlistSidebar";
import { useSignalFeed } from "@/hooks/useSignalFeed";
import { useSaveRule, useSignalRules, type SignalRule } from "@/hooks/useSignalRules";
import { useSignalSound } from "@/hooks/useSignalSound";
import { useStkfutContracts } from "@/hooks/useStkfutContracts";
import { errText, useSaveWatchlist, useStockWatchlist } from "@/hooks/useStockWatchlist";
import type { StockStreamState } from "@/hooks/useStockStream";
import { STOCK_VIEW_KEY } from "@/lib/constants";
import { chgPct, fmt, fmtPct } from "@/lib/format";
import { instrumentKeyOf, selectionOf, ymLabel, type StkfutSelection } from "@/lib/stkfut";
import { limitState } from "@/lib/stock-tick";
import { cn } from "@/lib/utils";
import { addCode, assignToGroup, isSameWatchlist, type Watchlist } from "@/lib/watchlist-model";

/** 個股頁中間主區(SC-6):報價 header → 圖表(江波圖 / K 線)→ 下半 五檔 | 明細。
 *  閃電梯 / 委託 / 部位已移到常駐右欄(RightRail);主檔與資料流由 App 持有(D-3)。
 *  最左為訊號欄(stock-signals SC-9),接線在本層 —— SignalRail 是純展示元件。 */

interface Props {
  code: string | null;
  onSelect: (code: string) => void;
  stream: StockStreamState;
  /** 選中的個股期合約;`null` = 現貨態。狀態持有者是 App(D5)—— 資料流(useStockStream)
   *  與右欄都要吃同一份,留在本元件內餵不到那兩處。 */
  contract?: StkfutSelection | null;
  onContract?: (next: StkfutSelection | null) => void;
}

/** 中間主區的檢視(group-grid SC-3):單檔看盤 vs 群組 mini 圖牆。 */
type StockView = "single" | "group";

const VIEW_LABELS: [StockView, string][] = [
  ["single", "單檔"],
  ["group", "群組"],
];

/** 只認得 `"group"`,其餘(未設 / 被人手動改壞 / 舊版遺留值)一律回單檔 ——
 *  預設檢視必須是「有主圖」的那個,壞值把使用者丟進群組檢視會像整頁不見了。 */
function initialView(): StockView {
  try {
    return window.localStorage.getItem(STOCK_VIEW_KEY) === "group" ? "group" : "single";
  } catch {
    return "single";
  }
}

/** jsdom 與不支援 Notification 的瀏覽器沒有這個全域 → 一律當「已拒絕」降級:
 *  rail 只在 `default` 時顯示「允許通知」鈕,denied 就是不出現那顆鈕。 */
function currentPermission(): NotificationPermission {
  try {
    return globalThis.Notification?.permission ?? "denied";
  } catch {
    return "denied";
  }
}

export function StockPage({ code, onSelect, stream, contract = null, onContract }: Props) {
  const { accum, watchlist, status, stkfut, wsStatus } = stream;
  // 訊號欄的三條資料線都在本層接:feed(WS + 當日 jsonl)/ 規則(後端 signal_rules.json)/
  // 提示音(localStorage 共用 store,與 App 的 useSignalAlerts 同一份真值)
  const { signals } = useSignalFeed();
  // `isError` 要一路帶到畫面:退回 `[]` 之後,「載入失敗」與「零規則」在 rail 與
  // Dialog 上長得一模一樣,而後者會讓使用者照著空態去新增(只會撞名失敗)。
  const { data: rules = [], isError: rulesError } = useSignalRules();
  const saveRule = useSaveRule();
  const [rulesOpen, setRulesOpen] = useState(false);
  const { soundOn, setSoundOn } = useSignalSound();
  const [notifPermission, setNotifPermission] = useState<NotificationPermission>(currentPermission);
  const [view, setView] = useState<StockView>(initialView);
  // 「加入自選」入口(round4 項 4):側欄搜尋改成預覽後,收藏動作移到這裡 ——
  // 使用者先看到資料,再決定要不要收藏、收到哪一組。
  // `isPending` / `isError` 要一路帶到群組檢視(review A4):`wl?.groups ?? []` 把
  // 「還在載」「載入失敗」「真的零群組」壓成同一個空陣列,而空態文案會叫使用者去
  // 建群組 —— 把「後端出事」講成「你沒建群組」。
  const { data: wl, isPending: wlPending, isError: wlError } = useStockWatchlist();
  const save = useSaveWatchlist();
  const [pickerOpen, setPickerOpen] = useState(false);
  // 換股時關掉面板(review F3)。App 渲染本元件沒帶 key,同一個 instance 會活過切檔 ——
  // 面板留在展開狀態、按鈕卻已綁到新的 code,誤觸就把**錯的股票**靜默加進群組。
  // 用 render 期間調整 state 的官方 pattern(專案有 you-might-not-need-an-effect lint)。
  const [prevCode, setPrevCode] = useState(code);
  if (prevCode !== code) {
    setPrevCode(code);
    setPickerOpen(false);
  }

  // 合約清單:404(這檔沒期貨)→ null → 不渲染下拉。TC4 斷線(502)也會沒有下拉,
  // 但那是 hook 內刻意保留的錯誤態,不與「沒期貨」共用一個 data 值。
  const { data: contracts } = useStkfutContracts(code);
  const meta = accum?.meta ?? null;
  const last = accum?.last ?? null;
  const chg = last && meta?.ref ? chgPct(last.p, meta.ref) : null;
  const limit = limitState(last?.p ?? null, meta?.upper ?? null, meta?.lower ?? null);
  // 回補中的旗標由後端以**槽位鍵**發出,期貨態是 `F:<prod>:<ym>` 不是股號
  const instrumentKey = instrumentKeyOf(code, contract);

  // **`wl` 未載入(loading / 失敗)時不渲染按鈕**:退回空自選再送 PUT 會把整份自選
  // 靜默清空。這是新入口才有的 gate,不是既有行為。
  const canAdd = wl !== undefined && code !== null && !wl.codes.includes(code);

  /** 零 PUT 早退(W-9):`assignToGroup` 內部恆回新陣列,內容相同也會送出,
   *  而內容相同的 PUT 會讓後端重設整個訂閱池(TC4 全量 UNSUB/SUB)。 */
  function commit(next: Watchlist): void {
    setPickerOpen(false);
    if (wl === undefined) return;
    if (isSameWatchlist(next, wl)) return;
    save.mutate(next);
  }

  /** 加自選 + 指派群組**合成單次 PUT**:分兩次會產出「在群組但不在 codes」的中間態。 */
  function addTo(group: string | null): void {
    if (wl === undefined || code === null) return;
    const withCode = addCode(wl, code);
    const g = group === null ? null : withCode.groups.find((x) => x.name === group);
    commit(g === null || g === undefined ? withCode : assignToGroup(withCode, code, g.name, g.codes.length));
  }

  /** 規則開關 = 整條規則 PUT(只翻 `enabled`)。PUT 失敗時 query data 不動 →
   *  開關停在原位,使用者看得出「沒切成功」;錯誤留在 `saveRule.error`,不另吞。
   *  送整條而不是部分更新:後端 PUT 是全量取代,少帶欄位會被判 INVALID_RULE。 */
  function toggleRule(rule: SignalRule): void {
    saveRule.mutate({ ...rule, enabled: !rule.enabled });
  }

  /** 檢視切換 + 記憶。localStorage 寫失敗(隱私模式 / 配額)不讓整頁掛掉:
   *  切換本身已生效,代價僅是下次重開回到單檔。 */
  function selectView(next: StockView): void {
    setView(next);
    try {
      window.localStorage.setItem(STOCK_VIEW_KEY, next);
    } catch {
      // 記不住就算了 —— 為了記憶檢視而讓看盤頁白掉是本末倒置
    }
  }

  /** 權限狀態不是 React state 的衍生值,要主動回寫 —— 使用者按完瀏覽器提示後,
   *  只有這裡更新才會讓「允許通知」鈕收起來。 */
  function requestNotif(): void {
    try {
      const Ctor = globalThis.Notification as typeof Notification | undefined;
      if (Ctor === undefined) return;
      void Ctor.requestPermission().then(
        (result) => setNotifPermission(result),
        // 舊瀏覽器是 callback 版、iframe 內會被擋:問不到就維持現值(鈕留著)
        () => setNotifPermission(currentPermission()),
      );
    } catch {
      setNotifPermission(currentPermission());
    }
  }

  return (
    <div className="flex min-h-0 flex-1 gap-4">
      <SignalRail
        signals={signals}
        rules={rules}
        rulesError={rulesError}
        toggleError={saveRule.error?.message ?? null}
        onToggleRule={toggleRule}
        onOpenManager={() => setRulesOpen(true)}
        onSelect={onSelect}
        notifPermission={notifPermission}
        onRequestNotif={requestNotif}
        soundOn={soundOn}
        onToggleSound={setSoundOn}
      />
      {/* 常駐掛載、只切 open(dialog 樣板慣例);規則清單由本層餵,Dialog 不自己抓 */}
      <SignalRulesDialog
        open={rulesOpen}
        rules={rules}
        rulesError={rulesError}
        onClose={() => setRulesOpen(false)}
      />
      <WatchlistSidebar active={code} onSelect={onSelect} quotes={watchlist} />
      <main className="flex min-h-0 min-w-0 flex-1 flex-col gap-3 overflow-y-auto">
        {status.tc4 === "down" || wsStatus === "closed" ? (
          <p className="rounded border border-bear bg-bear/10 px-3 py-1 text-sm text-bear">
            {status.tc4 === "down" ? "達錢 4 連線中斷,恢復後自動回補" : "伺服器連線中斷,重連中…"}
          </p>
        ) : null}
        {/* 檢視切換 pill(group-grid SC-3)。掛在 main 頂層、`code === null` 與
            `accum === null` 兩個條件分支**之外**(design R6)—— 掛進任一分支內,
            未選股 / 主圖 snapshot 還沒回來時就永遠切不到群組檢視,而那兩個時機
            恰恰是最想看「整組今天在幹嘛」的時候。 */}
        <div className="flex shrink-0 flex-wrap items-center gap-1">
          {VIEW_LABELS.map(([id, label]) => (
            <button
              key={id}
              type="button"
              aria-pressed={view === id}
              onClick={() => selectView(id)}
              className={cn(
                "rounded border px-2 py-0.5 text-xs",
                view === id ? "border-accent text-accent" : "border-line text-ink-dim hover:text-ink",
              )}
            >
              {label}
            </button>
          ))}
        </div>
        {view === "group" ? (
          // 群組檢視吃掉整個 main 主體(header / 圖表 / 下半列全部讓位),訊號欄與
          // 自選欄在 main 之外不受影響。載入 / 失敗 / 零群組的分態由 GroupGridView
          // 接手,但**判斷依據得由這裡給** —— 它只看得到 groups 陣列。
          <GroupGridView
            groups={wl?.groups ?? []}
            wlPending={wlPending}
            wlError={wlError}
            quotes={watchlist}
            // 點卡片 = **只換右欄閃電梯的標的**,檢視停在群組(SC-3 / D3)。卡片上已是
            // 單檔同款的完整分時圖,細節就在圖牆上看得完;自動切回單檔的舊行為會讓每次
            // 換標的都得再點一次「群組」回來,而盯盤時圖牆本身就是主畫面。
            // 進單檔的路徑只剩檢視 pill。
            onPick={onSelect}
          />
        ) : code === null ? (
          <div className="flex flex-1 items-center justify-center">
            <p className="text-sm text-ink-muted">從自選清單選擇一檔開始看盤</p>
          </div>
        ) : (
          <>
            <header className="flex flex-wrap items-baseline gap-3">
              <h2 className="text-lg font-bold text-ink">
                {meta?.name ?? ""} <span className="font-mono text-ink-muted">{code}</span>
                {/* 緩撮標示(SC-2):`contract === null` 才標 —— 期貨合約沒有試撮窗
                    (後端 trial 恆 false),而合約態下畫面上的標的是合約,同畫面側欄的
                    現貨列照標是正確的(兩者並存)。色系同側欄:amber = 中性警示。
                    `!accum.noData`(code review IC-4):窗內的 payload 對無資料檔照算
                    trial=true,而側欄那一列(`!q?.no_data`)不標 —— 少了這道,兩個視圖
                    對同一狀態給相反答案,而且是對沒有任何報價的標的講撮合狀態。 */}
                {accum?.trial && !accum.noData && contract === null ? (
                  <span data-testid="page-trial" className="text-sm text-amber-400">
                    (緩)
                  </span>
                ) : null}
              </h2>
              {/* 合約下拉(SC-4)。三類選項都得**逐字可指認**:`現貨` / `2026/09` /
                  `小型 2026/09` —— 標準與小型的契約單位差 20 倍(2,000 vs 100 股),
                  選錯而看不出來就是下單量差 20 倍。
                  受控於 `contract` prop:選擇態的真相源在 App,本元件不留第二份。 */}
              {contracts != null ? (
                <select
                  aria-label="合約"
                  value={contract === null ? "" : `${contract.prod}:${contract.ym}`}
                  onChange={(e) => onContract?.(selectionOf(contracts, e.target.value))}
                  className="rounded border border-line bg-bg-deep px-1.5 py-0.5 font-mono text-xs text-ink"
                >
                  <option value="">現貨</option>
                  {contracts.std.contracts.map((ym) => (
                    <option key={`s-${ym}`} value={`${contracts.std.prod}:${ym}`}>
                      {ymLabel(ym)}
                    </option>
                  ))}
                  {(contracts.mini?.contracts ?? []).map((ym) => (
                    <option key={`m-${ym}`} value={`${contracts.mini?.prod ?? ""}:${ym}`}>
                      {`小型 ${ymLabel(ym)}`}
                    </option>
                  ))}
                </select>
              ) : null}
              {/* 漲跌停亮燈(項 3):踩到漲跌停時整塊反白底色,不只是換文字色 ——
                  這是盤中要用餘光捕捉的狀態,而紅字與「今天最多只能到這裡」是兩件事。 */}
              {last ? (
                <span
                  data-testid="page-quote"
                  className={cn(
                    "font-mono text-3xl font-semibold",
                    limit === "upper" && "rounded bg-bull px-1.5 text-white",
                    limit === "lower" && "rounded bg-bear px-1.5 text-white",
                    limit === null &&
                      ((chg ?? 0) > 0 ? "text-bull" : (chg ?? 0) < 0 ? "text-bear" : "text-ink"),
                  )}
                >
                  {fmt(last.p)}
                  {/* font-normal 是**還原**不是新樣式:父層新加的 font-semibold 會繼承下來,
                      % 跟著變粗是主數字放大的副作用,不在本輪 scope。 */}
                  {chg != null ? (
                    <span data-testid="page-quote-pct" className="ml-1 text-sm font-normal">
                      {fmtPct(chg)}
                    </span>
                  ) : null}
                </span>
              ) : null}
              {accum?.noData ? <span className="text-xs text-ink-dim">無資料</span> : null}
              {status.backfilling === instrumentKey ? (
                <span className="text-xs text-ink-dim">回補中…</span>
              ) : null}
              {/* 期現價差列在期貨態清空(D15 前端側):兩條腿是「現貨主圖 vs 期貨」,
                  主圖已經是期貨時它比的是自己。 */}
              {contract === null && stkfut ? (
                <span className="font-mono text-xs text-ink-muted">
                  {stkfut.prod} {fmt(stkfut.p)}
                  {stkfut.basis != null ? (
                    <span className={cn("ml-1", stkfut.basis > 0 ? "text-bull" : stkfut.basis < 0 ? "text-bear" : "")}>
                      {`價差 ${stkfut.basis > 0 ? "+" : ""}${fmt(stkfut.basis)}`}
                    </span>
                  ) : null}
                </span>
              ) : null}
              {/* 加入自選(round4 項 4)。只在「看的是非自選股」時出現 —— 已在自選的檔
                  按了也沒有意義,按鈕本身就是狀態指示。
                  面板照側欄 assigning 的裸 div + button 慣例(專案無 Radix)。 */}
              {canAdd ? (
                <span className="relative">
                  <button
                    type="button"
                    aria-label="加入自選"
                    aria-expanded={pickerOpen}
                    disabled={save.isPending}
                    onClick={() => setPickerOpen((v) => !v)}
                    className="rounded border border-accent px-2 py-0.5 text-xs text-accent disabled:opacity-50"
                  >
                    加入自選
                  </button>
                  {pickerOpen ? (
                    <span className="absolute top-full left-0 z-20 mt-1 flex w-max flex-wrap gap-1 rounded border border-line bg-bg-deep p-2">
                      {wl.groups.map((g) => (
                        <button
                          key={g.name}
                          type="button"
                          aria-label={`加入 ${code} 到 ${g.name}`}
                          // PUT 未回前 wl 仍是舊值 → commit() 的零 PUT 早退擋不住重複送出
                          // (算出來的 next 與舊 wl 內容確實不同),只能靠停用(review F5)
                          disabled={save.isPending}
                          onClick={() => addTo(g.name)}
                          className="rounded border border-line px-1 py-0.5 text-xs text-ink hover:border-accent disabled:opacity-50"
                        >
                          {g.name}
                        </button>
                      ))}
                      {/* 零群組的使用者唯一的路徑,不可省 */}
                      <button
                        type="button"
                        aria-label={`加入 ${code} 到未分組`}
                        disabled={save.isPending}
                        onClick={() => addTo(null)}
                        className="rounded border border-line px-1 py-0.5 text-xs text-ink-dim hover:border-accent hover:text-ink disabled:opacity-50"
                      >
                        未分組
                      </button>
                    </span>
                  ) : null}
                </span>
              ) : null}
              {/* 上限 / 壞碼的文案要看得見,否則點了像沒反應 */}
              {save.error ? (
                <span className="text-xs text-bear">{errText(save.error.message)}</span>
              ) : null}
              <span className="ml-auto font-mono text-xs text-ink-dim">
                總量 {last?.cum_vol ?? "-"} · 昨量 {meta?.y_vol ?? "-"}
              </span>
            </header>
            {accum ? (
              <>
                <StockChart accum={accum} code={code} contract={contract} />
                {/* 下半:左五檔、右明細(round3 SC-6)。

                    h-56 shrink-0 = **確定高度**,不吃剩餘空間 —— 剩餘全歸圖表。
                    確定高度是必要的而不只是好看:TickTape 根節點的 `h-full` +
                    `overflow-y-auto` 只有在父層高度確定時才會內捲;父層若退化成
                    「內容自然高」,30 筆明細(每列 h-6)就把這列撐成 ~770px,
                    每點一次「載入更多」再 +720px,圖表被擠光而 <main> 靜默裁切。

                    兩個子 wrapper 都要 min-h-0,內層的 overflow 容器才算得出可捲高度。
                    五檔的 self-start 已移除、OrderBook 卡片加 h-full ——「兩塊底邊
                    齊平貼底」要求卡片撐滿列高,代價是卡片底部約 24px 留白,
                    這是對舊 self-start 取捨的刻意推翻(change-spec Known Risks 3)。 */}
                <div data-testid="stock-lower-row" className="flex h-56 min-w-0 shrink-0 gap-3">
                  <div className="min-h-0 min-w-0 flex-[3]">
                    <OrderBook
                      code={code}
                      book={accum.book}
                      last={last}
                      ref_={meta?.ref ?? null}
                      upper={meta?.upper ?? null}
                      lower={meta?.lower ?? null}
                    />
                  </div>
                  <div className="min-h-0 min-w-0 flex-[2]">
                    {/* `key={instrumentKey}`:明細的「載入更多」筆數是 TickTape 內部 state,
                        切標的時元件不 unmount → 展開到一半的筆數會跟著新標的走
                        (同一頁的 pickerOpen 是換股歸零的,兩者語意該一致)。
                        用 key 而不是 effect-on-code:重掛即歸零,零新 state 邏輯。
                        鍵是 instrument key 不是股號(F-4):同一檔股票的現貨與各月合約是
                        不同標的,而 `code` 在換月與現貨↔合約時恆不變 → 用它當 key 不重掛。 */}
                    <TickTape key={instrumentKey} ticks={accum.ticks} ref_={meta?.ref ?? null} />
                  </div>
                </div>
              </>
            ) : (
              <div className="flex flex-1 items-center justify-center">
                <p className="text-sm text-ink-muted">載入中…</p>
              </div>
            )}
          </>
        )}
      </main>
    </div>
  );
}

export default StockPage;
