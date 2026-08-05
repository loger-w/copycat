/** 台股綜合頁尾的相關係數收合區塊(SC-4)。
 *
 *  **收合 = unmount,不是 `hidden`**:corr / river 兩條 WS 活在 `CorrPage` 內,不 render
 *  就沒有 hook、沒有連線 —— 這個區塊在預設頁常駐,若用專案慣例的 `hidden` 保 DOM,
 *  等於所有人開站就吃兩條每秒推播。代價是重展開有 lazy 載入 + WS 重連的短暫空窗
 *  (design Known Risks KR-2,判定可接受:corr 是即時推播資料,重建即恢復)。
 *
 *  lazy chunk 邊界不變 —— 原本在 App 層的 `lazy(() => import("./CorrPage"))` 只是移到這裡。 */
import { lazy, Suspense, useState } from "react";

import { CORR_OPEN_KEY } from "@/lib/constants";

const CorrPage = lazy(() => import("@/components/corr/CorrPage"));

export function CorrSection() {
  // getItem 在 Safari 私密視窗 / storage 被政策鎖時光是存取就會拋,而這裡是 useState 的
  // initializer —— 拋出去就是整頁白屏。降回「收合」遠好過白屏(同 useChartToggles 慣例)。
  const [open, setOpen] = useState<boolean>(() => {
    try {
      return window.localStorage.getItem(CORR_OPEN_KEY) === "1";
    } catch {
      return false;
    }
  });

  function toggle(): void {
    const next = !open;
    setOpen(next);
    try {
      window.localStorage.setItem(CORR_OPEN_KEY, next ? "1" : "0");
    } catch {
      // 存不進去就算了 —— 偏好不落檔遠好於畫面崩掉
    }
  }

  return (
    <section className="rounded-md border border-line bg-surface">
      <button
        type="button"
        aria-expanded={open}
        onClick={toggle}
        className="flex w-full items-center gap-2 px-4 py-2 text-left"
      >
        <span className="text-sm font-bold text-ink">相關係數</span>
        <span className="text-xs text-ink-dim">{open ? "收合" : "展開"}</span>
      </button>
      {open ? (
        <div className="px-4 pb-4">
          {/* fallback 文字刻意不用「載入中…」(CorrPanel 空狀態就是那句)—— 測試要能
              逐字區分「仍 suspend」與「CorrPage 已 mount」,同字串會讓斷言失去鑑別力。 */}
          <Suspense
            fallback={<p className="py-6 text-center text-sm text-ink-muted">相關係數載入中…</p>}
          >
            <CorrPage />
          </Suspense>
        </div>
      ) : null}
    </section>
  );
}
