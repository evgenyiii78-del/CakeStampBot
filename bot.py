"""Bothost entrypoint for CakeStampBot v1.8.3.

Bothost forces `python bot.py`.  Keep this file as a tiny bootstrap and load the
actual compact UI entrypoint from bot_v182.py.
"""
import os
import sys

if __name__ == "__main__":
    target = os.path.join(os.path.dirname(os.path.abspath(__file__)), "bot_v182.py")
    os.execv(sys.executable, [sys.executable, target])
