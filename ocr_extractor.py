import os
import sys
import subprocess
import re
import numpy as np
from difflib import SequenceMatcher

def similar(a, b):
    return SequenceMatcher(None, a, b).ratio()


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


def _get_filtered_text(result):
    """
    Lọc kết quả OCR theo:
    1. Confidence > 0.6
    2. Phải chứa ký tự Hán
    """
    if not result:
        return ""

    texts = []
    for item in result:
        bbox, text, conf = item
        if conf <= 0.6:
            continue
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

    # --- Quét video ---
    cap            = cv2.VideoCapture(video_path)
    
    # Pass 1: Thu thập toàn bộ text
    raw_detections = []  # Lưu [{ 'text': ..., 'start': t, 'last_seen': t, 'y_bottom': ..., 'h_bbox': ... }]
    active_texts   = []  # Theo dõi text qua các frame liên tiếp

    frame_idx = 0
    processed = 0

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
            current_frame_items = []
            
            if result:
                for item in result:
                    bbox, text, conf = item
                    if conf <= 0.6: continue
                    pts = np.array(bbox, dtype=np.float32)
                    y_bottom = float(pts[:, 1].max())
                    h_bbox = float(pts[:, 1].max() - pts[:, 1].min())
                    
                    # Lọc sơ bộ: phải chứa chữ Hán hoặc dài >= 4
                    detected = re.sub(r'[a-zA-Z]', '', text).strip()
                    has_chinese = bool(re.search(r'[\u4e00-\u9fff]', detected))
                    if not has_chinese and len(detected) < 4:
                        continue
                    
                    current_frame_items.append({
                        'text': text,
                        'y_bottom': y_bottom,
                        'h_bbox': h_bbox
                    })

            # Ghép với active_texts
            for curr in current_frame_items:
                matched = False
                for active in active_texts:
                    if similar(active['text'], curr['text']) > 0.6 or curr['text'] in active['text'] or active['text'] in curr['text']:
                        # Cập nhật active
                        active['last_seen'] = t
                        if len(curr['text']) > len(active['text']):
                            active['text'] = curr['text']
                        # Cập nhật baseline trung bình mượt
                        active['y_bottom'] = (active['y_bottom'] + curr['y_bottom']) / 2.0
                        active['h_bbox'] = (active['h_bbox'] + curr['h_bbox']) / 2.0
                        matched = True
                        break
                if not matched:
                    new_item = {
                        'text': curr['text'],
                        'start': t,
                        'last_seen': t,
                        'y_bottom': curr['y_bottom'],
                        'h_bbox': curr['h_bbox']
                    }
                    active_texts.append(new_item)
                    _log_new(t, curr['text'])

            # Xóa các active_texts đã quá hạn (không xuất hiện trong 1s)
            survivors = []
            for active in active_texts:
                if t - active['last_seen'] > 1.0:
                    raw_detections.append(active)
                else:
                    survivors.append(active)
            active_texts = survivors

            processed += 1
            if progress_callback and frame_idx % (process_interval * 30) == 0:
                progress_callback(min(frame_idx / total_frames, 0.99))
            if log_callback and processed % 200 == 0:
                pct = frame_idx / total_frames * 100
                log_callback(
                    f"   [{pct:.1f}%] Đã quét {processed} frame | "
                    f"Phát hiện {len(raw_detections) + len(active_texts)} chuỗi text..."
                )

        frame_idx += 1

    cap.release()

    raw_detections.extend(active_texts)

    subs = []
    if raw_detections:
        # --- Pass 2: Phân tích Global Baseline ---
        from collections import defaultdict
        y_bins = defaultdict(float)  # bin -> total duration
        
        for item in raw_detections:
            duration = item['last_seen'] - item['start'] + 0.3
            item['duration'] = duration
            # Nhóm các Y_bottom gần nhau (làm tròn 5px)
            y_bin = round(item['y_bottom'] / 5.0) * 5
            y_bins[y_bin] += duration

        # Tọa độ Y phổ biến nhất chính là Baseline của phụ đề
        best_y_bin = max(y_bins.items(), key=lambda x: x[1])[0]

        if log_callback:
            log_callback(f"\n🔍 [Global Baseline] Phát hiện chân chữ phụ đề tại Y ≈ {best_y_bin}px")
            log_callback(f"   => Tự động vứt bỏ các text rác (hiển thị hệ thống) lệch khỏi tọa độ này.")

        # Lọc lại toàn bộ detections
        for item in raw_detections:
            y_diff = abs(item['y_bottom'] - best_y_bin)
            
            # Chấp nhận sai số Y <= 15px
            if y_diff <= 15:
                subs.append({
                    'text': item['text'],
                    'start': item['start'],
                    'end': item['last_seen'] + 0.3
                })

        # Sắp xếp theo thời gian
        subs.sort(key=lambda x: x['start'])


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
