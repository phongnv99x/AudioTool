import os
import sys
import subprocess
import re
import numpy as np
from difflib import SequenceMatcher


def _add_nvidia_dll_dirs():
    """
    Tự động tìm và đăng ký các thư mục chứa NVIDIA CUDA DLL
    (nvidia-cublas-cu12, nvidia-cudnn-cu12 cài qua pip).
    Phải gọi TRƯỚC KHI import onnxruntime để Windows tìm được DLL.
    """
    if sys.platform != 'win32':
        return  # Linux/VPS Linux không cần, CUDA path được set tự động
    try:
        import site
        site_packages = site.getsitepackages()
        user_site = site.getusersitepackages()
        if user_site:
            site_packages = [user_site] + list(site_packages)
        added = []
        for sp in site_packages:
            nvidia_dir = os.path.join(sp, 'nvidia')
            if not os.path.isdir(nvidia_dir):
                continue
            for pkg_name in os.listdir(nvidia_dir):
                bin_dir = os.path.join(nvidia_dir, pkg_name, 'bin')
                if os.path.isdir(bin_dir):
                    try:
                        os.add_dll_directory(bin_dir)
                        added.append(bin_dir)
                    except Exception:
                        pass
        return added
    except Exception:
        return []

# Gọi ngay khi module được import, trước mọi thứ khác
_add_nvidia_dll_dirs()


def similar(a, b):
    return SequenceMatcher(None, a, b).ratio()


def _init_ocr_gpu():
    """Khởi tạo RapidOCR với CUDA GPU, fallback về CPU nếu không có."""
    from rapidocr_onnxruntime import RapidOCR
    try:
        import onnxruntime as ort
        available_providers = ort.get_available_providers()
        if 'CUDAExecutionProvider' in available_providers:
            ocr = RapidOCR(
                det_use_cuda=True,
                cls_use_cuda=True,
                rec_use_cuda=True,
            )
            return ocr, "GPU (CUDA)"
        else:
            ocr = RapidOCR()
            return ocr, "CPU (CUDA không khả dụng)"
    except Exception:
        ocr = RapidOCR()
        return ocr, "CPU (fallback)"


def _calibrate_char_height(video_path, ocr, roi_bbox, fps, log_callback=None):
    """
    Quét nhanh 60 giây đầu video để tìm chiều cao median của ký tự phụ đề.

    Sub cứng có kích thước font nhất quán → dùng median làm tham chiếu.
    Text UI (tên skill, thông báo hệ thống) thường có font khác kích thước.

    Trả về (h_min, h_max) hoặc (None, None) nếu không đủ mẫu.
    """
    import cv2

    cap = cv2.VideoCapture(video_path)
    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    process_interval = max(int(fps / 2), 1)
    sample_frames = min(int(60 * fps), total_frames)  # Chỉ quét 60s đầu

    heights = []
    frame_idx = 0

    while cap.isOpened() and frame_idx < sample_frames:
        ret = cap.grab()
        if not ret:
            break

        if frame_idx % process_interval == 0:
            ret, frame = cap.retrieve()
            if not ret:
                break

            if roi_bbox:
                x, y, w, h_box = roi_bbox
                crop_img = frame[y:y+h_box, x:x+w]
            else:
                h, w = frame.shape[:2]
                crop_y1 = int(h * 0.8) if w >= h else int(h * 0.5)
                crop_img = frame[crop_y1:, :]

            result, _ = ocr(crop_img)
            if result:
                for item in result:
                    bbox, text, conf = item
                    if conf > 0.6 and bool(re.search(r'[\u4e00-\u9fff]', text)):
                        pts = np.array(bbox, dtype=np.float32)
                        h_bbox = float(pts[:, 1].max() - pts[:, 1].min())
                        if h_bbox > 4:
                            heights.append(h_bbox)

        frame_idx += 1

    cap.release()

    if len(heights) < 5:
        if log_callback:
            log_callback("   ⚠️ Không đủ mẫu để hiệu chỉnh bộ lọc. Quét toàn bộ không lọc font.")
        return None, None

    median_h = float(np.median(heights))
    h_min = median_h * 0.60  # Cho phép ±40% dao động
    h_max = median_h * 1.40

    if log_callback:
        log_callback(
            f"   ✅ Font phụ đề: ~{median_h:.1f}px → chấp nhận [{h_min:.0f}–{h_max:.0f}]px "
            f"(từ {len(heights)} mẫu chữ Hán)"
        )
    return h_min, h_max


def _get_filtered_text(result, ref_h_min, ref_h_max):
    """
    Lọc kết quả OCR theo:
    1. Confidence > 0.6
    2. Chiều cao bbox trong dải tham chiếu (nếu đã calibrate)
    3. Phải chứa ký tự Hán
    """
    if not result:
        return ""

    texts = []
    for item in result:
        bbox, text, conf = item
        if conf <= 0.6:
            continue

        # Lọc theo kích thước font
        if ref_h_min is not None:
            pts = np.array(bbox, dtype=np.float32)
            h_bbox = float(pts[:, 1].max() - pts[:, 1].min())
            if not (ref_h_min <= h_bbox <= ref_h_max):
                continue  # Font khác → text UI, tiêu đề, tên skill...

        texts.append(text)

    if not texts:
        return ""

    detected = re.sub(r'[a-zA-Z]', '', " ".join(texts)).strip()
    has_chinese = bool(re.search(r'[\u4e00-\u9fff]', detected))
    if not has_chinese and len(detected) < 4:
        return ""
    return detected


def extract_subtitles_from_video(video_path, output_srt, log_callback=None,
                                  progress_callback=None, roi_bbox=None,
                                  text_callback=None):
    try:
        import cv2
        import pysrt
        from rapidocr_onnxruntime import RapidOCR
    except ImportError:
        if log_callback: log_callback("Đang tự động cài đặt thư viện OCR...")
        subprocess.run("pip install rapidocr-onnxruntime onnxruntime-gpu opencv-python numpy pysrt",
                       shell=True)
        try:
            import cv2
            import pysrt
            from rapidocr_onnxruntime import RapidOCR
        except ImportError:
            if log_callback: log_callback("Lỗi: Không thể cài đặt thư viện.")
            return False

    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        if log_callback: log_callback(f"Lỗi: Không thể mở video {video_path}")
        return False

    fps          = cap.get(cv2.CAP_PROP_FPS)
    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    cap.release()

    process_interval = max(int(fps / 2), 1)  # ~2 frame/giây

    # --- Khởi tạo OCR ---
    if log_callback: log_callback("Đang khởi tạo bộ máy OCR...")
    ocr, mode = _init_ocr_gpu()
    if log_callback: log_callback(f"✅ OCR trên: {mode}")
    if log_callback: log_callback(
        f"Tổng frame: {total_frames} | FPS: {fps:.1f} | "
        f"Quét mỗi {process_interval} frame (~2fps)"
    )

    # --- BƯỚC 0: Auto-calibrate chiều cao ký tự ---
    if log_callback: log_callback("\n🔍 Hiệu chỉnh bộ lọc font (quét 60s đầu)...")
    ref_h_min, ref_h_max = _calibrate_char_height(
        video_path, ocr, roi_bbox, fps, log_callback
    )

    # --- Quét video ---
    cap            = cv2.VideoCapture(video_path)
    subs           = []
    current_text   = ""
    current_start  = 0
    last_seen      = 0
    MIN_DURATION   = 0.3  # Chỉ lọc flash < 0.3s; câu ngắn như "好" vẫn được giữ
    frame_idx      = 0
    processed      = 0

    def _save(text, start, end):
        if end - start >= MIN_DURATION:
            subs.append({'text': text, 'start': start, 'end': end + 0.3})

    def _log_new(t_sec, text):
        if text_callback:
            h_ = int(t_sec // 3600)
            m_ = int((t_sec % 3600) // 60)
            s_ = int(t_sec % 60)
            text_callback(f"[{h_:02d}:{m_:02d}:{s_:02d}] {text}")

    while cap.isOpened():
        ret = cap.grab()
        if not ret:
            break

        if frame_idx % process_interval == 0:
            ret, frame = cap.retrieve()
            if not ret:
                break

            t = frame_idx / fps

            if roi_bbox:
                x, y, w, h_box = roi_bbox
                crop = frame[y:y+h_box, x:x+w]
            else:
                h, w = frame.shape[:2]
                y0 = int(h * 0.5) if h > w else int(h * 0.8)
                crop = frame[y0:, :]

            result, _ = ocr(crop)
            text = _get_filtered_text(result, ref_h_min, ref_h_max)

            if text:
                if not current_text:
                    current_text  = text
                    current_start = t
                    last_seen     = t
                    _log_new(t, text)
                elif similar(current_text, text) > 0.7:
                    last_seen = t
                    if len(text) > len(current_text):
                        current_text = text
                else:
                    _save(current_text, current_start, last_seen)
                    current_text  = text
                    current_start = t
                    last_seen     = t
                    _log_new(t, text)
            else:
                if current_text:
                    _save(current_text, current_start, last_seen)
                    current_text = ""

            processed += 1
            if progress_callback and frame_idx % (process_interval * 30) == 0:
                progress_callback(min(frame_idx / total_frames, 0.99))
            if log_callback and processed % 200 == 0:
                pct = frame_idx / total_frames * 100
                log_callback(
                    f"   [{pct:.1f}%] Đã quét {processed} frame | "
                    f"Tìm được {len(subs)} dòng phụ đề..."
                )

        frame_idx += 1

    cap.release()

    if current_text:
        _save(current_text, current_start, last_seen)

    # --- Lưu SRT ---
    import pysrt
    srt_file = pysrt.SubRipFile()
    for i, sub in enumerate(subs):
        srt_file.append(pysrt.SubRipItem(
            index=i+1,
            start=pysrt.SubRipTime(milliseconds=int(sub['start'] * 1000)),
            end=pysrt.SubRipTime(milliseconds=int(sub['end'] * 1000)),
            text=sub['text']
        ))

    srt_file.save(output_srt, encoding='utf-8')
    if progress_callback: progress_callback(1.0)
    if log_callback:
        log_callback(f"HOÀN TẤT! Đã cào được {len(subs)} dòng phụ đề.")
        log_callback(f"Đã lưu SRT tại: {output_srt}")
    return True


if __name__ == "__main__":
    if len(sys.argv) > 2:
        extract_subtitles_from_video(sys.argv[1], sys.argv[2], print)
