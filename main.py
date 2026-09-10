"""
main.py – Điểm khởi chạy duy nhất của VBPL Scraper.

Chạy bằng lệnh:
    python d:\Data\tttttttt\vbpl_scraper\main.py
"""

import sys
import os

# Thêm thư mục gốc vào sys.path để import các module con hoạt động đúng
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from gui.app_gui import ScraperApp

if __name__ == "__main__":
    app = ScraperApp()
    app.mainloop()
