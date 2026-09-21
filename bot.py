"""Bothost entrypoint for CakeStampBot v2.3.5.

Bothost starts `python bot.py`; the active application lives in bot_v182.py.
"""
import os
import sys

if __name__ == "__main__":
    target = os.path.join(os.path.dirname(os.path.abspath(__file__)), "bot_v182.py")
    os.execv(sys.executable, [sys.executable, target])