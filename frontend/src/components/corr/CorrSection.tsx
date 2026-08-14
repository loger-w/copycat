/** 台股綜合頁的相關係數 subtab panel(SC-4)。
 *
 *  **非 active subtab = unmount,不是 `hidden`**(2026-08-14 subtab 改版前是「收合 =
 *  unmount」,掛載閘上移到 `IndexPage` 後語意等價轉移):corr / river 兩條 WS 活在
 *  `CorrPage` 內,不 render 就沒有 hook、沒有連線 —— 台股綜合是預設落地頁,若用專案
 *  慣例的 `hidden` 保 DOM,等於所有人開站就吃兩條每秒推播。代價是切回來有 lazy 載入 +
 *  WS 重連的短暫空窗(design Known Risks KR-2,判定可接受:corr 是即時推播資料,
 *  重建即恢復)。
 *
 *  lazy chunk 邊界不變 —— 原本在 App 層的 `lazy(() => import("./CorrPage"))` 只是移到這裡。 */
import { lazy, Suspense } from "react";

const CorrPage = lazy(() => import("@/components/corr/CorrPage"));

export function CorrSection() {
  return (
    <div data-testid="corr-section" className="px-4 pb-4">
      {/* fallback 文字刻意不用「載入中…」(CorrPanel 空狀態就是那句)—— 測試要能
          逐字區分「仍 suspend」與「CorrPage 已 mount」,同字串會讓斷言失去鑑別力。 */}
      <Suspense fallback={<p className="py-6 text-center text-sm text-ink-muted">相關係數載入中…</p>}>
        <CorrPage />
      </Suspense>
    </div>
  );
}
