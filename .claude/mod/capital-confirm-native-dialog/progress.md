# Progress ledger — mod/capital-confirm-native-dialog

- [x] §0 開工:branch `mod/capital-confirm-native-dialog`(base 53511b0f)、artifact 目錄
- [x] §1 現況:current-state.md(caller map 4 處、白名單 2 測試、樣板三坑)
- [x] §1 baseline:npm test 110 檔 / 1710 綠、tsc OK、eslint OK(byml5fm11)
- [x] §2 change-spec.md(預核准來源 = triage 文件 §一 + /auto 指令;auto-default 5+5 條)
- [x] §3 round 1:change-spec-reviewer(opus)→ P0×1 P1×3 P2×4,全 accepted,spec 已修訂
- [x] §3 round 2(限縮)→ 2 P1(jsdom 無 showModal 的 stub 手法 / focus spy 目標)+
      1 P2(preventScroll+body 跳過),全 accepted 入 spec
- [x] §4 🔴 red 361fddf3(8 新測試紅、既有 2 綠)
- [x] §4 🔴 green 9ccc4890(14/14 綠;5 caller 測試檔 89/89 綠)
- [x] §4 [lock] bc4fbe2f(unmount 零 callback,mutation-verified)
- [x] §5 自評 review(opus):0 P0 / 0 P1 / 8 P2 → 補強批 6f626e70([lock] ×2
      mutation-verified:settled 旗標 / Esc 不外洩;class 契約補 text-ink/p-0;JSDoc
      硬契約);rejected 3 條記 spec。self_review_head = 6f626e70
- [x] §6 auto-verify 全綠:npm test 1722 / tsc / eslint / react-doctor No issues /
      pytest 2566 / ruff / pyright(validate skip:零 .py diff,理由見 verification.md)
- [x] §6 真實環境:真 Chrome + vite dev(StrictMode)+ fetch-override 假 capital 單,
      SC-1/2/3/4 全 PASS,截圖入 evidence/;user 過目層待收尾回報
- [x] §7 白名單 5 條逐條打勾(verification.md)
- [x] §8.5 沉澱:jsdom dialog stub 教訓入 frontend-testing skill;next-time 2 條
- [ ] §8 收尾:check_feat_tags → artifact commit → branch-lifecycle(push→PR→merge)
