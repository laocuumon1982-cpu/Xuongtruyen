# ✍ Xưởng Truyện

App viết truyện bằng AI chạy **hoàn toàn trên máy bạn** (giống QuarterFull Studio), dùng model local qua LM Studio / Ollama / KoboldCpp / llama.cpp.

## Tải về

Vào [Releases](https://github.com/laocuumon1982-cpu/Xuongtruyen/releases) → tải `XuongTruyen_Portable_vX.Y.Z.zip` → giải nén → chạy `XuongTruyen.exe`.
Không cần cài đặt. Truyện và cài đặt nằm trong thư mục `data\` cạnh file exe (chép cả thư mục sang máy khác là dùng tiếp được).

## Cách dùng

1. **Ném ý tưởng** (hoặc chuyển sang tab *Dán bản nháp*), chọn số chương, thể loại, giới hạn nội dung → bấm **✨ Lên truyện**.
   AI tạo tên truyện, nhân vật, thế giới và dàn ý từng chương.
2. Mở một chương → **✍ Viết chương** (viết cả chương theo dàn ý) hoặc **➜ Viết tiếp** (viết tiếp từ vị trí con trỏ, phím tắt `Ctrl+Enter`).
3. **Bôi đen** một đoạn → menu hiện ra: *Viết lại · Mở rộng · Rút gọn · Đổi giọng văn · Tuỳ ý*. Xem trước kết quả rồi bấm *Thay thế* hoặc *Chèn phía sau*.
4. **↶ Hoàn tác** để quay lại bản trước mỗi thao tác AI.
5. **💬 Trợ lý truyện** (cột phải) để bàn về cốt truyện, plot twist, soát lỗi logic…
6. **Tự tóm tắt chương cũ**: trước khi viết chương mới, app tự tóm tắt các chương đã viết (hoặc vừa sửa) để AI nhớ mạch truyện dài.
7. **Giới hạn nội dung riêng từng truyện**: Mọi lứa tuổi / 18+ / NSFW (đổi trong *Tổng quan*). Ở mọi chế độ, nhân vật trong cảnh nóng luôn là người trưởng thành.
8. **Xuất** ra Word (.docx), EPUB hoặc TXT ở trang *Tổng quan*.
9. Nút **⟳** trên thanh trên cùng: kiểm tra và tự cập nhật bản mới từ GitHub (giữ nguyên thư mục `data`).

## Cài model (khuyên dùng LM Studio)

1. Cài [LM Studio](https://lmstudio.ai), tải một model GGUF.
2. Tab **Developer** → bật **Start server** (mặc định `http://127.0.0.1:1234/v1`).
3. Trong Xưởng Truyện bấm **⚙** → chọn LM Studio → *Tải danh sách* → chọn model → *Lưu*.

Với **RTX 3060 12GB + RAM 32GB**:

| Model | Lượng tử | Chạy | Ghi chú |
|---|---|---|---|
| 12–14B (Mistral Nemo, Qwen 14B…) | Q4_K_M / Q5_K_M | 100% GPU | Nhanh, ~25–40 token/s |
| 24–27B (Qwen 27B, Gemma 27B, Mistral Small…) | Q4_K_M | GPU + RAM | Viết hay hơn, ~3–8 token/s |

- Đặt **Context Length** của model ≥ 16384. Ô *Ngữ cảnh gửi cho AI* trong cài đặt ≈ 3 × số token context × 0,6 (ví dụ 16k → khoảng 28000 ký tự).
- Model Qwen3 có chế độ "suy nghĩ": để bật ô *Tắt chế độ suy nghĩ* cho nhanh; phần `<think>` luôn được lọc bỏ khỏi truyện.
- Ollama: `http://127.0.0.1:11434/v1` · KoboldCpp: `http://127.0.0.1:5001/v1`.

## Chạy từ mã nguồn / tự build

```bat
run_dev.bat          :: chạy bằng Python 3.10+
build_portable.bat   :: tự build ra dist\XuongTruyen\XuongTruyen.exe
```

Phát hành bản mới: sửa `app/version.py`, rồi đẩy tag `vX.Y.Z` lên GitHub – GitHub Actions sẽ build bản portable và tạo Release; nút ⟳ trong app sẽ thấy bản mới.
