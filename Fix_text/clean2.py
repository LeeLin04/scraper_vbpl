
"""
clean_json_chars.py

Làm sạch ký tự Unicode và newline trong phần content của dữ liệu VBPL.

CHỨC NĂNG
---------
1. Đọc file JSON dạng danh sách văn bản.
2. Chỉ xử lý dữ liệu bên trong content_tree.
3. Không thay đổi cấu trúc JSON.
4. Không thay đổi các key:
       level
       number
       title
       content
       key
       citation
       label
       children
5. Xóa Unicode ẩn.
6. Xóa zero-width characters.
7. Xóa bidi control characters.
8. Chuẩn hóa Unicode NFC.
9. Chuẩn hóa Unicode space.
10. Tất cả newline trong content được thay bằng dấu cách.
11. Xử lý cả newline thật và chuỗi literal "\\n".
12. Gom nhiều dấu cách thành một dấu cách.
13. Bỏ văn bản không có content thực tế.
14. Lưu source_url của văn bản trống vào PL_link_hd.json.
15. Có chế độ --dry-run.
16. Có chế độ --in-place và tạo backup.

Ví dụ:

Input:

"liệt sĩ;
b) Người khuyết tật;
c) Đối tượng quy định"

Output:

"liệt sĩ; b) Người khuyết tật; c) Đối tượng quy định"
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
import unicodedata

from collections import Counter
from pathlib import Path
from typing import Any


# ============================================================
# ĐƯỜNG DẪN INPUT MẶC ĐỊNH
# ============================================================

DEFAULT_INPUT = Path(
    r"D:\A_WORK\TGA\chatbot3\text_json\PL_tong_2\PL_tong.json"
)


# ============================================================
# CONTROL CHARACTER ĐƯỢC PHÉP
# ============================================================

# Sau khi xử lý newline, \n sẽ bị thay bằng space.
# Tuy nhiên vẫn giữ trong bước Unicode ban đầu để tránh
# làm hỏng quá trình đọc text.

ALLOWED_CONTROLS = {
    "\t",
    "\n",
    "\r",
}


# ============================================================
# UNICODE SPACE
# ============================================================

SPACE_CHARS = {
    "\u00a0",  # NO-BREAK SPACE
    "\u1680",  # OGHAM SPACE MARK

    "\u2000",  # EN QUAD
    "\u2001",  # EM QUAD
    "\u2002",  # EN SPACE
    "\u2003",  # EM SPACE
    "\u2004",  # THREE-PER-EM SPACE
    "\u2005",  # FOUR-PER-EM SPACE
    "\u2006",  # SIX-PER-EM SPACE
    "\u2007",  # FIGURE SPACE
    "\u2008",  # PUNCTUATION SPACE
    "\u2009",  # THIN SPACE
    "\u200A",  # HAIR SPACE

    "\u202F",  # NARROW NO-BREAK SPACE
    "\u205F",  # MEDIUM MATHEMATICAL SPACE
    "\u3000",  # IDEOGRAPHIC SPACE
}


# ============================================================
# KÝ TỰ UNICODE ẨN CẦN XÓA
# ============================================================

REMOVE_CHARS = {
    "\ufeff",  # BOM

    # Zero-width
    "\u200b",  # ZERO WIDTH SPACE
    "\u200c",  # ZERO WIDTH NON-JOINER
    "\u200d",  # ZERO WIDTH JOINER
    "\u2060",  # WORD JOINER

    # Bidi isolate
    "\u2066",
    "\u2067",
    "\u2068",
    "\u2069",

    # Bidi embedding / override
    "\u202a",
    "\u202b",
    "\u202c",
    "\u202d",
    "\u202e",
}


# ============================================================
# CLEAN TEXT
# ============================================================

def clean_text(
    value: str,
    stats: Counter[str],
) -> str:
    """
    Làm sạch text trong content_tree.

    QUAN TRỌNG:
    -----------
    Tất cả newline sẽ được thay bằng một dấu cách.

    Ví dụ:

        "liệt sĩ;
        b) Người khuyết tật;
        c) Đối tượng"

    thành:

        "liệt sĩ; b) Người khuyết tật; c) Đối tượng"
    """

    result: list[str] = []

    # ========================================================
    # 1. DUYỆT TỪNG KÝ TỰ
    # ========================================================

    for char in value:

        category = unicodedata.category(char)

        # ----------------------------------------------------
        # XÓA KÝ TỰ ẨN
        # ----------------------------------------------------

        if char in REMOVE_CHARS:

            name = unicodedata.name(
                char,
                "UNKNOWN"
            )

            stats[
                f"removed {name}"
            ] += 1

            continue

        # ----------------------------------------------------
        # UNICODE SPACE -> SPACE THƯỜNG
        # ----------------------------------------------------

        if char in SPACE_CHARS:

            name = unicodedata.name(
                char,
                "UNKNOWN"
            )

            stats[
                f"space -> normal ({name})"
            ] += 1

            result.append(" ")

            continue

        # ----------------------------------------------------
        # CONTROL CHARACTER BẤT THƯỜNG
        # ----------------------------------------------------

        if (
            category.startswith("C")
            and char not in ALLOWED_CONTROLS
        ):

            name = unicodedata.name(
                char,
                "UNKNOWN"
            )

            stats[
                f"removed {name}"
            ] += 1

            continue

        result.append(char)

    text = "".join(result)

    # ========================================================
    # 2. CHUẨN HÓA UNICODE NFC
    # ========================================================

    normalized = unicodedata.normalize(
        "NFC",
        text
    )

    if normalized != text:

        stats[
            "normalized NFC"
        ] += 1

    text = normalized

    # ========================================================
    # 3. CHUẨN HÓA CRLF / CR
    # ========================================================

    old_text = text

    text = text.replace(
        "\r\n",
        "\n"
    )

    text = text.replace(
        "\r",
        "\n"
    )

    if text != old_text:

        stats[
            "normalized CRLF/CR"
        ] += 1

    # ========================================================
    # 4. XÓA NEWLINE THẬT
    # ========================================================
    #
    # \n
    # \n\n
    # \n\n\n
    #
    # đều trở thành một space.
    #
    # Ví dụ:
    #
    #   "liệt sĩ;\nb) Người khuyết tật;"
    #
    # ->
    #
    #   "liệt sĩ; b) Người khuyết tật;"
    #
    # ========================================================

    old_text = text

    text = re.sub(
        r"\n+",
        " ",
        text
    )

    if text != old_text:

        stats[
            "replaced newline with space"
        ] += 1

    # ========================================================
    # 5. XỬ LÝ LITERAL "\\n"
    # ========================================================
    #
    # Một số dữ liệu crawl có thể chứa:
    #
    #   ký tự \ + n
    #
    # thay vì newline thật.
    #
    # Ví dụ:
    #
    #   "liệt sĩ;\\nb) Người khuyết tật;"
    #
    # ->
    #
    #   "liệt sĩ; b) Người khuyết tật;"
    #
    # ========================================================

    old_text = text

    text = re.sub(
        r"(?:\\n)+",
        " ",
        text
    )

    if text != old_text:

        stats[
            "replaced literal \\\\n with space"
        ] += 1

    # ========================================================
    # 6. XỬ LÝ TAB
    # ========================================================
    #
    # Tab cũng được chuyển thành space để tránh tạo
    # khoảng cách bất thường trong content.
    #
    # ========================================================

    old_text = text

    text = text.replace(
        "\t",
        " "
    )

    if text != old_text:

        stats[
            "replaced tab with space"
        ] += 1

    # ========================================================
    # 7. GOM NHIỀU SPACE
    # ========================================================
    #
    # Ví dụ:
    #
    #   "abc     def"
    #
    # ->
    #
    #   "abc def"
    #
    # ========================================================

    old_text = text

    text = re.sub(
        r" +",
        " ",
        text
    )

    if text != old_text:

        stats[
            "normalized multiple spaces"
        ] += 1

    # ========================================================
    # 8. XÓA SPACE ĐẦU / CUỐI
    # ========================================================

    old_text = text

    text = text.strip()

    if text != old_text:

        stats[
            "trimmed spaces"
        ] += 1

    return text


# ============================================================
# KIỂM TRA NODE CÓ NỘI DUNG
# ============================================================

def node_has_content(
    node: Any,
) -> bool:
    """
    Kiểm tra node có nội dung thực tế hay không.

    Một node được coi là có nội dung nếu:
        - content có text
        - hoặc title có text
        - hoặc children có node có nội dung
    """

    if not isinstance(
        node,
        dict
    ):

        return False

    # ========================================================
    # CONTENT
    # ========================================================

    content = node.get(
        "content"
    )

    if isinstance(
        content,
        str
    ):

        if content.strip():

            return True

    # ========================================================
    # TITLE
    # ========================================================

    title = node.get(
        "title"
    )

    if isinstance(
        title,
        str
    ):

        if title.strip():

            return True

    # ========================================================
    # CHILDREN
    # ========================================================

    children = node.get(
        "children"
    )

    if isinstance(
        children,
        list
    ):

        for child in children:

            if node_has_content(
                child
            ):

                return True

    return False


# ============================================================
# KIỂM TRA CONTENT TREE
# ============================================================

def has_real_content(
    content_tree: Any,
) -> bool:
    """
    Kiểm tra content_tree có nội dung hay không.
    """

    # --------------------------------------------------------
    # None
    # --------------------------------------------------------

    if content_tree is None:

        return False

    # --------------------------------------------------------
    # LIST
    # --------------------------------------------------------

    if isinstance(
        content_tree,
        list
    ):

        if not content_tree:

            return False

        for node in content_tree:

            if node_has_content(
                node
            ):

                return True

        return False

    # --------------------------------------------------------
    # DICT
    # --------------------------------------------------------

    if isinstance(
        content_tree,
        dict
    ):

        return node_has_content(
            content_tree
        )

    # --------------------------------------------------------
    # STRING
    # --------------------------------------------------------

    if isinstance(
        content_tree,
        str
    ):

        return bool(
            content_tree.strip()
        )

    return False


# ============================================================
# LÀM SẠCH CONTENT TREE
# ============================================================

def clean_content_tree(
    value: Any,
    stats: Counter[str],
) -> Any:
    """
    Đệ quy làm sạch toàn bộ text bên trong content_tree.

    Cấu trúc dict/list được giữ nguyên.

    QUAN TRỌNG:
    -----------
    Không làm sạch key của JSON.

    Ví dụ:

        "level"
        "number"
        "title"
        "content"
        "key"
        "citation"
        "label"
        "children"

    đều được giữ nguyên.
    """

    # ========================================================
    # STRING
    # ========================================================

    if isinstance(
        value,
        str
    ):

        return clean_text(
            value,
            stats
        )

    # ========================================================
    # LIST
    # ========================================================

    if isinstance(
        value,
        list
    ):

        return [
            clean_content_tree(
                item,
                stats
            )
            for item in value
        ]

    # ========================================================
    # DICT
    # ========================================================

    if isinstance(
        value,
        dict
    ):

        result = {}

        for key, item in value.items():

            # Giữ nguyên key.
            result[key] = clean_content_tree(
                item,
                stats
            )

        return result

    # ========================================================
    # NUMBER / BOOL / NONE
    # ========================================================

    return value


# ============================================================
# LÀM SẠCH MỘT VĂN BẢN
# ============================================================

def clean_document(
    document: Any,
    stats: Counter[str],
) -> tuple[Any, bool]:
    """
    Làm sạch một document.

    Returns:
        cleaned_document, valid
    """

    if not isinstance(
        document,
        dict
    ):

        return document, False

    # ========================================================
    # LẤY CONTENT TREE
    # ========================================================

    content_tree = document.get(
        "content_tree"
    )

    # ========================================================
    # KIỂM TRA VĂN BẢN TRỐNG
    # ========================================================

    if not has_real_content(
        content_tree
    ):

        return document, False

    # ========================================================
    # COPY DOCUMENT
    # ========================================================

    cleaned_document = dict(
        document
    )

    # ========================================================
    # CHỈ XỬ LÝ CONTENT_TREE
    # ========================================================

    cleaned_document[
        "content_tree"
    ] = clean_content_tree(
        content_tree,
        stats
    )

    return cleaned_document, True


# ============================================================
# LƯU SOURCE_URL CỦA VĂN BẢN TRỐNG
# ============================================================

def save_empty_links(
    links: list[dict[str, str]],
    path: Path,
) -> None:
    """
    Lưu thông tin văn bản không có content.

    Format:

    [
      {
        "title": "...",
        "doc_number": "...",
        "source_url": "..."
      }
    ]
    """

    path.parent.mkdir(
        parents=True,
        exist_ok=True
    )

    with path.open(
        "w",
        encoding="utf-8",
        newline="\n"
    ) as file:

        json.dump(
            links,
            file,
            ensure_ascii=False,
            indent=2
        )

        file.write("\n")


# ============================================================
# ARGUMENT PARSER
# ============================================================

def parse_args() -> argparse.Namespace:

    parser = argparse.ArgumentParser(
        description=(
            "Clean Unicode and newline "
            "inside VBPL content."
        )
    )

    # ========================================================
    # INPUT
    # ========================================================
    #
    # Không bắt buộc.
    #
    # python clean_json_chars.py
    #
    # sẽ dùng DEFAULT_INPUT.
    #
    # ========================================================

    parser.add_argument(
        "input",
        nargs="?",
        type=Path,
        help=(
            "Input JSON file. "
            "Nếu bỏ trống sẽ dùng DEFAULT_INPUT."
        )
    )

    # ========================================================
    # OUTPUT
    # ========================================================

    parser.add_argument(
        "-o",
        "--output",
        type=Path,
        help=(
            "Output JSON file."
        )
    )

    # ========================================================
    # LINK FILE
    # ========================================================

    parser.add_argument(
        "--link-file",
        type=Path,
        help=(
            "File JSON lưu source_url "
            "của văn bản trống."
        )
    )

    # ========================================================
    # IN PLACE
    # ========================================================

    parser.add_argument(
        "--in-place",
        action="store_true",
        help=(
            "Ghi đè file input sau khi "
            "tạo backup."
        )
    )

    # ========================================================
    # DRY RUN
    # ========================================================

    parser.add_argument(
        "--dry-run",
        action="store_true",
        help=(
            "Chỉ kiểm tra và thống kê, "
            "không ghi file."
        )
    )

    return parser.parse_args()


# ============================================================
# MAIN
# ============================================================

def main() -> int:

    args = parse_args()

    # ========================================================
    # 1. XÁC ĐỊNH INPUT
    # ========================================================

    input_path = DEFAULT_INPUT

    if args.input is not None:

        input_path = args.input

    # ========================================================
    # 2. KIỂM TRA OPTION
    # ========================================================

    if (
        args.in_place
        and args.output
    ):

        print(
            "[LỖI] Không dùng đồng thời "
            "--in-place và --output."
        )

        return 1

    # ========================================================
    # 3. OUTPUT
    # ========================================================

    if args.in_place:

        output_path = input_path

    else:

        output_path = (
            args.output
            or input_path.with_name(
                f"{input_path.stem}.cleaned"
                f"{input_path.suffix}"
            )
        )

    # ========================================================
    # 4. LINK FILE
    # ========================================================

    link_path = (
        args.link_file
        or input_path.parent
        / "PL_link_hd.json"
    )

    # ========================================================
    # 5. KIỂM TRA INPUT
    # ========================================================

    if not input_path.exists():

        print()
        print(
            "[LỖI] Không tìm thấy file:"
        )

        print(
            f"  {input_path}"
        )

        print()
        print(
            "Hãy sửa DEFAULT_INPUT "
            "ở đầu file."
        )

        return 1

    # ========================================================
    # 6. ĐỌC JSON
    # ========================================================

    try:

        with input_path.open(
            "r",
            encoding="utf-8-sig"
        ) as file:

            data = json.load(
                file
            )

    except (
        OSError,
        UnicodeError,
        json.JSONDecodeError
    ) as error:

        print()
        print(
            "[LỖI] Không đọc được JSON:"
        )

        print(
            f"  {error}"
        )

        return 1

    # ========================================================
    # 7. KIỂM TRA ROOT
    # ========================================================

    if not isinstance(
        data,
        list
    ):

        print()
        print(
            "[LỖI] JSON phải có root "
            "dạng danh sách []."
        )

        return 1

    # ========================================================
    # 8. KHỞI TẠO
    # ========================================================

    stats: Counter[str] = Counter()

    cleaned_documents: list[Any] = []

    empty_links: list[dict[str, str]] = []

    total_documents = len(
        data
    )

    kept_documents = 0

    skipped_documents = 0

    # ========================================================
    # 9. DUYỆT DOCUMENT
    # ========================================================

    for index, document in enumerate(
        data,
        start=1
    ):

        cleaned_document, valid = (
            clean_document(
                document,
                stats
            )
        )

        # ====================================================
        # DOCUMENT TRỐNG
        # ====================================================

        if not valid:

            skipped_documents += 1

            # -----------------------------------------------
            # LƯU SOURCE_URL
            # -----------------------------------------------

            if isinstance(
                document,
                dict
            ):

                title = document.get(
                    "title",
                    ""
                )

                doc_number = document.get(
                    "doc_number",
                    ""
                )

                source_url = document.get(
                    "source_url",
                    ""
                )

                if (
                    isinstance(
                        source_url,
                        str
                    )
                    and source_url.strip()
                ):

                    empty_links.append(
                        {
                            "title": str(
                                title
                            ),

                            "doc_number": str(
                                doc_number
                            ),

                            "source_url": source_url,
                        }
                    )

            print(
                f"[BỎ] Văn bản #{index}: "
                f"không có content"
            )

            continue

        # ====================================================
        # DOCUMENT HỢP LỆ
        # ====================================================

        cleaned_documents.append(
            cleaned_document
        )

        kept_documents += 1

    # ========================================================
    # 10. THỐNG KÊ
    # ========================================================

    print()
    print("=" * 75)
    print("CLEAN JSON VBPL - CONTENT")
    print("=" * 75)

    print(
        f"Tổng số văn bản   : "
        f"{total_documents}"
    )

    print(
        f"Văn bản giữ lại   : "
        f"{kept_documents}"
    )

    print(
        f"Văn bản bỏ        : "
        f"{skipped_documents}"
    )

    print(
        f"URL đã lưu        : "
        f"{len(empty_links)}"
    )

    print(
        f"Số thay đổi       : "
        f"{sum(stats.values())}"
    )

    # ========================================================
    # 11. CHI TIẾT THAY ĐỔI
    # ========================================================

    if stats:

        print()
        print("-" * 75)
        print("CHI TIẾT")
        print("-" * 75)

        for description, count in (
            stats.most_common()
        ):

            print(
                f"{count:>10}  "
                f"{description}"
            )

    # ========================================================
    # 12. DRY RUN
    # ========================================================

    if args.dry_run:

        print()
        print(
            "[DRY-RUN] Không ghi file."
        )

        return 0

    # ========================================================
    # 13. BACKUP
    # ========================================================

    if args.in_place:

        backup_path = Path(
            str(input_path)
            + ".backup"
        )

        try:

            shutil.copy2(
                input_path,
                backup_path
            )

            print()
            print(
                f"Đã tạo backup:"
            )

            print(
                f"  {backup_path}"
            )

        except OSError as error:

            print()
            print(
                "[LỖI] Không tạo được backup:"
            )

            print(
                f"  {error}"
            )

            return 1

    # ========================================================
    # 14. GHI OUTPUT
    # ========================================================

    try:

        output_path.parent.mkdir(
            parents=True,
            exist_ok=True
        )

        with output_path.open(
            "w",
            encoding="utf-8",
            newline="\n"
        ) as file:

            json.dump(
                cleaned_documents,
                file,
                ensure_ascii=False,
                indent=2
            )

            file.write("\n")

    except OSError as error:

        print()
        print(
            "[LỖI] Không ghi được "
            "file output:"
        )

        print(
            f"  {error}"
        )

        return 1

    # ========================================================
    # 15. GHI PL_link_hd.json
    # ========================================================

    try:

        save_empty_links(
            empty_links,
            link_path
        )

    except OSError as error:

        print()
        print(
            "[LỖI] Không ghi được "
            "PL_link_hd.json:"
        )

        print(
            f"  {error}"
        )

        return 1

    # ========================================================
    # 16. HOÀN TẤT
    # ========================================================

    print()
    print("=" * 75)
    print("HOÀN TẤT")
    print("=" * 75)

    print()
    print(
        "File output:"
    )

    print(
        f"  {output_path}"
    )

    print()
    print(
        "File link văn bản trống:"
    )

    print(
        f"  {link_path}"
    )

    print()
    print(
        f"Giữ lại : {kept_documents}"
    )

    print(
        f"Bỏ qua  : {skipped_documents}"
    )

    print("=" * 75)

    return 0


# ============================================================
# CHẠY CHƯƠNG TRÌNH
# ============================================================

if __name__ == "__main__":

    raise SystemExit(
        main()
    )

