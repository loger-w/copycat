# 群益 login probe(CAPITAL_ENV=test 專用):登入序列 → OnAccount 時序/帳號清單(遮罩)
# → GetOpenInterestGW 期貨部位查詢 → (--send-probe 時)遠價 IOC 微台單驗市價 literal。
# 收工 join COM 執行緒;OnReplyMessage 回 -1 抑制彈窗。
from __future__ import annotations

import argparse
import os
import sys
import time


def load_env(path: str = ".env") -> dict[str, str]:
    out: dict[str, str] = {}
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                out[k.strip()] = v.strip()
    return out


def mask(acc: str) -> str:
    return f"****{acc[-4:]}" if len(acc) >= 4 else "****"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--send-probe",
        action="store_true",
        help="送一筆遠價 IOC 微台單驗市價/範圍市價 literal(僅 test 環境)",
    )
    args = parser.parse_args()

    env = load_env()
    if env.get("CAPITAL_ENV", "").lower() != "test":
        print("拒絕執行:CAPITAL_ENV 必須是 test", file=sys.stderr)
        return 2
    user_id = env["CAPITAL_USER_ID"]
    dll_dir = env["CAPITAL_DLL_DIR"]

    os.add_dll_directory(dll_dir)
    import comtypes.client
    import pythoncom

    pythoncom.CoInitialize()
    comtypes.client.GetModule(os.path.join(dll_dir, "SKCOM.dll"))
    import comtypes.gen.SKCOMLib as sk

    center = comtypes.client.CreateObject(sk.SKCenterLib, interface=sk.ISKCenterLib)
    order = comtypes.client.CreateObject(sk.SKOrderLib, interface=sk.ISKOrderLib)
    reply = comtypes.client.CreateObject(sk.SKReplyLib, interface=sk.ISKReplyLib)

    accounts: list[tuple[float, str]] = []
    oi_lines: list[str] = []
    t0 = time.monotonic()

    class ReplyEvents:
        def OnReplyMessage(self, bstrUserID: str, bstrMessages: str) -> int:
            print(f"[{time.monotonic() - t0:6.2f}s] OnReplyMessage: {bstrMessages[:80]}")
            return -1

        def OnConnect(self, bstrUserID: str, nErrorCode: int) -> None:
            print(f"[{time.monotonic() - t0:6.2f}s] OnConnect err={nErrorCode}")

        def OnDisconnect(self, bstrUserID: str, nErrorCode: int) -> None:
            print(f"[{time.monotonic() - t0:6.2f}s] OnDisconnect err={nErrorCode}")

        def OnNewData(self, bstrUserID: str, bstrData: str) -> None:
            print(f"[{time.monotonic() - t0:6.2f}s] OnNewData: {bstrData[:160]}")

    class OrderEvents:
        def OnAccount(self, bstrLogInID: str, bstrAccountData: str) -> None:
            accounts.append((time.monotonic() - t0, bstrAccountData))

        def OnOpenInterest(self, bstrData: str) -> None:
            oi_lines.append(bstrData)
            print(f"[{time.monotonic() - t0:6.2f}s] OnOpenInterest: {bstrData[:120]}")

        def OnOpenInterestGWStatus(self, nQueryStatus: int, bstrErrorMsg: str) -> None:
            print(
                f"[{time.monotonic() - t0:6.2f}s] OnOpenInterestGWStatus {nQueryStatus} {bstrErrorMsg}"
            )

        def OnRealBalanceReport(self, bstrData: str) -> None:
            print(f"[{time.monotonic() - t0:6.2f}s] OnRealBalanceReport: {bstrData[:100]}")

    reply_conn = comtypes.client.GetEvents(reply, ReplyEvents())
    order_conn = comtypes.client.GetEvents(order, OrderEvents())
    _ = (reply_conn, order_conn)  # 防 GC Unadvise

    def pump(seconds: float) -> None:
        end = time.monotonic() + seconds
        while time.monotonic() < end:
            pythoncom.PumpWaitingMessages()
            time.sleep(0.02)

    def rc(label: str, code: int) -> None:
        msg = center.SKCenterLib_GetReturnCodeMessage(code)
        print(f"[{time.monotonic() - t0:6.2f}s] {label} -> {code} {msg}")

    rc("SetAuthority(2=test)", center.SKCenterLib_SetAuthority(2))
    rc("Login", center.SKCenterLib_Login(user_id, env["CAPITAL_PASSWORD"]))
    rc("SKOrderLib_Initialize", order.SKOrderLib_Initialize())
    rc("ReadCertByID", order.ReadCertByID(user_id))
    rc("SKReplyLib_ConnectByID", reply.SKReplyLib_ConnectByID(user_id))

    print("--- GetUserAccount(觀察 OnAccount 事件時序)---")
    rc("GetUserAccount", order.GetUserAccount())
    pump(3.0)
    print(f"OnAccount 共 {len(accounts)} 筆:")
    fut_account: str | None = None
    for ts, raw in accounts:
        parts = raw.split(",")
        # 格式候選:市場,經紀商?,分公司,帳號,身分證,姓名(以實際輸出為準)
        market = parts[0] if parts else "?"
        acc = ""
        for p in parts:
            if p.strip().isdigit() and len(p.strip()) >= 6:
                acc = p.strip()
                break
        print(
            f"  [{ts:6.2f}s] market={market} 欄數={len(parts)} account={mask(acc)} raw欄位0-2={parts[:3]}"
        )
        if market.upper().startswith("TF") and acc:
            fut_account = "".join(parts[1:3]) if len(parts) > 2 else acc
            print(f"    → 期貨帳號候選(分公司+帳號拼接待驗):{mask(acc)}")

    print("--- GetOpenInterestGW(期貨部位)---")
    if fut_account is None and accounts:
        print("(未辨識出 TF 帳號,改用第一筆嘗試)")
    probe_acc = fut_account
    if probe_acc is None and accounts:
        parts = accounts[0][1].split(",")
        probe_acc = "".join(parts[1:3]) if len(parts) > 2 else ""
    if probe_acc:
        rc("GetOpenInterestGW(fmt=1)", order.GetOpenInterestGW(user_id, probe_acc, 1))
        pump(3.0)
        print(f"OnOpenInterest 共 {len(oi_lines)} 行")

    if args.send_probe and probe_acc:
        print("--- send-probe:微台 遠價 IOC(test 環境)---")
        fo = sk.FUTUREORDER()
        fo.bstrFullAccount = probe_acc
        fo.bstrStockNo = "TMFH6"  # 微台 2026-08(近月;若已換月改下一碼)
        fo.sTradeType = 1  # IOC
        fo.sBuySell = 0  # 買
        fo.sDayTrade = 0
        fo.sNewClose = 2  # 自動
        fo.nQty = 1
        fo.bstrPrice = "15000"  # 遠低於市價的限價(不會成交,IOC 立即失效)
        msg, code = order.SendFutureOrder(user_id, False, fo)
        rc(f"SendFutureOrder(limit far) msg={msg}", code)
        fo.bstrPrice = "P"  # 範圍市價 literal 驗證
        fo.sTradeType = 1
        msg, code = order.SendFutureOrder(user_id, False, fo)
        rc(f"SendFutureOrder(bstrPrice=P) msg={msg}", code)
        pump(3.0)

    print("done;pump 殘餘 1s 後收工")
    pump(1.0)
    pythoncom.CoUninitialize()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
