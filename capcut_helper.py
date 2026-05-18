"""
capcut_helper.py — Wrapper cho CapCutAPI (ashreo/CapCutAPI)
Dùng cho Tab 7: Tạo CapCut Draft tự động với:
  - Video sạch từ Tab 5
  - SRT Việt từ Tab 1
  - Nhạc nền từ Tab 2
  - Zoom keyframes theo nhịp nhạc (librosa beat detection)
  - Style sub: Bo Bắp Media (tu tiên / kiếm hiệp / xuyên không)
"""

import os
import sys
import time
import random
import subprocess
import requests

CAPCUT_API_PORT  = 9000   # Port mặc định của ashreo/CapCutAPI (settings/local.py)
CAPCUT_API_URL   = f"http://localhost:{CAPCUT_API_PORT}"

# ─── Style Sub — Bo Bắp Media ─────────────────────────────────────────────────
# Phong cách: cổ trang / kiếm hiệp / dễ thương + dễ đọc trên mobile
BOBAP_SUB_STYLE = {
    "font_color":       "#FFF8E7",  # Kem vàng ấm — gợi cảm giác cổ trang
    "font_size":        6.0,        # Theo yêu cầu user
    "bold":             True,
    "italic":           False,
    "underline":        False,

    # Viền nâu sậm thay vì đen — hợp phong cách kiếm hiệp hơn
    "border_color":     "#3D1A00",
    "border_width":     12.0,
    "border_alpha":     1.0,

    # Nền nâu đen mờ — không che hình quá nhiều
    "background_color": "#1A0A00",
    "background_alpha": 0.55,
    "background_style": 1,

    # Vị trí: căn giữa, cách đáy ~12.5% (transform_y = 0.75 trong tọa độ [-1,1])
    "transform_x":      0.0,
    "transform_y":      -0.75,

    # Scale 130% theo yêu cầu user
    "scale_x":          1.3,
    "scale_y":          1.3,

    "alpha":            1.0,
    "vertical":         False,
    "track_name":       "bobap_vi_subtitle",
}


# ─── CapCut Draft Folder Detection ────────────────────────────────────────────

def get_capcut_draft_dir():
    """
    Tự động tìm thư mục Draft CapCut trên Windows.
    Trả về đường dẫn nếu tìm thấy, None nếu không.
    """
    userprofile = os.environ.get("USERPROFILE", os.path.expanduser("~"))
    candidates = [
        # CapCut International (Windows)
        os.path.join(userprofile, "AppData", "Local", "CapCut",
                     "User Data", "Projects", "com.lemon.lvideo-pc", "default"),
        # CapCut International (Alternative path found)
        os.path.join(userprofile, "AppData", "Local", "CapCut",
                     "User Data", "Projects", "com.lveditor.draft"),
        # CapCut older path
        os.path.join(userprofile, "Documents", "CapCut",
                     "User Data", "Projects", "com.lemon.lvideo-pc", "default"),
        # JianYing (China version) — phòng hờ
        os.path.join(userprofile, "AppData", "Local", "JianyingPro",
                     "User Data", "Projects", "com.lveditor.draft"),
    ]
    for d in candidates:
        if os.path.isdir(d):
            return d
    return None


# ─── CapCutAPI Server Manager ─────────────────────────────────────────────────

_server_proc = None

def start_capcut_server(capcut_api_dir, log_callback=None):
    """
    Khởi động CapCutAPI Flask server dưới dạng subprocess.
    Chờ tối đa 20 giây cho đến khi server sẵn sàng.
    """
    global _server_proc

    server_script = os.path.join(capcut_api_dir, "capcut_server.py")
    if not os.path.exists(server_script):
        raise FileNotFoundError(
            f"Không tìm thấy CapCutAPI server tại: {server_script}\n"
            f"Hãy đảm bảo đã clone repo vào {capcut_api_dir}"
        )

    if log_callback:
        log_callback(f"   → Đang khởi động CapCutAPI server (port {CAPCUT_API_PORT})...")

    _server_proc = subprocess.Popen(
        [sys.executable, server_script],
        cwd=capcut_api_dir,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        env={**os.environ, "FLASK_ENV": "production"},
    )

    # Chờ server sẵn sàng — ashreo/CapCutAPI không có /health, dùng /create_draft để probe
    for i in range(60):   # Chờ tối đa 30 giây (60 × 0.5s)
        try:
            r = requests.post(
                f"{CAPCUT_API_URL}/create_draft",
                json={"width": 100, "height": 100},
                timeout=2,
            )
            if r.status_code in (200, 400):
                if log_callback:
                    log_callback("   ✅ CapCutAPI server sẵn sàng!")
                return _server_proc
        except Exception:
            pass
        time.sleep(0.5)

    _server_proc.terminate()
    raise RuntimeError("CapCutAPI server không khởi động được sau 30 giây.")


def stop_capcut_server():
    """Dừng CapCutAPI server nếu đang chạy."""
    global _server_proc
    if _server_proc and _server_proc.poll() is None:
        _server_proc.terminate()
        _server_proc = None


# ─── HTTP Helper ──────────────────────────────────────────────────────────────

def _post(endpoint, data, timeout=120):
    """POST request đến CapCutAPI, raise nếu thất bại."""
    # ashreo/CapCutAPI không cần license_key
    r = requests.post(f"{CAPCUT_API_URL}/{endpoint}", json=data, timeout=timeout)
    r.raise_for_status()
    result = r.json()
    if not result.get("success"):
        raise RuntimeError(f"CapCutAPI [{endpoint}] lỗi: {result.get('error', result)}")
    return result["output"]


# ─── Beat Detection ───────────────────────────────────────────────────────────

def detect_beats(audio_path, log_callback=None):
    """
    Phân tích nhịp nhạc từ file audio bằng librosa.
    Trả về list thời gian (giây) của mỗi beat.
    """
    try:
        import librosa
    except ImportError:
        raise ImportError("Cần cài librosa: pip install librosa soundfile")

    if log_callback:
        log_callback(f"   🎵 Đang phân tích nhịp nhạc: {os.path.basename(audio_path)}...")

    y, sr = librosa.load(audio_path, sr=None, mono=True)
    tempo, beat_frames = librosa.beat.beat_track(y=y, sr=sr)
    
    # librosa >= 0.10 trả về tempo là numpy array thay vì scalar → cần flatten
    import numpy as np
    if isinstance(tempo, np.ndarray):
        tempo = float(tempo.flat[0])
    else:
        tempo = float(tempo)
        
    beat_times = librosa.frames_to_time(beat_frames, sr=sr).tolist()

    if log_callback:
        log_callback(f"   → Tempo: {tempo:.1f} BPM | {len(beat_times)} beat phát hiện")

    return beat_times


def generate_zoom_keyframes(beat_times, video_duration):
    """
    Tạo zoom keyframes ngẫu nhiên tại mỗi beat.
    Scale dao động nhẹ [0.97 – 1.07] để tạo cảm giác sống động.
    Trả về (times, scale_str_list) cho cả scale_x và scale_y.
    """
    zoom_pool = [1.00, 1.02, 1.03, 1.05, 1.07, 0.97, 0.98]
    times  = []
    values = []

    prev = 1.0
    for t in beat_times:
        t = round(float(t), 3)
        if t >= video_duration:
            break
        # Không lặp cùng hướng 2 lần liên tiếp
        candidates = [v for v in zoom_pool if abs(v - prev) > 0.01]
        scale = random.choice(candidates if candidates else zoom_pool)
        times.append(t)
        values.append(str(scale))
        prev = scale

    return times, values


# ─── CapCutAPI Wrappers ───────────────────────────────────────────────────────

def api_create_draft(width=1920, height=1080):
    out = _post("create_draft", {"width": width, "height": height})
    return out["draft_id"]


def api_add_video(draft_id, video_path, video_duration, width=1920, height=1080):
    out = _post("add_video", {
        "draft_id":     draft_id,
        "video_url":    video_path,
        "width":        width,
        "height":       height,
        "start":        0,
        "end":          video_duration,
        "target_start": 0,
        "track_name":   "main_video",
    })
    return out.get("draft_id", draft_id)


def api_add_audio(draft_id, audio_path, video_duration):
    out = _post("add_audio", {
        "draft_id":     draft_id,
        "audio_url":    audio_path,
        "start":        0,
        "end":          video_duration,
        "target_start": 0,
        "volume":       0.75,
        "track_name":   "bobap_bgm",
    })
    return out.get("draft_id", draft_id)


def api_add_subtitle(draft_id, srt_path, width=1920, height=1080):
    payload = {
        "draft_id": draft_id,
        "srt":      srt_path,
        "width":    width,
        "height":   height,
        **BOBAP_SUB_STYLE,
    }
    out = _post("add_subtitle", payload)
    return out.get("draft_id", draft_id)


def api_add_zoom_keyframes(draft_id, times, values):
    if not times:
        return draft_id
    # Cần tạo list property_types có cùng độ dài với times và values
    # Mỗi thời điểm t cần 2 keyframe: scale_x và scale_y
    expanded_props = []
    expanded_times = []
    expanded_vals  = []
    for t, v in zip(times, values):
        # Thêm scale_x
        expanded_props.append("scale_x")
        expanded_times.append(t)
        expanded_vals.append(v)
        # Thêm scale_y
        expanded_props.append("scale_y")
        expanded_times.append(t)
        expanded_vals.append(v)

    out = _post("add_video_keyframe", {
        "draft_id":       draft_id,
        "track_name":     "main_video",
        "property_types": expanded_props,
        "times":          expanded_times,
        "values":         expanded_vals,
    })
    return out.get("draft_id", draft_id)


def api_save_draft(draft_id, draft_folder):
    out = _post("save_draft", {
        "draft_id":     draft_id,
        "draft_folder": draft_folder,
    }, timeout=300)
    return out


# ─── Main Pipeline ────────────────────────────────────────────────────────────

def build_capcut_draft(video_path, srt_path, audio_path, draft_folder,
                       capcut_api_dir, log_callback=None, progress_callback=None):
    """
    Pipeline chính: tạo CapCut Draft từ video + SRT + nhạc nền.

    Returns: đường dẫn thư mục draft đã tạo (dfd_...) hoặc raise Exception.
    """
    import cv2

    def log(msg):
        if log_callback:
            log_callback(msg)

    def prog(v):
        if progress_callback:
            progress_callback(v)

    # ── Lấy thông tin video ──────────────────────────────────────────────────
    log("📐 Đang đọc thông tin video...")
    cap = cv2.VideoCapture(video_path)
    vid_w   = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    vid_h   = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    fps_vid = cap.get(cv2.CAP_PROP_FPS)
    n_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    cap.release()
    vid_duration = round(n_frames / fps_vid, 3) if fps_vid > 0 else 0
    log(f"   → {vid_w}x{vid_h} | {fps_vid:.1f}fps | {vid_duration:.1f}s")
    prog(0.05)

    # ── Beat detection ───────────────────────────────────────────────────────
    log("🎵 Bước 1/5: Phân tích nhịp nhạc...")
    beat_times = detect_beats(audio_path, log_callback)
    zoom_times, zoom_values = generate_zoom_keyframes(beat_times, vid_duration)
    log(f"   → Tạo {len(zoom_times)} keyframe zoom")
    prog(0.15)

    # ── Start server ─────────────────────────────────────────────────────────
    log("🚀 Bước 2/5: Khởi động CapCutAPI server...")
    proc = start_capcut_server(capcut_api_dir, log_callback)
    prog(0.20)

    try:
        # ── Create draft ─────────────────────────────────────────────────────
        log("🎬 Bước 3/5: Tạo draft CapCut...")
        draft_id = api_create_draft(width=vid_w, height=vid_h)
        log(f"   → Draft ID: {draft_id}")

        # Add video
        log("   → Thêm video chính...")
        draft_id = api_add_video(draft_id, video_path, vid_duration, vid_w, vid_h)
        prog(0.35)

        # Add BGM
        log("   → Thêm nhạc nền (75% volume)...")
        draft_id = api_add_audio(draft_id, audio_path, vid_duration)
        prog(0.50)

        # Add subtitles
        log("📝 Bước 4/5: Thêm phụ đề Việt (Bo Bắp Media style)...")
        draft_id = api_add_subtitle(draft_id, srt_path, vid_w, vid_h)
        prog(0.65)

        # Add zoom keyframes
        log("✨ Thêm hiệu ứng zoom theo nhịp nhạc...")
        draft_id = api_add_zoom_keyframes(draft_id, zoom_times, zoom_values)
        prog(0.80)

        # Save draft
        log(f"💾 Bước 5/5: Lưu draft vào CapCut...")
        log(f"   → Thư mục: {draft_folder}")
        result = api_save_draft(draft_id, draft_folder)
        prog(1.0)

        draft_path = os.path.join(draft_folder, draft_id)
        log(f"\n🎉 HOÀN TẤT! Draft đã tạo: {draft_id}")
        log(f"   → Mở CapCut → Draft của tôi → Tìm '{draft_id[:8]}...'")
        return draft_path

    finally:
        stop_capcut_server()
