"""群益 COM 封裝。CapitalCom 是介面;SkcomCapitalCom 是真實 comtypes 實作。

真實實作的所有方法都必須在「同一條」CoInitialize 過的執行緒上呼叫
(COM apartment 親和性)—— 由 CapitalClient 的專屬執行緒保證。

comtypes / pythoncom 一律不在 module 頂層 import(CI 無 COM 環境也要能
import copycat.capital.com);函式內走 importlib.import_module 動態載入,
pyright 對 ModuleType 屬性存取視為 Any,不需 ignore 註記。

COM 簽名定案:docs/research/2026-07-28-skcom-typelib.md(期權共用 FUTUREORDER、
刪改減共用證券 BySeqNo 家族、GetOpenInterestGW → OnOpenInterest 事件)。
"""

from __future__ import annotations

import importlib
import logging
import os
import time
from collections.abc import Callable
from typing import Any, Protocol

logger = logging.getLogger(__name__)


class CapitalCom(Protocol):
    def setup(
        self,
        on_reply: Callable[[str], None] | None = None,
        on_balance: Callable[[str], None] | None = None,
        on_profit: Callable[[str], None] | None = None,
        on_reply_disconnect: Callable[[int], None] | None = None,
        on_open_interest: Callable[[str], None] | None = None,
    ) -> None: ...
    def set_authority(self, flag: int) -> int: ...  # 0=正式 2=測試
    def login(self, user_id: str, password: str) -> int: ...
    def init_order(self) -> int: ...
    def read_cert(self, user_id: str) -> int: ...
    def connect_reply(self, user_id: str) -> int: ...  # 連回報主機,OnNewData 才會推
    def send_stock_order(self, user_id: str, fields: dict[str, object]) -> tuple[str, int]: ...
    def send_future_order(
        self, user_id: str, fields: dict[str, object], *, is_option: bool
    ) -> tuple[str, int]: ...  # 期權共用 FUTUREORDER struct;is_option 決定 SendOptionOrder
    def cancel_order(self, user_id: str, full_account: str, seq_no: str) -> tuple[str, int]: ...
    def correct_price(
        self, user_id: str, full_account: str, seq_no: str, price: float
    ) -> tuple[str, int]: ...
    def decrease_qty(
        self, user_id: str, full_account: str, seq_no: str, qty: int
    ) -> tuple[str, int]: ...
    def get_real_balance(self, user_id: str, full_account: str) -> int: ...  # OnRealBalanceReport
    def get_profit_loss_gw(self, user_id: str, full_account: str) -> int: ...  # OnProfitLossGW
    def get_user_accounts(self, timeout_s: float = 3.0) -> list[tuple[str, str]]: ...
    def get_open_interest(self, user_id: str, futures_account: str) -> int: ...  # OnOpenInterest
    def return_code_message(self, code: int) -> str: ...
    def pump(self) -> None: ...


def _resolve_skcom_load(dll_dir: str | None) -> tuple[str | None, str]:
    """決定 SKCOM.dll 載入方式 → (要加進 DLL 搜尋路徑的資料夾 or None, 給 GetModule 的引數)。

    有設 dll_dir → 絕對路徑載入(穩,不靠行程 CWD/PATH,且把元件資料夾加進搜尋路徑,
    SKCOM.dll 的相依 DLL 才載得到);沒設(None/空白)→ 裸檔名,沿用舊行為。
    """
    d = (dll_dir or "").strip()
    if not d:
        return None, "SKCOM.dll"
    return d, os.path.join(d, "SKCOM.dll")


def _parse_account_row(raw: str) -> tuple[str, str] | None:
    """OnAccount 的 bstrAccountData 一列 → (market_prefix, full_account);畸形列回 None 略過。

    欄序依群益官方 Python 範例 Order.py 慣例(`市場,經紀商,分公司,帳號,身分證,姓名`):
    market = 欄 0 前 2 碼上大寫(TS=證券/TF=期貨),full_account = parts[1] + parts[3]。
    **欄序 prod 實測後校正** —— test 沙盒帳號未開通(1097),OnAccount 實際欄序無法先驗,
    首次 prod 登入要對群益 App 核對後修正此處與測試治具。
    """
    parts = [p.strip() for p in raw.split(",")]
    if len(parts) < 4 or not parts[0]:
        return None
    market = parts[0][:2].upper()
    full_account = parts[1] + parts[3]
    if not full_account:
        return None
    return market, full_account


class SkcomCapitalCom:
    """真實群益 SKCOM 實作(comtypes)。"""

    def __init__(self, dll_dir: str | None = None) -> None:
        self._dll_dir = dll_dir
        self._dll_cookie: object | None = None  # os.add_dll_directory handle,存著避免被 GC
        self._reply_sink: _ReplyEvents | None = None
        self._reply_conn: object | None = None  # GetEvents advise 連線,存著避免 GC → Unadvise
        self._order_sink: _OrderEvents | None = None  # OrderLib 事件 sink,同樣防 GC
        self._order_conn: object | None = None
        self._sk: Any = None
        self._center: Any = None
        self._order: Any = None
        self._reply: Any = None

    def setup(
        self,
        on_reply: Callable[[str], None] | None = None,
        on_balance: Callable[[str], None] | None = None,
        on_profit: Callable[[str], None] | None = None,
        on_reply_disconnect: Callable[[int], None] | None = None,
        on_open_interest: Callable[[str], None] | None = None,
    ) -> None:
        comtypes_client = importlib.import_module("comtypes.client")
        add_dir, module_arg = _resolve_skcom_load(self._dll_dir)
        if add_dir:
            if not os.path.isdir(add_dir):
                raise FileNotFoundError(f"CAPITAL_DLL_DIR 不存在: {add_dir}")
            # Python 3.8+ 安全 DLL 搜尋:把元件資料夾加進去,相依(SKWebCALib 等)才載得到
            self._dll_cookie = os.add_dll_directory(add_dir)
        comtypes_client.GetModule(module_arg)
        sk = importlib.import_module("comtypes.gen.SKCOMLib")
        self._sk = sk
        self._center = comtypes_client.CreateObject(sk.SKCenterLib, interface=sk.ISKCenterLib)
        self._order = comtypes_client.CreateObject(sk.SKOrderLib, interface=sk.ISKOrderLib)
        self._reply = comtypes_client.CreateObject(sk.SKReplyLib, interface=sk.ISKReplyLib)
        # OnReplyMessage 回 -1 抑制群益彈窗;OnNewData 主動回報轉給 on_reply。
        # sink 與 advise 連線都存住:丟掉會被 GC → Unadvise,登入即報
        # SK_WARNING_REGISTER_REPLYLIB_ONREPLYMESSAGE_FIRST。
        self._reply_sink = _ReplyEvents(on_reply, on_disconnect=on_reply_disconnect)
        self._reply_conn = comtypes_client.GetEvents(self._reply, self._reply_sink)
        self._order_sink = _OrderEvents(on_balance, on_profit, on_open_interest)
        self._order_conn = comtypes_client.GetEvents(self._order, self._order_sink)

    def set_authority(self, flag: int) -> int:
        return self._center.SKCenterLib_SetAuthority(flag)

    def login(self, user_id: str, password: str) -> int:
        return self._center.SKCenterLib_Login(user_id, password)

    def init_order(self) -> int:
        return self._order.SKOrderLib_Initialize()

    def read_cert(self, user_id: str) -> int:
        return self._order.ReadCertByID(user_id)

    def connect_reply(self, user_id: str) -> int:
        # 連上回報主機後,OnNewData 才會推委託/成交/刪單回報(並重播當日 backlog)。
        return self._reply.SKReplyLib_ConnectByID(user_id)

    def send_stock_order(self, user_id: str, fields: dict[str, object]) -> tuple[str, int]:
        order = self._sk.STOCKORDER()
        for k, v in fields.items():
            setattr(order, k, v)
        # bAsync=0 同步,回 (message, nCode)
        message, code = self._order.SendStockOrder(user_id, 0, order)
        return message, code

    def send_future_order(
        self, user_id: str, fields: dict[str, object], *, is_option: bool
    ) -> tuple[str, int]:
        # 期權共用 FUTUREORDER struct(typelib 無 OPTIONORDER);未賦值欄位為零值。
        order = self._sk.FUTUREORDER()
        for k, v in fields.items():
            setattr(order, k, v)
        if is_option:
            message, code = self._order.SendOptionOrder(user_id, 0, order)
        else:
            message, code = self._order.SendFutureOrder(user_id, 0, order)
        return message, code

    def cancel_order(self, user_id: str, full_account: str, seq_no: str) -> tuple[str, int]:
        # 證券/期權共用 BySeqNo 家族;期權單由呼叫端帶期貨帳號。
        message, code = self._order.CancelOrderBySeqNo(user_id, 0, full_account, seq_no)
        return message, code

    def correct_price(
        self, user_id: str, full_account: str, seq_no: str, price: float
    ) -> tuple[str, int]:
        # 末參數 nTradeType=0(ROD),同官方範例;價格字串化 %.2f 與送單一致
        message, code = self._order.CorrectPriceBySeqNo(
            user_id, 0, full_account, seq_no, f"{price:.2f}", 0
        )
        return message, code

    def decrease_qty(
        self, user_id: str, full_account: str, seq_no: str, qty: int
    ) -> tuple[str, int]:
        # qty 單位=證券張/期貨口(與送單 nQty 同慣例)
        message, code = self._order.DecreaseOrderBySeqNo(user_id, 0, full_account, seq_no, qty)
        return message, code

    def get_real_balance(self, user_id: str, full_account: str) -> int:
        # 非同步查詢:nCode 同步回,結果走 OnRealBalanceReport 事件
        return self._order.GetRealBalanceReport(user_id, full_account)

    def get_profit_loss_gw(self, user_id: str, full_account: str) -> int:
        # 未實現損益試算(彙總、全部商品);結果走 OnProfitLossGWReport 事件。
        # 字串欄一律帶空字串 — comtypes 未設的 BSTR 是 None,群益端行為未定義
        q = self._sk.TSPROFITLOSSGWQUERY()
        q.bstrFullAccount = full_account
        q.nTPQueryType = 0  # 0=未實現
        q.nFunc = 0  # 0=彙總
        q.bstrStockNo = ""
        q.bstrTradeType = ""
        q.bstrStartDate = ""
        q.bstrEndDate = ""
        q.bstrBookNo = ""
        q.bstrSeqNo = ""
        return self._order.GetProfitLossGWReport(user_id, q)

    def get_user_accounts(self, timeout_s: float = 3.0) -> list[tuple[str, str]]:
        """GetUserAccount → pump 迴圈收 OnAccount 事件到 timeout(review R6)。

        OnAccount 逐筆推、沒有「收完」訊號 → 只能以 timeout 收束;啟動時呼叫一次,
        3 秒成本可接受。回 (market_prefix, full_account) 清單,畸形列略過。
        """
        sink = self._order_sink
        if sink is None:
            raise RuntimeError("setup() 尚未呼叫,OnAccount sink 不存在")
        sink.accounts.clear()
        code = self._order.GetUserAccount()
        if code != 0:
            logger.warning("GetUserAccount 回傳碼 %s(仍等待 OnAccount 到 timeout)", code)
        deadline = time.monotonic() + timeout_s
        while time.monotonic() < deadline:
            self.pump()
            time.sleep(0.05)
        out: list[tuple[str, str]] = []
        for raw in sink.accounts:
            parsed = _parse_account_row(raw)
            if parsed is None:
                logger.warning("OnAccount 帳號列格式不符,略過: %r", raw)
                continue
            out.append(parsed)
        return out

    def get_open_interest(self, user_id: str, futures_account: str) -> int:
        # 非同步查詢:nCode 同步回,資料列走 OnOpenInterest、狀態走 OnOpenInterestGWStatus
        return self._order.GetOpenInterestGW(user_id, futures_account, 1)

    def return_code_message(self, code: int) -> str:
        return self._center.SKCenterLib_GetReturnCodeMessage(code)

    def pump(self) -> None:
        pythoncom = importlib.import_module("pythoncom")
        pythoncom.PumpWaitingMessages()


class _ReplyEvents:
    """SKReplyLib 事件 sink;回呼例外不可炸掉 COM 事件迴圈。"""

    def __init__(
        self,
        on_reply: Callable[[str], None] | None = None,
        on_disconnect: Callable[[int], None] | None = None,
    ) -> None:
        self._on_reply = on_reply
        self._on_disconnect = on_disconnect

    def OnReplyMessage(self, bstrUserID: str, bstrMessage: str) -> int:
        return -1  # 群益慣例:回 -1 抑制彈窗

    def OnConnect(self, bstrUserID: str, nErrorCode: int) -> None:
        # 回報主機連線結果;0=成功,之後 OnNewData 才會推(含當日 backlog)。
        if nErrorCode == 0:
            logger.info("Capital reply connected (user=%s)", bstrUserID)
        else:
            logger.warning("Capital reply connect error (user=%s, code=%s)", bstrUserID, nErrorCode)

    def OnDisconnect(self, bstrUserID: str, nErrorCode: int) -> None:
        # 回報主機斷線(comtypes 對 sink 未實作的事件靜默忽略 → 不掛就偵測不到)。
        # 只做偵測+通知降級;自動重連需先 store.clear() 防成交重複累計,另案處理。
        logger.error("Capital reply disconnected (user=%s, code=%s)", bstrUserID, nErrorCode)
        if self._on_disconnect:
            try:
                self._on_disconnect(nErrorCode)
            except Exception:
                logger.exception("reply 斷線回呼例外(已忽略,COM 事件迴圈不可炸)")

    def OnNewData(self, bstrUserID: str, bstrData: str) -> None:
        # 主動回報(委託/成交)轉給 client;回呼例外不可炸 COM 迴圈,但必須留痕 —
        # 這代表一筆委託/成交回報被丟棄,委託面板會跟市場脫節
        if self._on_reply:
            try:
                self._on_reply(bstrData)
            except Exception:
                logger.exception("reply 回呼例外,該筆回報丟棄: %r", bstrData)


class _OrderEvents:
    """SKOrderLib 事件 sink(帳號清單+即時庫存+損益+期貨部位);回呼例外不可炸 COM 迴圈。"""

    def __init__(
        self,
        on_balance: Callable[[str], None] | None = None,
        on_profit: Callable[[str], None] | None = None,
        on_open_interest: Callable[[str], None] | None = None,
    ) -> None:
        self._on_balance = on_balance
        self._on_profit = on_profit
        self._on_open_interest = on_open_interest
        self.accounts: list[str] = []  # OnAccount 原始列;get_user_accounts 清空後收集

    def OnAccount(self, bstrLogInID: str, bstrAccountData: str) -> None:
        # GetUserAccount 後逐筆推;只收集原始列,解析在 get_user_accounts(可測純邏輯)
        self.accounts.append(bstrAccountData)

    def OnRealBalanceReport(self, bstrData: str) -> None:
        if self._on_balance:
            try:
                self._on_balance(bstrData)
            except Exception:
                logger.exception("balance 回呼例外,該筆庫存事件丟棄: %r", bstrData)

    def OnProfitLossGWReport(self, bstrData: str) -> None:
        if self._on_profit:
            try:
                self._on_profit(bstrData)
            except Exception:
                logger.exception("profit 回呼例外,該筆損益事件丟棄: %r", bstrData)

    def OnOpenInterest(self, bstrData: str) -> None:
        # 期貨未平倉部位資料列(GetOpenInterestGW 觸發)
        if self._on_open_interest:
            try:
                self._on_open_interest(bstrData)
            except Exception:
                logger.exception("open-interest 回呼例外,該筆部位事件丟棄: %r", bstrData)

    def OnOpenInterestGWStatus(self, nQueryStatus: int, bstrErrorMsg: str) -> None:
        # 查詢狀態通知;只留 log(client 以 OnOpenInterest 資料列為準)
        if bstrErrorMsg:
            logger.warning("Capital open-interest 查詢狀態 %s: %s", nQueryStatus, bstrErrorMsg)
        else:
            logger.debug("Capital open-interest 查詢狀態 %s", nQueryStatus)
