"""
scraper/engine.py – Động cơ Playwright điều khiển quá trình cào dữ liệu VBPL.

Chứa toàn bộ logic:
  - Bước 1 (Pass 1): Mở trang nhẹ nhàng để tạo session / vượt chống bot.
  - Bước 2 (Pass 2): Mở đầy đủ giao diện, click switch & Modal Ant Design,
                     đọc tách biệt nội dung Mới và nội dung Gốc cho từng khoản.
"""

import re
import time

from bs4 import BeautifulSoup

from config import USER_AGENTS
from utils.text_utils import clean_text, extract_document_number, slugify_key
from scraper.parser import build_document
from utils.storage import save_document


# =========================================================================
# FETCH PAGE – Điều khiển trình duyệt, click expand & Modal
# =========================================================================

def _open_session_pass(page, url: str) -> bool:
    """
    Pass 1: Chỉ mở URL để tạo session / cookie / vượt kiểm tra chống bot.
    Không trích xuất bất kỳ dữ liệu nào.
    """
    page.goto(url, wait_until="domcontentloaded", timeout=60000)
    page.wait_for_timeout(3000)
    return True


def _fetch_content_pass(page, url: str, log_fn=None) -> tuple | None:
    """
    Pass 2: Tải đầy đủ nội dung trang, click các nút expand / ant-switch,
    tuần tự mở từng Modal sửa đổi và đọc cả nội dung mới lẫn nội dung gốc
    cho mọi khoản (kể cả 17, 18, 18a, 18b...).
    """

    def log(msg):
        if log_fn:
            log_fn(msg)

    page.goto(url, wait_until="domcontentloaded", timeout=60000)
    page.wait_for_timeout(2000)

    # --- Click các nút expand thông thường ---
    try:
        expand_selectors = [
            ".btn-expand", ".btn-more", ".show-more", ".toggle-content",
            "[data-toggle='collapse']", ".prov-expand", ".icon-expand",
            "a.view-more", "button.btn-show",
        ]
        for sel in expand_selectors:
            for btn in page.query_selector_all(sel):
                try:
                    if btn.is_visible():
                        btn.click(force=True)
                        page.wait_for_timeout(300)
                except Exception:
                    pass
    except Exception:
        pass

    # --- Bật switch "Hiển thị chi tiết cập nhật" ---
    try:
        for sw in page.query_selector_all(".ant-switch, [role='switch']"):
            try:
                if not sw.is_visible():
                    continue
                if sw.get_attribute("aria-checked") != "true":
                    sw.scroll_into_view_if_needed()
                    sw.hover()
                    sw.click(force=True)
                    page.wait_for_timeout(300)
            except Exception:
                pass
    except Exception:
        pass

    # --- Tuần tự mở từng nút sửa đổi bằng vòng lặp động ---
    modified_texts = []
    processed_count = 0
    max_retries = 50  # Giới hạn an toàn tránh lặp vô tận

    while processed_count < max_retries:
        try:
            all_buttons = page.query_selector_all("button")
            target_btn = None
            button_index = 0

            for btn in all_buttons:
                try:
                    if not btn.is_visible():
                        continue
                    btn_text = btn.inner_text().strip().lower()
                    if (
                        "điều khoản được sửa đổi" not in btn_text
                        and "sửa đổi, bổ sung" not in btn_text
                    ):
                        continue
                    
                    button_index += 1
                    if button_index <= processed_count:
                        continue
                        
                    target_btn = btn
                    break
                except Exception:
                    continue

            if not target_btn:
                break  # Đã duyệt hết tất cả các nút hợp lệ trên trang

            processed_count += 1
            current_btn_idx = processed_count

            # Lấy chính xác ngữ cảnh Điều/Khoản từ thẻ chứa nút hoặc các thẻ lân cận
            context_info = target_btn.evaluate("""
                (element) => {
                    let item_text = null, clause_text = null, article_text = null;
                    
                    // 1. Quét ngay bên trong thẻ <p> chứa nút bấm (trường hợp nút nằm chung với text khoản)
                    let parentP = element.closest('p');
                    if (parentP) {
                        let text = parentP.innerText || '';
                        let lines = text.split('\\n');
                        for (let line of lines) {
                            line = line.trim();
                            if (/^\\d+[a-zA-Z]?\\.\\s*/.test(line) && !line.includes('Điều khoản được sửa đổi')) {
                                clause_text = line;
                                break;
                            }
                        }
                    }

                    // 2. Nếu chưa tìm thấy clause_text, quét các thẻ anh em đứng trước
                    let curr = element;
                    while (curr && curr !== document.body) {
                        let sib = curr.previousElementSibling;
                        while (sib) {
                            if (!item_text && !clause_text && !article_text
                                    && sib.matches && sib.matches('p.prov-item'))
                                item_text = sib.innerText.trim();
                            if (!clause_text && !article_text
                                    && sib.matches && sib.matches('p.prov-clause'))
                                clause_text = sib.innerText.trim();
                            if (!article_text && sib.matches && sib.matches('p.prov-article')) {
                                article_text = sib.innerText.trim();
                                break;
                            }
                            sib = sib.previousElementSibling;
                        }
                        if (article_text) break;
                        curr = curr.parentElement;
                    }

                    // 3. Tìm Điều (article_text) nếu chưa có
                    curr = element;
                    while (curr && curr !== document.body && !article_text) {
                        let sib = curr.previousElementSibling;
                        while (sib) {
                            if (sib.matches && sib.matches('p.prov-article')) {
                                article_text = sib.innerText.trim();
                                break;
                            }
                            sib = sib.previousElementSibling;
                        }
                        if (article_text) break;
                        curr = curr.parentElement;
                    }

                    return { item: item_text, clause: clause_text, article: article_text };
                }
            """)

            doc_title = page.title()
            nghi_dinh = extract_document_number(doc_title) or doc_title
            document_key = slugify_key(nghi_dinh)
            target_key = document_key

            article_text = context_info.get("article", "")
            clause_text = context_info.get("clause", "")
            item_text = context_info.get("item", "")

            if article_text:
                m = re.match(r"Điều\s+(\d+[a-zA-Z]?)", article_text, flags=re.IGNORECASE)
                if m:
                    target_key += f"_Dieu_{slugify_key(m.group(1))}"
            
            if clause_text:
                # Bắt chuẩn xác cả số khoản lẫn hậu tố chữ cái (VD: 17, 18, 18a, 18b)
                m = re.match(r"^(\d+[a-zA-Z]?)\.\s*", clause_text)
                if m:
                    target_key += f"_Khoan_{slugify_key(m.group(1))}"
            
            if item_text:
                m = re.match(r"^([a-zđĐ])\)\s+", item_text)
                if m:
                    target_key += f"_Diem_{slugify_key(m.group(1))}"

            target_btn.scroll_into_view_if_needed()
            target_btn.hover()
            target_btn.click(force=True)

            # Chờ modal hiển thị rõ ràng
            try:
                page.wait_for_selector(".ant-modal", state="visible", timeout=10000)
            except Exception:
                pass
            page.wait_for_timeout(300)

            # Cô lập phạm vi modal hiện tại
            current_modal = page.locator(".ant-modal-body:visible").last

            # --- Chọn dropdown ngày sửa đổi trong modal hiện tại ---
            try:
                select_elem = current_modal.locator(".ant-select").last
                if select_elem.is_visible(timeout=5000):
                    select_elem.scroll_into_view_if_needed()
                    select_elem.hover()
                    select_elem.click()
                    page.wait_for_timeout(300)
                    
                    option_elem = page.locator(
                        ".ant-select-dropdown:not(.ant-select-dropdown-hidden) "
                        ".ant-select-item-option:not(.ant-select-item-option-disabled)"
                    ).first
                    if option_elem.is_visible(timeout=3000):
                        option_elem.click()
                        page.wait_for_timeout(400)
            except Exception as e_sel:
                log(f"   ℹ️ Không có dropdown ngày ở nút #{current_btn_idx}: {e_sel}")

            new_content = ""
            old_content = ""

            # --- 1. LẤY NỘI DUNG MỚI (Sau chỉnh sửa) ---
            try:
                tab_moi = current_modal.locator(".ant-tabs-tab").filter(has_text=re.compile(r"mới|sau chỉnh sửa", re.IGNORECASE)).first
                if tab_moi.count() == 0:
                    tab_moi = current_modal.locator(".ant-tabs-tab[data-node-key='1']").last

                if tab_moi.is_visible(timeout=3000):
                    tab_moi.scroll_into_view_if_needed()
                    tab_moi.click(force=True)
                    page.wait_for_timeout(600)

                pane_moi = current_modal.locator(".ant-tabs-tabpane-active").last
                if pane_moi.is_visible(timeout=2000):
                    new_content = clean_text(pane_moi.inner_text())
                else:
                    new_content = clean_text(current_modal.inner_text())
            except Exception as e_new:
                log(f"   ⚠️ Lỗi đọc Nội dung mới ở nút #{current_btn_idx}: {e_new}")

            # --- 2. LẤY NỘI DUNG GỐC/CŨ (Trước chỉnh sửa) ---
            try:
                tab_cu = current_modal.locator(".ant-tabs-tab").filter(has_text=re.compile(r"cũ|trước|gốc", re.IGNORECASE)).first
                if tab_cu.count() == 0:
                    tab_cu = current_modal.locator(".ant-tabs-tab[data-node-key='2']").last

                if tab_cu.is_visible(timeout=3000):
                    tab_cu.scroll_into_view_if_needed()
                    tab_cu.click(force=True)
                    page.wait_for_timeout(600)

                pane_cu = current_modal.locator(".ant-tabs-tabpane-active").last
                if pane_cu.is_visible(timeout=2000):
                    old_content = clean_text(pane_cu.inner_text())
                else:
                    old_content = clean_text(current_modal.inner_text())
            except Exception as e_old:
                log(f"   ⚠️ Lỗi đọc Nội dung gốc ở nút #{current_btn_idx}: {e_old}")

            # --- LƯU THÀNH 2 KHOẢN RIÊNG BIỆT (MỚI & GỐC) ---
            if new_content:
                modified_texts.append({
                    "target_key": target_key,
                    "btn_idx": current_btn_idx,
                    "content": new_content,
                })
                log(f"   📌 Đã lưu [MỚI] cho khóa: {target_key}")

            if old_content:
                modified_texts.append({
                    "target_key": f"{target_key}_cu",
                    "btn_idx": current_btn_idx,
                    "content": old_content,
                })
                log(f"   📌 Đã lưu [CŨ] cho khóa: {target_key}_cu")

            # Đóng Modal hiện tại
            try:
                close_btn = page.query_selector(
                    ".ant-modal-close, .ant-modal-footer button"
                )
                if close_btn and close_btn.is_visible():
                    close_btn.click(force=True)
                else:
                    page.keyboard.press("Escape")
            except Exception:
                page.keyboard.press("Escape")

            page.wait_for_timeout(500)

        except Exception as e_loop:
            log(f"⚠️ Lỗi ở vòng lặp nút #{processed_count}: {e_loop}")
            try:
                page.keyboard.press("Escape")
            except Exception:
                pass
            processed_count += 1

    page.wait_for_timeout(1000)

    soup = BeautifulSoup(page.content(), "lxml")
    page_text = soup.get_text("\n", strip=True)

    if len(page_text) < 100:
        return None

    return page_text, soup, modified_texts


# =========================================================================
# SCRAPE URL – Cào một văn bản từ URL cụ thể
# =========================================================================

def scrape_url(url: str, keyword: str = "Direct_URL", log_fn=None) -> str | None:
    """
    Cào một văn bản VBPL từ URL, lưu file JSON + TXT và trả về đường dẫn file.

    Quy trình 2 bước:
      - Pass 1: Mở trang nhẹ để tạo session / vượt chống bot.
      - Pass 2: Mở đầy đủ, click Modal, đọc & xử lý dữ liệu.
    """
    from playwright.sync_api import sync_playwright

    def log(msg):
        if log_fn:
            log_fn(msg)

    try:
        log(f"🎯 Bắt đầu cào: {url}")
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=False)
            page = browser.new_page(user_agent=USER_AGENTS[0])

            # Pass 1
            log("🛡️ Pass 1: Tạo session / vượt chống bot...")
            try:
                _open_session_pass(page, url)
            except Exception as e:
                log(f"❌ Pass 1 thất bại: {e}")
                browser.close()
                return None

            log("✅ Pass 1 xong. Chờ 2 giây...")
            time.sleep(2)

            # Pass 2
            log("💾 Pass 2: Cào chính thức...")
            result = _fetch_content_pass(page, url, log_fn=log_fn)
            if not result:
                log("❌ Pass 2 thất bại (trang trống).")
                browser.close()
                return None

            page_text, soup, modified_texts = result

            # Metadata
            h1 = soup.find("h1")
            title = clean_text(h1.get_text(" ", strip=True)) if h1 else "Chưa rõ Tiêu đề"

            from utils.text_utils import detect_status, extract_issued_date, extract_effective_date
            doc_info = {
                "title": title,
                "keyword": keyword,
                "status": detect_status(page_text),
                "issued_date": extract_issued_date(page_text),
                "effective_date": extract_effective_date(page_text),
                "source_url": url,
            }

            # Build + Save
            document = build_document(soup, page_text, doc_info, modified_texts)
            file_path = save_document(document)

            content_tree = document.get("content_tree", [])
            khoan_count = sum(len(d.get("children", [])) for d in content_tree)

            log(f"🎉 HOÀN THÀNH: [{title[:60]}...]")
            log(f"   ├── File     : {file_path}")
            log(f"   ├── Số Điều  : {len(content_tree)}")
            log(f"   ├── Số Khoản : {khoan_count}")
            log(f"   └── Sửa đổi  : {len(modified_texts)} mục (mới & gốc)")

            browser.close()
            return file_path

    except Exception as e:
        log(f"❌ Lỗi khi cào {url}: {e}")
        return None