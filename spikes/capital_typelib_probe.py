# 群益 SKCOM typelib 反射 probe(不需登入):dump FUTUREORDER/STOCKORDER struct 欄位、
# ISKOrderLib 送單/刪改減/部位查詢方法簽名 → 供 capital-order PLAN Task 3/5/6 定案。
from __future__ import annotations

import argparse
import ctypes
import inspect
import os
import sys


def dump_struct(sk: object, name: str) -> list[str]:
    out: list[str] = [f"### struct {name}"]
    cls = getattr(sk, name, None)
    if cls is None:
        out.append("(不存在)")
        return out
    fields = getattr(cls, "_fields_", None)
    if fields is None:
        out.append("(無 _fields_)")
        return out
    for fname, ftype in fields:
        out.append(f"- `{fname}`: {getattr(ftype, '__name__', ftype)}")
    return out


def dump_methods(sk: object, iface_name: str, keywords: tuple[str, ...]) -> list[str]:
    out: list[str] = [f"### interface {iface_name}(關鍵字命中方法)"]
    iface = getattr(sk, iface_name, None)
    if iface is None:
        out.append("(不存在)")
        return out
    names = sorted(n for n in dir(iface) if any(k.lower() in n.lower() for k in keywords))
    for n in names:
        m = getattr(iface, n, None)
        try:
            sig = str(inspect.signature(m)) if callable(m) else ""
        except (TypeError, ValueError):
            sig = "(comtypes slot)"
        out.append(f"- `{n}{sig}`")
    return out


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dll-dir", default=os.environ.get("CAPITAL_DLL_DIR", ""))
    parser.add_argument("--out", default="docs/research/2026-07-28-skcom-typelib.md")
    args = parser.parse_args()
    if not args.dll_dir:
        print("需要 --dll-dir 或 CAPITAL_DLL_DIR", file=sys.stderr)
        return 2

    os.add_dll_directory(args.dll_dir)
    import comtypes.client

    comtypes.client.GetModule(os.path.join(args.dll_dir, "SKCOM.dll"))
    import comtypes.gen.SKCOMLib as sk

    lines: list[str] = [
        "# SKCOM typelib dump(capital-order Task 0)",
        "",
        f"來源:{os.path.join(args.dll_dir, 'SKCOM.dll')}",
        "",
    ]
    for struct in (
        "STOCKORDER",
        "FUTUREORDER",
        "OPTIONORDER",
        "TSPROFITLOSSGWQUERY",
        "FUTUREORDERFORDAYTRADE",
    ):
        lines += dump_struct(sk, struct)
        lines.append("")
    lines += dump_methods(
        sk,
        "ISKOrderLib",
        (
            "SendStock",
            "SendFuture",
            "SendOption",
            "Cancel",
            "Correct",
            "Decrease",
            "GetOpenInterest",
            "GetRealBalance",
            "GetProfitLoss",
            "Initialize",
            "ReadCert",
            "GetUserAccount",
            "GetFutureRights",
            "AccountInfo",
        ),
    )
    lines.append("")
    lines += dump_methods(
        sk,
        "ISKOrderLibEvents",
        ("OnAccount", "OnOpenInterest", "OnRealBalance", "OnProfitLoss", "OnFutureRights"),
    )
    lines.append("")
    lines += dump_methods(
        sk, "ISKReplyLibEvents", ("OnNewData", "OnConnect", "OnDisconnect", "OnReplyMessage")
    )
    lines.append("")
    lines += dump_methods(sk, "ISKCenterLib", ("Login", "SetAuthority", "GetReturnCodeMessage"))

    # ctypes struct 大小佐證(欄位順序正確性 sanity)
    for struct in ("STOCKORDER", "FUTUREORDER"):
        cls = getattr(sk, struct, None)
        if cls is not None:
            lines.append(f"\nsizeof({struct}) = {ctypes.sizeof(cls)}")

    text = "\n".join(lines) + "\n"
    with open(args.out, "w", encoding="utf-8") as fh:
        fh.write(text)
    print(text)
    print(f"[written] {args.out}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
