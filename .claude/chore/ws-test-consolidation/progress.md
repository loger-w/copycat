# Progress ledger:chore/ws-test-consolidation(/auto 第 2 輪)

來源:docs/next-time.md「2026-08-04(asyncio-socket-send-warning 收尾留尾巴)」前兩條 +
「WS 突斷整合覆蓋」條(查證註記;FakeIndexSource ×3 / futures_source 參數名已於
remove-tc4-trade-path 增量 review 校正)。

定界:測試-only。**不做**:production code(ws.py/app.py)、`test_no_write_to_dead_transport`
的 0.5s flake 窗修正(獨立 next-time 條目)。

`[auto-default: 「真環境重現」以真 uvicorn + 真 socket + fake source 落地,不重啟 prod
server | reason: 夜盤時段不起第二台連 TC4 的後端(CLAUDE.md §8 紀律);prod 級關機驗證
等下次自然重啟窗口,shutdown 鏈(uvicorn should_exit → WS relay 收尾)在 fake source
下與 prod 同構]`

- [x] Task 1:3fc08b1(🔵 helpers 收斂,前後皆 1626 passed)+ deefa0e(🟢 shutdown 回歸 +
  六路 parametrize,1633 passed)。真環境重現:真 uvicorn 保持連線 should_exit → 0.28s 關機
  乾淨;負向對照(relay 換 send-only)紅。六路零排除,mutation 六路全紅非 vacuous。
- [x] review gate(C 節一輪 medium,雙 lens):0 P0/P1 / 7 P2 全 accepted → 修於 9869490
  (R-3 記帳不重寫歷史)。reviewer 的 ws.py 暫時 mutation 已還原並複核。
- [x] gate:全套 1633 passed / ruff 0 / pyright 0;test_ws_disconnect ×6 唯二失敗 =
  既有 handshake flake(HEAD 前版本對照重現;本輪新 13 條零失敗)。frontend 零觸碰不跑
  npm gate。
- [x] next-time 打勾(shutdown 條 + WS 突斷條)+ 新沉澱節(第二 flake 源 /
  DISCORD_WEBHOOK_URL conftest 全域中和候選 / corr_tick_secs 透出候選)
- [ ] branch-lifecycle 收尾(push/PR/merge)

`[auto-default: 既有 flake(_ws_handshake 吞首 frame)不順手修 | reason: 需動既有斷言,
超出 chore 授權;next-time 已有專條(兩個 flake 源一起收)]`
`[auto-default: timeout_graceful_shutdown 只加六路 | reason: 加在 shutdown 測試會讓被測
bug 在期限內被強制收尾 → 測試永遠綠(mutation 實測 20.10s 才 FAIL 為證)]`
