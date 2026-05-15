import os
import sys
import subprocess
import re
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
        # Thêm cả user site-packages
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

def extract_subtitles_from_video(video_path, output_srt, log_callback=None, progress_callback=None, roi_bbox=None, text_callback=None):
    try:
        import cv2
        import pysrt
        from rapidocr_onnxruntime import RapidOCR
    except ImportError:
        if log_callback: log_callback("Đang tự động cài đặt thư viện OCR... Vui lòng đợi.")
        subprocess.run("pip install rapidocr-onnxruntime onnxruntime-gpu opencv-python numpy pysrt", shell=True)
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

    fps = cap.get(cv2.CAP_PROP_FPS)
    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    cap.release()

    # Quét 2 frame/giây để cân bằng tốc độ và độ chính xác
    process_interval = max(int(fps / 2), 1)

    # --- Khởi tạo OCR với GPU ---
    if log_callback: log_callback("Đang khởi tạo bộ máy OCR...")
    ocr, mode = _init_ocr_gpu()
    if log_callback: log_callback(f"✅ Đã khởi tạo OCR trên: {mode}")
    if log_callback: log_callback(f"Tổng số frame: {total_frames} | FPS: {fps:.1f} | Quét mỗi {process_interval} frame (~2fps)")

    # --- Quét video trên 1 luồng GPU duy nhất ---
    cap = cv2.VideoCapture(video_path)
    subs = []
    current_text = ""
    current_start_time = 0
    last_detected_time = 0
    frame_idx = 0
    processed_count = 0

    while cap.isOpened():
        ret = cap.grab()
        if not ret:
            break

        if frame_idx % process_interval == 0:
            ret, frame = cap.retrieve()
            if not ret:
                break

            current_time_sec = frame_idx / fps

            if roi_bbox:
                x, y, w, h_box = roi_bbox
                crop_img = frame[y:y+h_box, x:x+w]
            else:
                h, w = frame.shape[:2]
                if h > w:
                    crop_y1 = int(h * 0.5)
                    crop_y2 = int(h * 0.95)
                else:
                    crop_y1 = int(h * 0.8)
                    crop_y2 = h
                crop_img = frame[crop_y1:crop_y2, :]

            result, _ = ocr(crop_img)
            detected_text = ""
            if result:
                texts = [res[1] for res in result if res[2] > 0.6]
                detected_text = " ".join(texts).strip()

                if detected_text:
                    detected_text = re.sub(r'[a-zA-Z]', '', detected_text).strip()
                    has_chinese = bool(re.search(r'[\u4e00-\u9fff]', detected_text))
                    if not has_chinese and len(detected_text) < 4:
                        detected_text = ""

            if detected_text:
                if not current_text:
                    current_text = detected_text
                    current_start_time = current_time_sec
                    last_detected_time = current_time_sec
                    # Bắt đầu câu mới -> log ra UI
                    if text_callback:
                        h = int(current_time_sec // 3600)
                        m = int((current_time_sec % 3600) // 60)
                        s = int(current_time_sec % 60)
                        text_callback(f"[{h:02d}:{m:02d}:{s:02d}] {detected_text}")
                else:
                    if similar(current_text, detected_text) > 0.7:
                        last_detected_time = current_time_sec
                        if len(detected_text) > len(current_text):
                            current_text = detected_text
                    else:
                        if last_detected_time - current_start_time >= 0.2:
                            subs.append({
                                'text': current_text,
                                'start': current_start_time,
                                'end': last_detected_time + 0.3
                            })
                        current_text = detected_text
                        current_start_time = current_time_sec
                        last_detected_time = current_time_sec
                        # Câu mới khác câu cũ -> log ra UI
                        if text_callback:
                            h = int(current_time_sec // 3600)
                            m = int((current_time_sec % 3600) // 60)
                            s = int(current_time_sec % 60)
                            text_callback(f"[{h:02d}:{m:02d}:{s:02d}] {detected_text}")
            else:
                if current_text:
                    if last_detected_time - current_start_time >= 0.2:
                        subs.append({
                            'text': current_text,
                            'start': current_start_time,
                            'end': last_detected_time + 0.3
                        })
                    current_text = ""

            processed_count += 1
            # Cập nhật tiến trình
            if progress_callback and frame_idx % (process_interval * 30) == 0:
                progress_callback(min(frame_idx / total_frames, 0.99))
            if log_callback and processed_count % 200 == 0:
                pct = frame_idx / total_frames * 100
                log_callback(f"   [{pct:.1f}%] Đã quét {processed_count} frame | Tìm được {len(subs)} dòng phụ đề...")

        frame_idx += 1

    cap.release()

    # Lưu câu cuối nếu video kết thúc đột ngột
    if current_text and (last_detected_time - current_start_time >= 0.2):
        subs.append({
            'text': current_text,
            'start': current_start_time,
            'end': last_detected_time + 0.3
        })

    # --- LƯU RA FILE SRT ---
    srt_file = pysrt.SubRipFile()
    for i, sub in enumerate(subs):
        item = pysrt.SubRipItem(
            index=i+1,
            start=pysrt.SubRipTime(milliseconds=int(sub['start']*1000)),
            end=pysrt.SubRipTime(milliseconds=int(sub['end']*1000)),
            text=sub['text']
        )
        srt_file.append(item)

    srt_file.save(output_srt, encoding='utf-8')
    if progress_callback: progress_callback(1.0)
    if log_callback: log_callback(f"HOÀN TẤT! Đã cào được tổng cộng {len(subs)} dòng phụ đề.")
    if log_callback: log_callback(f"Đã lưu SRT tại: {output_srt}")
    return True

if __name__ == "__main__":
    import sys
    if len(sys.argv) > 2:
        extract_subtitles_from_video(sys.argv[1], sys.argv[2], print)
