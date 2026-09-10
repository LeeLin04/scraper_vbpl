"""
gui/app_gui.py – Giao diện Tkinter đa luồng cho VBPL Scraper.

KIẾN TRÚC MỚI (SQLite-backed):
  - Thread Search : duyệt keyword → search_documents() → enqueue_many() vào SQLite
                    ngay lập tức, không giữ URL trong RAM.
  - Thread Worker : vòng lặp liên tục fetch_next_pending() → scrape_url() →
                    mark_done/error. Chạy song song với Thread Search.

  Ưu điểm:
    - RAM không tăng dù có hàng nghìn URL (URL nằm trên đĩa, trong SQLite).
    - Crash bất kỳ lúc nào → khởi động lại sẽ tự resume (pending còn trong DB).
    - Văn bản hết hiệu lực bị lọc ngay từ kết quả search (EXPIRED_POLICY='skip'),
      đánh dấu 'skipped' trong SQLite, không cào.

Giữ nguyên từ phiên bản cũ:
  - PanedWindow 2 cột (Log | Kết quả).
  - 3 trạng thái: Bắt đầu / Tạm dừng / Dừng hẳn bằng threading.Event.
  - Thanh tiến trình Progress Bar.
  - Ghi nhật ký hoạt động Thread-safe (widget.after).
"""

import json
import logging
import os
import random
import threading
import time
import tkinter as tk
import tkinter.ttk as ttk
from tkinter import messagebox, scrolledtext

from playwright.sync_api import sync_playwright

import sys
# Đảm bảo import được từ thư mục gốc vbpl_scraper
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config import (
    KEY_PATH, USER_AGENTS,
    WAIT_BETWEEN_KEYWORDS, WAIT_BETWEEN_URLS,
    MAX_RETRIES, RETRY_DELAY_SECONDS,
)
from scraper.api_client import search_documents
from scraper.engine import scrape_url
from utils import db_queue
from utils.text_utils import clean_text


# =========================================================================
# TEXT HANDLER – Ghi log Thread-safe lên ScrolledText
# =========================================================================

class _TextHandler(logging.Handler):
    """Chuyển hướng logging Python vào widget Tkinter ScrolledText."""

    def __init__(self, text_widget: scrolledtext.ScrolledText):
        super().__init__()
        self._widget = text_widget

    def emit(self, record):
        msg = self.format(record)

        def _append():
            self._widget.configure(state="normal")
            self._widget.insert(tk.END, msg + "\n")
            self._widget.configure(state="disabled")
            self._widget.yview(tk.END)

        self._widget.after(0, _append)


# =========================================================================
# MAIN GUI APP
# =========================================================================

class ScraperApp(tk.Tk):

    def __init__(self):
        super().__init__()
        self.title("🏛️ VBPL Scraper — Cào Văn Bản Pháp Luật")
        self.geometry("1100x680")
        self.minsize(750, 480)
        self.resizable(True, True)

        # Threading events
        self.pause_event = threading.Event()
        self.pause_event.set()
        self.stop_event = threading.Event()
        self.is_running = False

        # Khởi tạo SQLite DB và reset stuck URLs
        db_queue.init_db()
        stuck = db_queue.reset_processing()
        if stuck > 0:
            logging.info(f"♻️ Resume: reset {stuck} URL bị stuck về pending.")

        self._build_ui()
        self._setup_logging()

        # Cập nhật stats bar định kỳ
        self._update_stats_bar()

    # ------------------------------------------------------------------
    # UI
    # ------------------------------------------------------------------

    def _build_ui(self):
        # === Thanh điều khiển trên cùng ===
        ctrl_frame = tk.Frame(self, pady=6)
        ctrl_frame.pack(fill=tk.X, padx=10)

        self.start_btn = tk.Button(
            ctrl_frame, text="▶ Bắt đầu", width=12,
            bg="#27ae60", fg="white", font=("Arial", 10, "bold"),
            command=self._start_keywords,
        )
        self.start_btn.pack(side=tk.LEFT, padx=3)

        self.pause_btn = tk.Button(
            ctrl_frame, text="⏸ Tạm dừng", width=12,
            state=tk.DISABLED, font=("Arial", 10),
            command=self._toggle_pause,
        )
        self.pause_btn.pack(side=tk.LEFT, padx=3)

        self.stop_btn = tk.Button(
            ctrl_frame, text="⏹ Dừng hẳn", width=12,
            bg="#e74c3c", fg="white", state=tk.DISABLED,
            font=("Arial", 10, "bold"), command=self._stop,
        )
        self.stop_btn.pack(side=tk.LEFT, padx=3)

        tk.Button(
            ctrl_frame, text="🗑 Xóa Log", width=10,
            font=("Arial", 10), command=self._clear_log,
        ).pack(side=tk.LEFT, padx=3)

        # Ô nhập URL đơn lẻ
        tk.Label(ctrl_frame, text="  URL đơn:").pack(side=tk.LEFT)
        self._url_var = tk.StringVar()
        url_entry = tk.Entry(ctrl_frame, textvariable=self._url_var, width=40)
        url_entry.pack(side=tk.LEFT, padx=4)

        tk.Button(
            ctrl_frame, text="Cào URL này",
            bg="#2980b9", fg="white", font=("Arial", 9, "bold"),
            command=self._start_single_url,
        ).pack(side=tk.LEFT)

        # === Progress bar ===
        pg_frame = tk.Frame(self)
        pg_frame.pack(fill=tk.X, padx=10, pady=3)

        self._progress_lbl = tk.Label(
            pg_frame, text="Tiến độ: 0/0 từ khóa", font=("Arial", 9),
        )
        self._progress_lbl.pack(side=tk.LEFT, padx=5)

        self._progress_bar = ttk.Progressbar(
            pg_frame, orient=tk.HORIZONTAL, mode="determinate",
        )
        self._progress_bar.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=5)

        # === Status bar (SQLite stats) ===
        self._stats_lbl = tk.Label(
            self,
            text="DB: Hàng chờ: — | Đang cào: — | Xong: — | Lỗi: — | Bỏ qua: —",
            font=("Consolas", 8), fg="#555555", anchor="w",
            relief=tk.SUNKEN, bd=1,
        )
        self._stats_lbl.pack(fill=tk.X, padx=10, pady=(0, 3))

        # === PanedWindow: Log (trái) | Kết quả (phải) ===
        pane = tk.PanedWindow(
            self, orient=tk.HORIZONTAL,
            sashwidth=6, sashrelief=tk.RAISED, bg="#aaaaaa",
        )
        pane.pack(expand=True, fill=tk.BOTH, padx=10, pady=5)

        # Log
        log_frame = tk.Frame(pane)
        tk.Label(
            log_frame, text="Nhật ký hoạt động:", font=("Arial", 9, "bold"),
        ).pack(anchor=tk.W)
        self.log_text = scrolledtext.ScrolledText(
            log_frame, state="disabled",
            bg="#1e1e1e", fg="#00ff00", font=("Consolas", 9),
        )
        self.log_text.pack(expand=True, fill=tk.BOTH)
        pane.add(log_frame, minsize=220, stretch="always")

        # Kết quả
        result_frame = tk.Frame(pane)
        tk.Label(
            result_frame, text="Văn bản đã thu thập:", font=("Arial", 9, "bold"),
        ).pack(anchor=tk.W)
        self.result_text = scrolledtext.ScrolledText(
            result_frame, state="disabled",
            bg="#f8f8f8", fg="#222222", font=("Arial", 9),
        )
        self.result_text.pack(expand=True, fill=tk.BOTH)
        pane.add(result_frame, minsize=300, stretch="always")

    def _setup_logging(self):
        handler = _TextHandler(self.log_text)
        handler.setFormatter(
            logging.Formatter("%(asctime)s  %(message)s", "%H:%M:%S")
        )
        root_logger = logging.getLogger()
        root_logger.setLevel(logging.INFO)
        root_logger.handlers = []
        root_logger.addHandler(handler)

    # ------------------------------------------------------------------
    # HELPERS
    # ------------------------------------------------------------------

    def _clear_log(self):
        self.log_text.configure(state="normal")
        self.log_text.delete("1.0", tk.END)
        self.log_text.configure(state="disabled")

    def _update_progress(self, current: int, total: int):
        self._progress_lbl.config(text=f"Tiến độ: {current}/{total} từ khóa")
        self._progress_bar["maximum"] = max(total, 1)
        self._progress_bar["value"] = current

    def _update_stats_bar(self):
        """Cập nhật status bar từ SQLite stats, lên lịch chạy lại sau 3 giây."""
        try:
            s = db_queue.get_stats()
            self._stats_lbl.config(
                text=(
                    f"DB — "
                    f"Hàng chờ: {s['pending']}  |  "
                    f"Đang cào: {s['processing']}  |  "
                    f"Xong: {s['done']}  |  "
                    f"Lỗi: {s['error']}  |  "
                    f"Bỏ qua: {s['skipped']}  |  "
                    f"Tổng: {s['total']}"
                )
            )
        except Exception:
            pass
        self.after(3000, self._update_stats_bar)

    def _append_result(self, title: str, keyword: str, file_path: str):
        def _do():
            self.result_text.configure(state="normal")
            self.result_text.insert(
                tk.END, f"[{keyword}]\n  ✓ {title[:80]}\n  → {file_path}\n\n"
            )
            self.result_text.yview(tk.END)
            self.result_text.configure(state="disabled")
        self.after(0, _do)

    def _log(self, msg: str):
        logging.info(msg)

    def _check_events(self) -> bool:
        """Kiểm tra dừng/tạm dừng. Trả về True nếu cần thoát."""
        if self.stop_event.is_set():
            return True
        if not self.pause_event.is_set():
            logging.info("⏳ Đang tạm dừng... Nhấn Tiếp tục để chạy tiếp.")
            self.pause_event.wait()
            if self.stop_event.is_set():
                return True
            logging.info("🚀 Tiếp tục...")
        return False

    # ------------------------------------------------------------------
    # ĐIỀU KHIỂN (Start / Pause / Stop)
    # ------------------------------------------------------------------

    def _toggle_pause(self):
        if self.pause_event.is_set():
            self.pause_event.clear()
            self.pause_btn.config(text="▶ Tiếp tục", bg="#f39c12")
        else:
            self.pause_event.set()
            self.pause_btn.config(text="⏸ Tạm dừng", bg="SystemButtonFace")

    def _stop(self):
        if messagebox.askyesno("Xác nhận", "Bạn có chắc muốn dừng hẳn?"):
            self.stop_event.set()
            self.pause_event.set()
            self.pause_btn.config(state=tk.DISABLED)
            self.stop_btn.config(state=tk.DISABLED)
            logging.warning("🛑 Đã yêu cầu dừng hẳn.")

    def _reset_ui(self):
        self.is_running = False
        self.start_btn.config(state=tk.NORMAL)
        self.pause_btn.config(state=tk.DISABLED, text="⏸ Tạm dừng", bg="SystemButtonFace")
        self.stop_btn.config(state=tk.DISABLED)

    def _set_running(self):
        self.is_running = True
        self.stop_event.clear()
        self.pause_event.set()
        self.start_btn.config(state=tk.DISABLED)
        self.pause_btn.config(state=tk.NORMAL)
        self.stop_btn.config(state=tk.NORMAL)

    # ------------------------------------------------------------------
    # CÀO URL ĐƠN LẺ
    # ------------------------------------------------------------------

    def _start_single_url(self):
        url = self._url_var.get().strip()
        if not url:
            messagebox.showwarning("Cảnh báo", "Vui lòng nhập URL!")
            return
        self._url_var.set("")
        threading.Thread(
            target=self._run_single_url, args=(url,), daemon=True,
        ).start()

    def _run_single_url(self, url: str):
        # Enqueue trực tiếp, bypass kiểm tra hiệu lực (URL thủ công)
        db_queue.enqueue_url(url, keyword="Direct_URL", title=url, hieu_luc="Còn hiệu lực")
        scrape_url(url, keyword="Direct_URL", log_fn=self._log)

    # ------------------------------------------------------------------
    # CÀO THEO KEYWORD (từ key.json) — HAI THREAD SONG SONG
    # ------------------------------------------------------------------

    def _start_keywords(self):
        if self.is_running:
            return
        if not os.path.exists(KEY_PATH):
            messagebox.showerror("Lỗi", f"Không tìm thấy file từ khóa:\n{KEY_PATH}")
            return
        self._set_running()
        # Thread A: tìm kiếm + enqueue
        threading.Thread(target=self._thread_search, daemon=True).start()
        # Thread B: worker cào từng URL
        threading.Thread(target=self._thread_worker, daemon=True).start()

    # ---- Thread A: Tìm kiếm & enqueue --------------------------------

    def _thread_search(self):
        """
        Duyệt từng keyword: search_documents() → enqueue_many() vào SQLite ngay.
        Không giữ URL trong RAM. Kết thúc sau khi hết keyword.
        """
        try:
            with open(KEY_PATH, "r", encoding="utf-8") as f:
                key_data = json.load(f)

            keywords: list[str] = []
            direct_urls: list[str] = []

            if isinstance(key_data, dict):
                search_data = key_data.get("search_keywords", {})
                if isinstance(search_data, dict):
                    for kws in search_data.values():
                        if isinstance(kws, list):
                            keywords.extend(kws)
                        elif isinstance(kws, str):
                            keywords.append(kws)
                elif isinstance(search_data, list):
                    keywords.extend(search_data)

                for url_key in ("urls", "links", "source_urls"):
                    vals = key_data.get(url_key, [])
                    if isinstance(vals, str):
                        vals = [vals]
                    for v in vals:
                        v = str(v).strip()
                        if v.startswith(("http://", "https://")):
                            direct_urls.append(v)

            elif isinstance(key_data, list):
                keywords.extend(key_data)

            keywords = list(dict.fromkeys(str(k).strip() for k in keywords if str(k).strip()))
            direct_urls = list(dict.fromkeys(direct_urls))

            # Enqueue direct URLs ngay (không qua search, coi là còn hiệu lực)
            if direct_urls:
                items = [
                    {"url": u, "keyword": "Direct_URL", "title": u, "hieu_luc": "Còn hiệu lực"}
                    for u in direct_urls
                ]
                added = db_queue.enqueue_many(items)
                logging.info(f"📎 Enqueue {added} URL trực tiếp (bỏ qua {len(direct_urls)-added} trùng).")

            if not keywords and not direct_urls:
                logging.warning("⚠️ key.json không có từ khóa hoặc URL.")
                return

            if not keywords:
                logging.info("ℹ️ Không có keyword, chỉ có direct URL.")
                return

            logging.info(f"🔍 Bắt đầu tìm kiếm {len(keywords)} từ khóa...")

            with sync_playwright() as p:
                browser = p.chromium.launch(headless=False)
                page = browser.new_page(user_agent=USER_AGENTS[0])
                try:
                    for idx, kw in enumerate(keywords, 1):
                        if self._check_events():
                            break

                        logging.info(f"🔍 [{idx}/{len(keywords)}] Keyword: {kw}")
                        self.after(0, self._update_progress, idx - 1, len(keywords))

                        docs = []
                        for attempt in range(1, MAX_RETRIES + 1):
                            try:
                                docs = search_documents(page, kw, log_fn=self._log)
                                break
                            except Exception as e:
                                logging.warning(f"⚠️ Search lần {attempt}: {e}")
                                if attempt < MAX_RETRIES:
                                    time.sleep(RETRY_DELAY_SECONDS)

                        # Enqueue ngay vào SQLite — kèm hieu_luc để tự lọc
                        items = [
                            {
                                "url": doc.get("url", ""),
                                "keyword": kw,
                                "title": doc.get("title", ""),
                                "hieu_luc": doc.get("hieu_luc", ""),
                            }
                            for doc in docs
                            if doc.get("url", "")
                        ]
                        if items:
                            added = db_queue.enqueue_many(items)
                            skipped_hl = sum(
                                1 for it in items
                                if it["hieu_luc"] not in ("Còn hiệu lực", "")
                            )
                            logging.info(
                                f"   ✅ Enqueue {added} mới | "
                                f"Hết/bỏ HiệuLực: {skipped_hl} | "
                                f"Trùng: {len(items) - added - skipped_hl}"
                            )

                        if idx < len(keywords):
                            wait = random.uniform(*WAIT_BETWEEN_KEYWORDS)
                            logging.info(f"   ⏳ Chờ {wait:.1f}s...")
                            time.sleep(wait)

                    self.after(0, self._update_progress, len(keywords), len(keywords))
                    logging.info("✅ Hoàn tất tìm kiếm tất cả keyword.")

                finally:
                    try:
                        page.close()
                    except Exception:
                        pass
                    try:
                        browser.close()
                    except Exception:
                        pass

        except Exception as e:
            logging.error(f"❌ Lỗi Thread Search: {e}")

    # ---- Thread B: Worker cào URL từ SQLite ---------------------------

    def _thread_worker(self):
        """
        Vòng lặp liên tục:
          1. fetch_next_pending() từ SQLite.
          2. scrape_url().
          3. mark_done() hoặc mark_error().
        Thoát khi stop_event hoặc không còn URL pending và search đã xong.
        """
        idle_ticks = 0  # Đếm số lần liên tiếp không có URL mới
        MAX_IDLE = 20   # ~60 giây idle → thoát

        logging.info("⚙️ Worker bắt đầu chờ URL từ hàng chờ SQLite...")

        while not self.stop_event.is_set():
            if self._check_events():
                break

            task = db_queue.fetch_next_pending()
            if task is None:
                idle_ticks += 1
                if idle_ticks >= MAX_IDLE:
                    logging.info("🏁 Worker: Không còn URL pending. Kết thúc.")
                    break
                time.sleep(3)
                continue

            idle_ticks = 0  # reset idle counter
            doc_url = task["url"]
            kw = task.get("keyword", "")
            title = task.get("title", "") or doc_url

            logging.info(f"📄 Worker cào: {title[:70]}")

            file_path = None
            last_err = ""
            for attempt in range(1, MAX_RETRIES + 1):
                try:
                    file_path = scrape_url(doc_url, keyword=kw, log_fn=self._log)
                    if file_path:
                        break
                    last_err = "scrape_url trả về None"
                except Exception as e:
                    last_err = str(e)
                    logging.warning(f"⚠️ Lần {attempt}: {e}")
                    if attempt < MAX_RETRIES:
                        time.sleep(RETRY_DELAY_SECONDS)

            if file_path:
                db_queue.mark_done(doc_url, file_path=file_path)
                self._append_result(title, kw, file_path)
            else:
                db_queue.mark_error(doc_url, error_msg=last_err)
                logging.warning(f"❌ Lỗi cào (đánh dấu error): {doc_url[:60]}")

            # Delay giữa các lần cào
            if not self.stop_event.is_set():
                wait = random.uniform(*WAIT_BETWEEN_URLS)
                time.sleep(wait)

        logging.info("🎉 Worker kết thúc.")
        self.after(0, self._reset_ui)
