# Báo cáo chung: Pipes và Light Up

Tài liệu nộp là `main-vi.tex`: tiếng Việt, A4 theo bố cục báo cáo mẫu của nhóm.
Gồm mô hình bài toán, trạng thái/đích/bước chuyển, không gian tìm kiếm,
giả mã, cắt tỉa/heuristic, độ phức tạp, thực nghiệm và giới hạn kết luận.

Hai section chính là Pipes và Light Up. Mỗi section dùng cùng 8 subsection:
Giới thiệu; Phát biểu bài toán tìm kiếm; Tạo dữ liệu đầu vào; Giải thuật tìm
kiếm mù; Giải thuật tìm kiếm heuristic; Hiện thực và minh họa từng bước;
Kết quả thực nghiệm; Nhận xét. Phụ lục `lightup-per-input.tex` chứa kết quả
thời gian/bộ nhớ của từng seed Light Up, lấy từ CSV gốc.

Điền giảng viên, lớp, họ tên và MSSV trong `metadata.tex` trước khi nộp.
Hiện chưa có thông tin này; không dùng lại danh tính trong báo cáo mẫu.

Từ thư mục gốc:

```sh
mkdir -p output/final
tectonic report/main-vi.tex --outdir output/final
tectonic slides/submission.tex --outdir output/final
python3 scripts/package_submission.py
```

Có thể dùng XeLaTeX trên Overleaf với `report` và `slides` giữ cạnh nhau.
Times New Roman/Arial có phông thay thế tự do nếu máy không cài sẵn.
Logo trường trích từ báo cáo mẫu do nhóm cung cấp.
Slides dùng `slides/beamerthemeHCMUT.sty`, dựa trên Beamer Madrid, có logo
HCMUT, tên trường/khoa và số mục của từng game. Cần giữ file theme khi biên dịch.

Pipes dùng lô 25/10/2026: 9 bản đồ × 2 thuật toán × 5 lần lặp.
Light Up dùng lô 31/10/2026: 60 bản khác nhau × 2 thuật toán.
CSV, manifest và summary gốc nằm trong `docs/benchmarks`.
Không trộn kết quả generator Light Up cũ với generator hiện tại.

`main.tex`, `chapters/`, `generated/`, `build_tables.py` là bản Pipes riêng
trước khi ghép; không phải tài liệu nộp chung và không đưa vào ZIP.
