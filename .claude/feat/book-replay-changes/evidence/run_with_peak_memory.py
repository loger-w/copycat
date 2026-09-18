"""#269 量測:跑一個子程序,結束後讀它的峰值工作集(Windows GetProcessMemoryInfo),印耗時與峰值。

#275 那次用 PowerShell 輪詢 venv python.exe 量到 0(venv 啟動器另開子程序);這裡直接拿 Popen 的程序
handle 讀 PeakWorkingSetSize。venv 的 python.exe 是啟動器 → 實際工作的是它的子程序,所以同時列出
結束前掃到的**直屬子程序**峰值(每 0.5 秒掃一次,取最大;pr-279 review F-32:children_of 只比
th32ParentProcessID == pid,不會往下追孫程序 —— 若指令本身還會 fork 出子程序的子程序,這裡量不到)。
讀的是 PeakWorkingSetSize(實體駐留工作集),記憶體吃緊、工作集被系統修剪時會低估實際需求;
同時印 PeakPagefileUsage(committed)供對照。

用法:python run_with_peak_memory.py <指令…>
"""

from __future__ import annotations

import ctypes
import ctypes.wintypes as wt
import subprocess
import sys
import time

PROCESS_QUERY_INFORMATION = 0x0400
PROCESS_VM_READ = 0x0010
TH32CS_SNAPPROCESS = 0x00000002


class PROCESS_MEMORY_COUNTERS(ctypes.Structure):
    _fields_ = [
        ("cb", wt.DWORD),
        ("PageFaultCount", wt.DWORD),
        ("PeakWorkingSetSize", ctypes.c_size_t),
        ("WorkingSetSize", ctypes.c_size_t),
        ("QuotaPeakPagedPoolUsage", ctypes.c_size_t),
        ("QuotaPagedPoolUsage", ctypes.c_size_t),
        ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t),
        ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
        ("PagefileUsage", ctypes.c_size_t),
        ("PeakPagefileUsage", ctypes.c_size_t),
    ]


class PROCESSENTRY32(ctypes.Structure):
    _fields_ = [
        ("dwSize", wt.DWORD),
        ("cntUsage", wt.DWORD),
        ("th32ProcessID", wt.DWORD),
        ("th32DefaultHeapID", ctypes.c_void_p),
        ("th32ModuleID", wt.DWORD),
        ("cntThreads", wt.DWORD),
        ("th32ParentProcessID", wt.DWORD),
        ("pcPriClassBase", ctypes.c_long),
        ("dwFlags", wt.DWORD),
        ("szExeFile", ctypes.c_char * 260),
    ]


kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
psapi = ctypes.WinDLL("psapi", use_last_error=True)


def peak_of_handle(handle: int) -> tuple[int, int]:
    """回傳 (PeakWorkingSetSize, PeakPagefileUsage);讀不到回傳 (-1, -1)。"""
    counters = PROCESS_MEMORY_COUNTERS()
    counters.cb = ctypes.sizeof(counters)
    if not psapi.GetProcessMemoryInfo(wt.HANDLE(handle), ctypes.byref(counters), counters.cb):
        return -1, -1
    return counters.PeakWorkingSetSize, counters.PeakPagefileUsage


def children_of(pid: int) -> list[int]:
    snap = kernel32.CreateToolhelp32Snapshot(TH32CS_SNAPPROCESS, 0)
    entry = PROCESSENTRY32()
    entry.dwSize = ctypes.sizeof(entry)
    out: list[int] = []
    ok = kernel32.Process32First(snap, ctypes.byref(entry))
    while ok:
        if entry.th32ParentProcessID == pid:
            out.append(entry.th32ProcessID)
        ok = kernel32.Process32Next(snap, ctypes.byref(entry))
    kernel32.CloseHandle(snap)
    return out


def main() -> int:
    started = time.monotonic()
    proc = subprocess.Popen(sys.argv[1:])
    child_handles: dict[int, int] = {}
    while proc.poll() is None:
        for pid in children_of(proc.pid):
            if pid not in child_handles:
                h = kernel32.OpenProcess(PROCESS_QUERY_INFORMATION | PROCESS_VM_READ, False, pid)
                if h:
                    child_handles[pid] = h
        time.sleep(0.5)
    elapsed = time.monotonic() - started
    own_ws, own_pf = peak_of_handle(int(proc._handle))  # type: ignore[attr-defined]
    kids = {pid: peak_of_handle(h) for pid, h in child_handles.items()}
    print(
        f"[run_with_peak_memory] exit={proc.returncode} elapsed={elapsed:.1f}s "
        f"peak_ws_self={own_ws / 1e9:.2f}GB peak_pagefile_self={own_pf / 1e9:.2f}GB peak_ws_children="
        + ", ".join(
            f"{pid}:ws={ws / 1e9:.2f}GB,pf={pf / 1e9:.2f}GB" for pid, (ws, pf) in kids.items()
        )
    )
    return proc.returncode


if __name__ == "__main__":
    raise SystemExit(main())
