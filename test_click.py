"""Test click pydirectinput (chỉ chạy khi thực thi trực tiếp)."""
import ctypes
import sys
import time


def runMouseClickTest():
    """Chạy kiểm thử di chuyển và click chuột trên Windows."""
    import pydirectinput

    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(2)
    except Exception:
        try:
            ctypes.windll.user32.SetProcessDPIAware()
        except Exception:
            pass

    print("=== Test Controller (pydirectinput) ===")
    print("Click sau 3 giay...")

    for i in range(3, 0, -1):
        pos = pydirectinput.position()
        print(f"  {i}... cursor: {pos}")
        time.sleep(1)

    x, y = pydirectinput.position()
    print(f"Click tai ({x}, {y})")
    pydirectinput.click(x, y)
    print("Done click!")
    time.sleep(0.5)

    for tx, ty in [(100, 100), (500, 400)]:
        pydirectinput.moveTo(tx, ty)
        time.sleep(0.3)
        print(f"Move to ({tx},{ty}) -> actual: {pydirectinput.position()}")

    print("=== XONG ===")


if __name__ == "__main__":
    runMouseClickTest()
