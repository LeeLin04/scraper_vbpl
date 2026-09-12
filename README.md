# VBPL Web Scraper - Cấu trúc Dự án (Project Structure)

Dự án cào dữ liệu Văn bản Pháp luật (VBPL) được thiết kế theo kiến trúc **modular (hướng mô-đun)**. Cấu trúc này giúp bạn dễ dàng bảo trì, nâng cấp hoặc thay đổi logic mà không phải sửa lại toàn bộ ứng dụng.

---

## 📁 Cây Thư Mục Dự Án (Directory Tree)

```text
vbpl_scraper/
│
├── main.py                  # [File Chạy Chính] Khởi chạy ứng dụng GUI
├── config.py                # [Cấu Hình Global] Chứa URL, selector, đường dẫn lưu, User-Agent...
│
├── scraper/                 # [Mô-đun Cào Dữ Liệu]
│   ├── __init__.py
│   ├── api_client.py        # Gọi API VBPL qua Playwright (bắt response JSON, xử lý streaming)
│   ├── parser.py            # Phân tích cú pháp HTML/Text (Điều, Khoản, Điểm, Modal VB sửa đổi)
│   └── engine.py            # Động cơ cào chính (kết nối Playwright, luồng 2-pass, quản lý session)
│
├── utils/                   # [Tiện Ích Bo Mạch]
│   ├── __init__.py
│   ├── text_utils.py        # Xử lý văn bản (Regex trích xuất ngày, hiệu lực, slugify, lọc rác)
│   └── storage.py           # Quản lý lưu trữ (Save JSON/TXT, ghi nhận/khôi phục tiến độ resume)
│
└── gui/                     # [Giao Diện Người Dùng]
    ├── __init__.py
    └── app_gui.py           # Giao diện Tkinter (PanedWindow, Start/Pause/Stop, thanh tiến trình)
```

---

## 🛠️ Chi Tiết Nhiệm Vụ Các Mô-đun (Module Responsibilities)

Khi bạn muốn cập nhật hoặc sửa đổi tool, **hãy tra bảng dưới đây để biết cần sửa file nào**:

| Mục đích muốn sửa / nâng cấp | File cần chỉnh sửa | Ghi chú |
| :--- | :--- | :--- |
| Thay đổi URL gốc, số lần thử lại, thư mục lưu file, User-Agent | [config.py](file:///d:/Data/tttttttt/vbpl_scraper/config.py) | Tất cả tham số hệ thống nằm ở đây |
| Thêm/Sửa biểu thức chính quy (Regex) lấy ngày ban hành, điều/khoản | [utils/text_utils.py](file:///d:/Data/tttttttt/vbpl_scraper/utils/text_utils.py) | Xử lý chuỗi văn bản thuần túy |
| Thay đổi định dạng file đầu ra (JSON/TXT), cấu trúc tiến độ resume | [utils/storage.py](file:///d:/Data/tttttttt/vbpl_scraper/utils/storage.py) | Quản lý đọc/ghi đĩa cứng |
| Thay đổi cách gọi API tìm kiếm, xử lý streaming response của trang web | [scraper/api_client.py](file:///d:/Data/tttttttt/vbpl_scraper/scraper/api_client.py) | Tương tác mạng và bóc tách API |
| Bóc tách nội dung HTML Điều/Khoản, sửa lỗi modal lịch sử hiệu lực | [scraper/parser.py](file:///d:/Data/tttttttt/vbpl_scraper/scraper/parser.py) | Logic bóc tách cây nội dung văn bản |
| Thay đổi luồng duyệt web của Playwright, chế độ 2-pass | [scraper/engine.py](file:///d:/Data/tttttttt/vbpl_scraper/scraper/engine.py) | Động cơ điều khiển trình duyệt |
| Chỉnh sửa giao diện, màu sắc, nút bấm, bảng hiển thị tiến độ | [gui/app_gui.py](file:///d:/Data/tttttttt/vbpl_scraper/gui/app_gui.py) | Giao diện người dùng Tkinter |

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
