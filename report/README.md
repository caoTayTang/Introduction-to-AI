# Báo cáo chung: Pipes và Light Up

Tài liệu nộp là `main-vi.tex`: tiếng Việt, A4 theo bố cục báo cáo mẫu của nhóm.
Gồm mô hình bài toán, trạng thái/đích/bước chuyển, không gian tìm kiếm,
giả mã, cắt tỉa/heuristic, độ phức tạp, thực nghiệm và giới hạn kết luận.

Hai section chính là Pipes và Light Up. Mỗi section dùng cùng 8 subsection:
Giới thiệu; Phát biểu bài toán tìm kiếm; Tạo dữ liệu đầu vào; Giải thuật tìm
kiếm mù; Giải thuật tìm kiếm heuristic; Hiện thực và minh họa từng bước;
Kết quả thực nghiệm; Nhận xét. Phụ lục `lightup-per-input.tex` chứa kết quả
thời gian/bộ nhớ của từng seed Light Up, lấy từ CSV gốc.

Thông tin giảng viên, lớp, họ tên và MSSV được lấy từ `metadata.tex` cho
báo cáo và cả hai bản slide. Khi đổi thành viên hoặc giảng viên, sửa file này
rồi biên dịch lại. Tên tiếng Việt được giữ đầy đủ dấu trong bản tiếng Anh.

Từ thư mục gốc, biên dịch và đặt tên PDF như sau. Dùng thư mục build riêng để
hai nguồn `report/main-vi.tex` và `slides/main-vi.tex` không ghi đè PDF của nhau:

```sh
mkdir -p output/final output/build/report-vi output/build/slide-vi output/build/slide-en

tectonic report/main-vi.tex --outdir output/build/report-vi && \
  cp output/build/report-vi/main-vi.pdf output/final/report-vi.pdf

tectonic slides/main-vi.tex --outdir output/build/slide-vi && \
  cp output/build/slide-vi/main-vi.pdf output/final/slide.-vi.pdf

tectonic slides/main-en.tex --outdir output/build/slide-en && \
  cp output/build/slide-en/main-en.pdf output/final/slide-en.pdf
```

Ba đầu ra là `output/final/report-vi.pdf`, `output/final/slide.-vi.pdf` và
`output/final/slide-en.pdf`. Dấu chấm trong `slide.-vi.pdf` được giữ đúng tên
yêu cầu. Hai bản slide dùng bố cục gốc của `slides/main-vi.tex` và
`slides/main-en.tex`; phần Light Up đồng bộ về nội dung, công thức MRV/gain và
biểu đồ mean. `slides/submission.tex` là bản dùng theme HCMUT riêng.

Có thể dùng XeLaTeX trên Overleaf với `report` và `slides` giữ cạnh nhau.
Times New Roman/Arial có phông thay thế tự do nếu máy không cài sẵn.
Logo trường trích từ báo cáo mẫu do nhóm cung cấp. Minh họa gain của seed
70098 dùng chung hai file TikZ `assets/lightup-gain-70098-a.tex` và
`assets/lightup-gain-70098-b.tex` giữa báo cáo và slide; cần giữ các file này.

Pipes dùng lô 25/10/2026: 9 bản đồ × 2 thuật toán × 5 lần lặp.
Light Up dùng lô 31/10/2026: 60 bản khác nhau × 2 thuật toán.
CSV, manifest và summary gốc nằm trong `docs/benchmarks`.
Không trộn kết quả generator Light Up cũ với generator hiện tại.

`main.tex`, `chapters/`, `generated/`, `build_tables.py` là bản Pipes riêng
trước khi ghép; không phải tài liệu nộp chung và không đưa vào ZIP.
