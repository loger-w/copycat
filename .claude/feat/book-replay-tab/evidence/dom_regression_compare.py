"""#268 既有分頁回歸:舊頁(備份)與新頁同樣操作後各區塊 innerHTML 比對。

左欄與活潑日索引刻意多了「非群組(簿重播)」一段(接在最後)→ 判準改成「舊內容原樣是新內容的前綴」;
活潑日索引另去掉開頭總數那一句(總數含新增)。其餘區塊須完全相同。
用法:python dom_regression_compare.py cap_old.json cap_new.json
"""

import json
import sys


def load(path):
    text = open(path, encoding="utf-8").read()
    return (
        json.loads(text[text.index("[") :])
        if not text.lstrip().startswith("[")
        else json.loads(text)
    )


old, new = load(sys.argv[1]), load(sys.argv[2])
labels = ["2426|09-16", "8064|09-09", "1815|07-01", "3441|09-10", "2344|08-20", "互動後 2426|09-16"]
bad = 0
for label, o, n in zip(labels, old, new):
    res = {}
    for k in o:
        if k in ("rail", "idx"):
            ok = n[k].startswith(o[k])
            res[k] = "前綴相同" if ok and n[k] != o[k] else "相同" if ok else "不同"
        else:
            ok = n[k] == o[k]
            res[k] = "相同" if ok else "不同"
        bad += not ok
    print(label, res)
print("不符區塊數:", bad, "/", sum(len(o) for o in old))
