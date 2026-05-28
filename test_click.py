"""Test click pydirectinput"""
import time
import ctypes
import pydirectinput
import sys

sys.stdout.reconfigure(encoding='utf-8')

try:
    ctypes.windll.shcore.SetProcessDpiAwareness(2)
except Exception:
    ctypes.windll.user32.SetProcessDPIAware()

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

# Test move
pydirectinput.moveTo(100, 100)
time.sleep(0.3)
actual = pydirectinput.position()
print(f"Move to (100,100) -> actual: {actual}")

pydirectinput.moveTo(500, 400)
time.sleep(0.3)
actual = pydirectinput.position()
print(f"Move to (500,400) -> actual: {actual}")

print("=== XONG ===")
