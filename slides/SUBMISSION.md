# Slides nộp: Pipes và Light Up

Tài liệu chính: `submission.tex`. Biên dịch từ gốc mã nguồn:

```sh
mkdir -p output/final
tectonic slides/submission.tex --outdir output/final
```

Theme `beamerthemeHCMUT.sty` dựa trên Beamer Madrid. Logo dùng bản trích từ
báo cáo mẫu của nhóm trong `report/assets/`. Theme có tên trường/khoa,
định vị section/subsection và số trang. PDF 16:9, hình minh họa bằng TikZ.

Hai section là Pipes và Light Up, mỗi game dùng đúng cùng 8 subsection
với báo cáo. Một subsection có thể có nhiều slide, như phần CP/MRV hoặc
kết quả Light Up. Nội dung tập trung luật, mô hình tìm kiếm, input, hai
giải thuật, minh họa, bảng thời gian/bộ nhớ và nhận xét theo đề BTL1.

Thông tin giảng viên, lớp, thành viên lấy từ `report/metadata.tex`.
Giữ thư mục `report/` và `slides/` cạnh nhau để các đường dẫn hoạt động.

`slides/main-vi.pdf` và `report/main-vi.pdf` trong repository vẫn là PDF
gốc của Huy ở commit ce01a0e. Bản chỉnh để nộp xuất sang `output/final/`
rồi được script đóng gói sao chép vào `output/submission/`.
