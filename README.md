# ✍ Xưởng Truyện

App viết truyện bằng AI chạy **hoàn toàn trên máy bạn** (giống QuarterFull Studio). Có sẵn bộ máy chạy model và nút tải model không kiểm duyệt – bấm 1 nút là dùng được. Vẫn hỗ trợ LM Studio / Ollama / KoboldCpp.

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

## Model AI – có sẵn trong app (không cần LM Studio)

Lần đầu mở app sẽ hiện màn **Chào mừng** → bấm **⚡ Cài tự động**. App tự:
1. Tải **bộ máy llama.cpp** bản CUDA cho card NVIDIA (khoảng 200–600 MB),
2. Tải model đề xuất **Gemma 4 12B Abliterated** (8,6 GB),
3. Chạy model và kết nối – thanh trên cùng hiện chấm xanh là viết được.

Lần sau mở app, model tự chạy lại. Bấm nút **🧠** trên thanh trên cùng để mở **Model AI**:

| Model đề xuất (đều không kiểm duyệt, viết được 18+/NSFW) | Dung lượng | Trên RTX 3060 12GB |
|---|---|---|
| ⭐ Gemma 4 12B Abliterated – tiếng Việt tốt | 8,6 GB | Rất nhanh, chạy hết trên GPU |
| Gemma 4 26B-A4B Heretic (MoE) – tiếng Việt tốt | 16,8 GB | Khá nhanh, tràn một phần sang RAM |
| Qwen 3.6 27B Abliterated – tiếng Việt tốt, viết hay nhất | 16,6 GB | Chậm (3–6 chữ/giây) |
| Qwen3 14B Abliterated – tiếng Việt khá | 10,5 GB | Nhanh, vừa khít GPU |
| Rocinante 12B – chuyên truyện 18+ tiếng Anh | 8,7 GB | Rất nhanh |
| Cydonia 24B – truyện 18+ tiếng Anh | 14,3 GB | Trung bình |

- **⬇ Tải & dùng**: tải xong tự chạy. **Chỉ tải**: tải để dành. Bị ngắt mạng thì bấm tải lại – app **tải tiếp** phần còn thiếu.
- **▶ Dùng model này**: đổi model (vài giây đến 1 phút để nạp).
- **Context**: 16k là hợp lý; 32k nhớ truyện dài hơn nhưng tốn VRAM hơn. Đổi xong bấm **↻ Khởi động lại**.
- **Model trên máy**: tự nhận model đã tải bằng LM Studio; thêm thư mục chứa file `.gguf` khác ở mục *Tải model khác*.
- **Tải model khác từ HuggingFace**: dán tên repo (VD `bartowski/…-GGUF`) hoặc link, chọn bản nén (Q4_K_M/Q5_K_M…), bấm Tải.
- App tự chia model giữa GPU và RAM cho vừa máy. Báo lỗi thiếu bộ nhớ → giảm Context hoặc chọn model nhỏ hơn.
- Bộ máy lỗi trên máy bạn → chọn **Vulkan** rồi bấm *Cập nhật / cài lại*.
- Nên đặt app ở thư mục **không dấu** (VD `D:\XuongTruyen`).
- Truyện NSFW: chọn **NSFW** trong trang *Tổng quan* của từng truyện.

## Dùng LM Studio / Ollama / KoboldCpp (tuỳ chọn)

**LM Studio**
1. Cài từ lmstudio.ai → biểu tượng kính lúp (**Discover**) → tìm model (VD `gemma-4-12B-it-abliterated`) → chọn bản **GGUF Q4_K_M / Q5_K_M** → **Download**.
2. Bấm **Select a model to load** → bật *Manually choose model load parameters*: **Context Length 16384**, **GPU Offload** kéo hết (model ≤ 11GB) hoặc ~70–85% (model lớn), bật **Flash Attention**, **K/V Cache = Q8_0** → **Load Model**.
3. Tab **Developer** (`>_`) → gạt **Status: Running** (địa chỉ `http://127.0.0.1:1234`).
4. Trong Xưởng Truyện: **⚙** → *Phần mềm chạy model* = **LM Studio** → **↻ Tải danh sách** → chọn model → **Lưu**. Ô *Ngữ cảnh gửi cho AI* ≈ 28000 (context 16k) hoặc 55000 (32k).

**Ollama**: cài từ ollama.com → `ollama pull hf.co/<repo-GGUF>:Q4_K_M` → đặt `setx OLLAMA_CONTEXT_LENGTH 16384` rồi mở lại Ollama → trong app chọn **Ollama**.

**KoboldCpp**: tải `koboldcpp_cu12.exe` → *Browse* chọn file `.gguf` → *GPU Layers* -1, *Context Size* 16384 → **Launch** → trong app chọn **KoboldCpp**.

## Chạy từ mã nguồn / tự build

```bat
run_dev.bat          :: chạy bằng Python 3.10+
build_portable.bat   :: tự build ra dist\XuongTruyen\XuongTruyen.exe
```

Phát hành bản mới: tăng số trong `app/version.py` rồi đẩy lên nhánh `main` – GitHub Actions tự build bản portable, tạo tag và Release; nút ⟳ trong app sẽ thấy bản mới.
