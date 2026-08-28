# chore/pr-135-followups — change-spec

來源 = `/pr-review 135` 主報告 `docs/superpowers/specs/pr-135-review.md`(完整證據 `.audit.md`,generation `b148dcbc…`)三條 finding,
user 2026-08-28 拍板「開分支修,依序把這三個都修好」。全 Nice to Have、action 全 `auto-fix`。

| # | 位置 | 問題 | 修法(報告 Inline Comment) |
|---|---|---|---|
| F-01 | `tests/server/test_index_routes.py:100-102` | ping `continue` 不計數也無牆鐘上限;推播鏈迴歸時由「紅」退化成「全量 pytest hang」 | ping 小上限,或整段套 `time.monotonic()` 牆鐘預算、逾時印已收則數 |
| F-02 | `tests/capital/balance_rows.py:1` | docstring「唯一定義處」與 `test_client.py:1078 / :1103` 兩列同欄形合成列不符 | 比照 `profit_rows` 明列例外與理由(零風險),或收成常數 |
| F-03 | `tests/server/test_bars.py:603` | 哨兵 docstring 第三子句「擋別的測試把 `_now_time` 改回真牆鐘」機制不成立(autouse 每測試蓋掉) | 刪該子句(純文件) |

白名單:生產碼 `copycat/` 零 diff;斷言語意除 F-01 新增的 deadline `assert` 外不變;順帶把兩份報告從 root 搬進 `docs/superpowers/specs/`(比照 #131 慣例)。
