# app.py - 安全啟動器：載入 aurum_gui.py 並強制呼叫 main()
import sys, traceback
from pathlib import Path
import importlib.util

BASE = Path(__file__).resolve().parent
target = BASE / "aurum_gui.py"

print(f"[launcher] 啟動中，尋找：{target}")
if not target.exists():
    raise FileNotFoundError(f"找不到 {target}")

try:
    # 以模組方式載入 aurum_gui.py
    spec = importlib.util.spec_from_file_location("aurum_gui", str(target))
    mod = importlib.util.module_from_spec(spec)
    sys.modules["aurum_gui"] = mod
    spec.loader.exec_module(mod)
    print("[launcher] aurum_gui 載入成功")

    # 強制呼叫 main()（就算檔案底部沒有 if __name__ == '__main__' 也能跑）
    if hasattr(mod, "main") and callable(mod.main):
        print("[launcher] 呼叫 aurum_gui.main() …")
        mod.main()
        print("[launcher] aurum_gui.main() 已結束")
    else:
        print("[launcher] 警告：aurum_gui.py 裡沒有 main()，因此沒有任何東西可執行。")
except Exception:
    # 任何錯誤 → 同步寫入 error.log 並在主控台印出
    with open(BASE / "error.log", "w", encoding="utf-8") as f:
        traceback.print_exc(file=f)
    traceback.print_exc()
    sys.exit(1)
