# Bài tập lớn 1 — Pipes và Light Up

Gói LMS chứa `report.pdf`, `slides.pdf` và `source_code/`.
Một thành viên đại diện nhóm tải cả file ZIP lên LMS.
Hạn nộp và ngày trình bày: chờ thông báo của giảng viên.

**Trước khi nộp:** bổ sung giảng viên, lớp, họ tên và MSSV trong
`source_code/report/metadata.tex`, rồi biên dịch và đóng gói lại.
Các thông tin này hiện để trống vì chưa được cung cấp.

## Chạy chương trình

Cần Python 3.13 và uv. Từ thư mục `source_code` sau khi giải nén:

```sh
uv sync --frozen
uv run main.py pipes
uv run main.py lightup
```

Pipes: DFS và Greedy Best-First. Light Up: DFS và Backtracking + MRV +
Constraint Propagation (CSP); mã còn có A* để tham khảo. Báo cáo chính so sánh
DFS/CSP cho Light Up, không trộn kết quả A* từ generator cũ.
Mỗi game có chơi tay, giải tự động và xem bước tìm kiếm.

## Kiểm tra

```sh
uv run ruff check main.py pipes_problem light_up_problem
uv run python -m unittest discover -s pipes_problem -t .
uv run python -m unittest discover -s light_up_problem -t .
```

Khi chuẩn bị gói: 33 kiểm thử Pipes và 65 kiểm thử Light Up đạt; lint đạt.

## Thực nghiệm

```sh
uv run python -m pipes_problem.benchmark
uv run python -m light_up_problem.benchmark.suite \
  --output-prefix results/lightup-dfs-csp --seeds-per-config 5 \
  --timeout 30 --node-limit 500000 --memory-limit-mb 512
```

Benchmark đầy đủ Light Up có thể mất nhiều phút. Chạy một lệnh benchmark
mỗi lần để hạn chế nhiễu. Dữ liệu gốc kèm trong `docs/benchmarks`:

- Pipes 25/10: 9 bản × 2 thuật toán × 5 lượt = 90, tất cả SOLVED.
- Light Up 31/10: 60 bản × 2 thuật toán = 120; DFS 52 SOLVED/8 TIMEOUT,
  CSP 60 SOLVED. Mỗi cấu hình có 5 seed khác nhau, không phải 5 lần cùng bàn.
- Peak là đỉnh cấp phát Python, không phải RSS. Pipes tách đo bộ nhớ khỏi
  lượt đo thời gian; Light Up bật tracemalloc khi đo thời gian.
- Hash solver/generator/luật Light Up khớp manifest. Hai tệp điều phối
  benchmark đã thay đổi so với thời điểm đo; manifest lịch sử được giữ nguyên.
  Gói hỗ trợ benchmark khi không có Git hoặc thư mục `.git`.

Phân tích chi tiết: `docs/pipes-analysis.md`, `docs/lightup-analysis.md`.

## Biên dịch lại tài liệu

Giữ `report/` và `slides/` cạnh nhau. Cài Tectonic rồi chạy từ `source_code`:

```sh
mkdir -p output/final
tectonic report/main-vi.tex --outdir output/final
tectonic slides/submission.tex --outdir output/final
python3 scripts/package_submission.py
```

Slides là PDF Beamer 16:9 với hình TikZ chỉnh sửa được; nguồn `.tex` kèm theo.
Script tạo `output/submission/Introduction-to-AI-submission.zip`, gồm đúng
hai PDF ở gốc, mã nguồn và danh sách SHA-256 để đối chiếu nội dung.
Không kèm môi trường ảo, lịch sử Git hoặc bài legacy.
