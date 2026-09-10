# VBPL Web Scraper - Cấu trúc Dự án (Project Structure)

Dự án cào dữ liệu Văn bản Pháp luật (VBPL) được thiết kế theo kiến trúc **modular (hướng mô-đun)**. Cấu trúc này giúp bạn dễ dàng bảo trì, nâng cấp hoặc thay đổi logic mà không phải sửa lại toàn bộ ứng dụng.

---

## 📁 Cây Thư Mục Dự Án (Directory Tree)

```text
vbpl_scraper/
│
├── main.py                  # [File Chạy Chính] Khởi chạy ứng dụng GUI
├── config.py                # [Cấu Hình Global] URL, selector, đường dẫn lưu, DB_PATH, EXPIRED_POLICY...
│
├── scraper/                 # [Mô-đun Cào Dữ Liệu]
│   ├── __init__.py
│   ├── api_client.py        # Gọi API VBPL qua Playwright (bắt response JSON, xử lý streaming)
│   │                        # → Trả về field `hieu_luc` từ effStatus; normalize qua _EFF_STATUS_MAP
│   ├── parser.py            # Phân tích cú pháp HTML/Text (Điều, Khoản, Điểm, Modal VB sửa đổi)
│   └── engine.py            # Động cơ cào chính (kết nối Playwright, luồng 2-pass, quản lý session)
│
├── utils/                   # [Tiện Ích Bo Mạch]
│   ├── __init__.py
│   ├── text_utils.py        # Xử lý văn bản (Regex trích xuất ngày, hiệu lực, slugify, lọc rác)
│   ├── storage.py           # Lưu file output (JSON/TXT). Progress đã chuyển sang db_queue.py
│   └── db_queue.py          # [MỚI] Quản lý hàng chờ URL + tiến độ bằng SQLite (vbpl_queue.db)
│
└── gui/                     # [Giao Diện Người Dùng]
    ├── __init__.py
    └── app_gui.py           # Giao diện Tkinter: 2 thread song song (Search+Enqueue | Worker Cào)
                             # + Status bar hiển thị thống kê SQLite realtime
```

---

## 🗄️ Kiến Trúc SQLite Queue (Mới)

```
[Thread Search]                          [Thread Worker]
search_documents(keyword)                fetch_next_pending()
       │                                        │
       ▼                                        ▼
enqueue_many() ──► [SQLite: url_queue] ──► scrape_url()
  (INSERT OR IGNORE)                           │
  (hieu_luc filter)                    mark_done() / mark_error()
```

**Bảng `url_queue` trong `vbpl_queue.db`**:

| Cột | Kiểu | Mô tả |
| :--- | :--- | :--- |
| `id` | INTEGER PK | Auto-increment |
| `url` | TEXT UNIQUE | URL văn bản (UNIQUE → tự chống trùng) |
| `keyword` | TEXT | Từ khóa tìm thấy URL |
| `title` | TEXT | Tiêu đề từ search API |
| `status` | TEXT | `pending` / `processing` / `done` / `error` / `skipped` |
| `hieu_luc` | TEXT | Trạng thái hiệu lực từ search API |
| `file_path` | TEXT | Đường dẫn file JSON đầu ra |
| `error_msg` | TEXT | Thông báo lỗi (nếu có) |
| `created_at` | TEXT | Timestamp tạo |
| `updated_at` | TEXT | Timestamp cập nhật cuối |

**Chính sách văn bản hết hiệu lực** (`EXPIRED_POLICY = "skip"` trong `config.py`):
- Khi `hieu_luc` ≠ `"Còn hiệu lực"` → `status = "skipped"` ngay khi enqueue, worker bỏ qua.

---

## 🛠️ Chi Tiết Nhiệm Vụ Các Mô-đun (Module Responsibilities)

| Mục đích muốn sửa / nâng cấp | File cần chỉnh sửa | Ghi chú |
| :--- | :--- | :--- |
| Thay đổi URL gốc, số lần thử lại, thư mục lưu file, User-Agent | [config.py](config.py) | Tất cả tham số hệ thống nằm ở đây |
| Thay đổi đường dẫn SQLite DB, chính sách hết hiệu lực | [config.py](config.py) | `DB_PATH`, `EXPIRED_POLICY` |
| Thêm/Sửa biểu thức chính quy (Regex) lấy ngày ban hành, điều/khoản | [utils/text_utils.py](utils/text_utils.py) | Xử lý chuỗi văn bản thuần túy |
| Thay đổi định dạng file đầu ra (JSON/TXT) | [utils/storage.py](utils/storage.py) | Chỉ còn save_document() |
| Quản lý hàng chờ URL, check trùng, resume, thống kê | [utils/db_queue.py](utils/db_queue.py) | SQLite queue (thay progress.json) |
| Thay đổi cách gọi API tìm kiếm, xử lý streaming response | [scraper/api_client.py](scraper/api_client.py) | Tương tác mạng và bóc tách API |
| Bóc tách nội dung HTML Điều/Khoản, sửa lỗi modal lịch sử hiệu lực | [scraper/parser.py](scraper/parser.py) | Logic bóc tách cây nội dung văn bản |
| Thay đổi luồng duyệt web của Playwright, chế độ 2-pass | [scraper/engine.py](scraper/engine.py) | Động cơ điều khiển trình duyệt |
| Chỉnh sửa giao diện, màu sắc, nút bấm, bảng hiển thị tiến độ | [gui/app_gui.py](gui/app_gui.py) | Giao diện người dùng Tkinter |

---

## 🚀 Hướng Dẫn Chạy Ứng Dụng (How to Run)

### 1. Cài đặt thư viện phụ thuộc (Dependencies)
```bash
pip install playwright beautifulsoup4
playwright install chromium
```

### 2. Khởi chạy tool
```bash
python main.py
```

### 3. Xem dữ liệu SQLite (tuỳ chọn)
Dùng [DB Browser for SQLite](https://sqlitebrowser.org/) để mở `vbpl_queue.db` và kiểm tra hàng chờ URL, trạng thái cào.

---

## 🐛 Các Lỗi Đã Được Khắc Phục (Fixed Issues in New Architecture)

1. **Lỗi Modal luôn đọc bản ghi số 1** (`app2.py` / `app4.py`):
   - **Nguyên nhân**: Dùng `page.content()` làm BeautifulSoup đọc lại toàn bộ DOM chứa nhiều modal ẩn.
   - **Khắc phục**: Dùng `.last` locator trên Ant Design modal element trong `parser.py`.

2. **Lỗi Parse API Streaming response (`10:`, `11:`)** (`app.py` / `app2.py`):
   - **Nguyên nhân**: Logic cắt chuỗi cứng `line[1] == ':'` bị hỏng khi số thứ tự dòng là 2 chữ số.
   - **Khắc phục**: Thay bằng Regex `re.sub(r"^\d+:\s*", "", line)` trong `api_client.py`.

3. **Lỗi Trồng Lắng Lắng Nghe Event (Listener Stacking)** (`app.py`):
   - **Nguyên nhân**: Mỗi lượt tìm kiếm thêm 1 listener `page.on("response")` mà không tháo bỏ.
   - **Khắc phục**: Thêm `page.remove_listener("response", ...)` sau mỗi lần cào trong `api_client.py`.

4. **Lỗi Điều dạng 5a, 12b bị bỏ sót**:
   - **Nguyên nhân**: Pattern Regex cũ `r"^Điều\s+(\d+)"` không bắt chữ cái đi kèm.
   - **Khắc phục**: Cập nhật Regex `r"^Điều\s+(\d+[a-zA-Z]?)"` trong `text_utils.py`.

5. **Lỗi mất nội dung Modal ở cấp Điểm**:
   - **Nguyên nhân**: Slugify key dạng `Dieu_1_Khoan_2_Diem_a` không khớp với key của Khoản cha `Dieu_1_Khoan_2`.
   - **Khắc phục**: Hàm `apply_modal_updates()` tự động tách suffix `_Diem_x` để cập nhật đúng vào Khoản chứa nó.

6. **[MỚI] Toàn bộ URL nằm trong RAM sau khi search**:
   - **Nguyên nhân**: `search_results` list tích lũy trong bộ nhớ, crash → mất hết.
   - **Khắc phục**: Mỗi keyword search xong → `enqueue_many()` vào SQLite ngay, RAM sạch.

7. **[MỚI] Không kiểm duyệt hiệu lực văn bản**:
   - **Nguyên nhân**: Bộ lọc "Còn hiệu lực" trên UI không đảm bảo 100%.
   - **Khắc phục**: `api_client.py` đọc field `effStatus` từ API JSON, `enqueue_many()` tự gán `status='skipped'` cho văn bản hết hiệu lực.

8. **[MỚI] Không resume được sau crash**:
   - **Nguyên nhân**: `progress.json` chỉ lưu URL đã xong, URL đang cào (`processing`) bị mất.
   - **Khắc phục**: `db_queue.reset_processing()` được gọi khi khởi động, reset `processing → pending`.
