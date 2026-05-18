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
    "font_size":        6.0,        # pyJianYingDraft đơn vị nội bộ; 6.0 theo yêu cầu user
    "bold":             True,
    "italic":           False,
    "underline":        False,

    # Viền nâu sậm — giá trị hợp lệ của pyJianYingDraft nằm trong ~0.0–8.0
    # Bug cũ: 12.0 vượt ngưỡng nên border bị bỏ qua hoàn toàn
    "border_color":     "#3D1A00",
    "border_width":     6.0,        # FIX: giảm từ 12.0 → 6.0 để border thực sự hiển thị
    "border_alpha":     1.0,

    # Nền nâu đen mờ — không che hình quá nhiều
    "background_color": "#1A0A00",
    "background_alpha": 0.55,
    "background_style": 1,

    # Vị trí: căn giữa, cách đáy ~12.5% (transform_y = -0.75 trong tọa độ [-1,1])
    "transform_x":      0.0,
    "transform_y":      -0.75,

    # Scale 130% theo yêu cầu user
    "scale_x":          1.0,
    "scale_y":          1.0,

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
    Tạo zoom keyframes tại các nhịp beat.
    Scale dao động cực nhẹ để tự nhiên, và giảm tần suất để không gây chóng mặt.
    """
    # Biên độ nhỏ lại (từ 0.99 đến 1.02) để không quá gắt
    zoom_pool = [1.00, 1.01, 1.02, 0.99]
    times  = []
    values = []

    prev = 1.0
    last_t = -10.0
    
    for t in beat_times:
        t = round(float(t), 3)
        if t >= video_duration:
            break
            
        # GIẢM TẦN SUẤT: Ít nhất 1.5 giây mới đổi scale 1 lần để xem đỡ chóng mặt
        if t - last_t < 1.5:
            continue
            
        # Random skip 30% số nhịp để hiệu ứng không lặp lại quá đều đặn
        import random
        if random.random() < 0.3:
            continue
            
        candidates = [v for v in zoom_pool if abs(v - prev) > 0.005]
        scale = random.choice(candidates if candidates else zoom_pool)
        times.append(t)
        values.append(str(scale))
        prev = scale
        last_t = t

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
        # FIX: thêm "duration" để add_video_track biết thời lượng thực của clip.
        # Nếu thiếu tham số này, video_material được tạo với duration=0.0
        # khiến CapCut chỉ phát vài giây đầu rồi màn hình đen.
        "duration":     video_duration,
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


def api_save_draft(draft_id, draft_folder, log_callback=None):
    """
    Lưu draft trực tiếp vào thư mục CapCut (local) thay vì cloud OSS.
    1. Lấy JSON content từ /query_script
    2. Copy template folder → draft_folder/<draft_name>/
    3. Ghi draft_content.json
    4. Tạo draft_meta_info.json
    5. Cập nhật root_meta_info.json → Draft hiển thị trong CapCut
    """
    import shutil, uuid, time as _time

    def log(msg):
        if log_callback:
            log_callback(msg)

    # ── 1. Lấy script JSON từ server ─────────────────────────────────────────
    log("   → Lấy nội dung draft từ server...")
    r = requests.post(f"{CAPCUT_API_URL}/query_script",
                      json={"draft_id": draft_id, "force_update": True},
                      timeout=120)
    r.raise_for_status()
    result = r.json()
    if not result.get("success"):
        raise RuntimeError(f"query_script lỗi: {result.get('error', result)}")

    script_json_str = result["output"]
    if isinstance(script_json_str, dict):
        script_content = script_json_str
    else:
        import json as _json
        script_content = _json.loads(script_json_str)

    # ── 2. Tạo thư mục draft trong CapCut ────────────────────────────────────
    draft_name = draft_id           # CapCut dùng tên thư mục làm tên draft
    draft_path = os.path.join(draft_folder, draft_name)

    # Copy template từ capcut_api/template
    template_src = os.path.join(
        os.path.dirname(os.path.abspath(__file__)),
        "capcut_api", "template"
    )
    if os.path.exists(draft_path):
        shutil.rmtree(draft_path)

    if os.path.exists(template_src):
        shutil.copytree(template_src, draft_path)
        log(f"   → Đã copy template → {draft_name}")
    else:
        os.makedirs(draft_path, exist_ok=True)
        log("   → Không có template, tạo thư mục mới")

    # ── 3. Ghi draft_content.json ─────────────────────────────────────────────
    import json as _json

    # PATCH: thay placeholder path bằng remote_url (đường dẫn local thực)
    # pyJianYingDraft lưu path = "draft/assets/video/xxx.mp4" (placeholder)
    # CapCut cần path thực để tìm file → dùng remote_url là đường dẫn gốc
    patched_videos = 0
    patched_audios = 0
    for vid in script_content.get("materials", {}).get("videos", []):
        real_path = vid.get("remote_url", "")
        if real_path and os.path.exists(real_path):
            vid["path"] = real_path.replace("/", "\\")
            patched_videos += 1
        elif not real_path:
            # Thử lấy từ replace_path nếu có
            rp = vid.get("replace_path", "")
            if rp and os.path.exists(rp):
                vid["path"] = rp

    for aud in script_content.get("materials", {}).get("audios", []):
        real_path = aud.get("remote_url", "")
        if real_path and os.path.exists(real_path):
            aud["path"] = real_path.replace("/", "\\")
            patched_audios += 1
        elif not real_path:
            rp = aud.get("replace_path", "")
            if rp and os.path.exists(rp):
                aud["path"] = rp

    log(f"   → Đã patch path: {patched_videos} video, {patched_audios} audio")

    content_path = os.path.join(draft_path, "draft_content.json")
    with open(content_path, "w", encoding="utf-8") as f:
        _json.dump(script_content, f, ensure_ascii=False, indent=None)
    log("   → Đã ghi draft_content.json")

    # ── 4. Tạo draft_meta_info.json ──────────────────────────────────────────
    now_us = int(_time.time() * 1_000_000)
    duration_us = script_content.get("duration", 0)

    # Thu thập danh sách file media từ materials
    import urllib.request as _ur
    meta_materials = [{
        "type": 0, "value": []   # video/photo
    }, {
        "type": 1, "value": []   # audio text? 
    }, {
        "type": 2, "value": []   # srt/subtitle
    }, {
        "type": 3, "value": []
    }, {
        "type": 6, "value": []
    }, {
        "type": 7, "value": []
    }, {
        "type": 8, "value": []
    }]

    # Thêm video materials
    for vid in script_content.get("materials", {}).get("videos", []):
        path = vid.get("path", "") or vid.get("replace_path", "") or vid.get("remote_url", "")
        meta_materials[0]["value"].append({
            "ai_group_type": "",
            "create_time": int(_time.time()),
            "duration": vid.get("duration", 0),
            "enter_from": 0,
            "extra_info": os.path.basename(path),
            "file_Path": path.replace("/", "\\") if path else "",
            "height": vid.get("height", 1080),
            "id": str(uuid.uuid4()).upper(),
            "import_time": int(_time.time()),
            "import_time_ms": now_us,
            "item_source": 1,
            "md5": "",
            "metetype": vid.get("type", "video"),
            "roughcut_time_range": {"duration": vid.get("duration", 0), "start": 0},
            "sub_time_range": {"duration": -1, "start": -1},
            "type": 0,
            "width": vid.get("width", 1920)
        })

    # Thêm audio materials
    for aud in script_content.get("materials", {}).get("audios", []):
        path = aud.get("path", "") or aud.get("replace_path", "") or aud.get("remote_url", "")
        meta_materials[0]["value"].append({
            "ai_group_type": "",
            "create_time": int(_time.time()),
            "duration": aud.get("duration", 0),
            "enter_from": 0,
            "extra_info": os.path.basename(path),
            "file_Path": path.replace("/", "\\") if path else "",
            "height": 0,
            "id": str(uuid.uuid4()).upper(),
            "import_time": int(_time.time()),
            "import_time_ms": now_us,
            "item_source": 1,
            "md5": "",
            "metetype": "music",
            "roughcut_time_range": {"duration": aud.get("duration", 0), "start": 0},
            "sub_time_range": {"duration": -1, "start": -1},
            "type": 0,
            "width": 0
        })

    draft_fold_path = draft_path.replace("\\", "/")
    draft_root_path = draft_folder.replace("\\", "/")
    meta = {
        "cloud_draft_cover": False,
        "cloud_draft_sync": False,
        "cloud_package_completed_time": "",
        "draft_cloud_capcut_purchase_info": "",
        "draft_cloud_last_action_download": False,
        "draft_cloud_package_type": "",
        "draft_cloud_purchase_info": "",
        "draft_cloud_template_id": "",
        "draft_cloud_tutorial_info": "",
        "draft_cloud_videocut_purchase_info": "",
        "draft_cover": "draft_cover.jpg",
        "draft_deeplink_url": "",
        "draft_enterprise_info": {
            "draft_enterprise_extra": "",
            "draft_enterprise_id": "",
            "draft_enterprise_name": "",
            "enterprise_material": []
        },
        "draft_fold_path": draft_fold_path,
        "draft_id": str(uuid.uuid4()).upper(),
        "draft_is_ae_produce": False,
        "draft_is_ai_packaging_used": False,
        "draft_is_ai_shorts": False,
        "draft_is_ai_translate": False,
        "draft_is_article_video_draft": False,
        "draft_is_cloud_temp_draft": False,
        "draft_is_from_deeplink": "false",
        "draft_is_invisible": False,
        "draft_is_pippit_draft": False,
        "draft_is_web_article_video": False,
        "draft_materials": meta_materials,
        "draft_materials_copied_info": [],
        "draft_name": draft_name,
        "draft_need_rename_folder": False,
        "draft_new_version": "",
        "draft_removable_storage_device": "",
        "draft_root_path": draft_root_path,
        "draft_segment_extra_info": [],
        "draft_timeline_materials_size_": os.path.getsize(content_path),
        "draft_type": "",
        "draft_web_article_video_enter_from": "",
        "tm_draft_cloud_completed": "",
        "tm_draft_cloud_entry_id": -1,
        "tm_draft_cloud_modified": 0,
        "tm_draft_cloud_parent_entry_id": -1,
        "tm_draft_cloud_space_id": -1,
        "tm_draft_cloud_user_id": -1,
        "tm_draft_create": now_us,
        "tm_draft_modified": now_us,
        "tm_draft_removed": 0,
        "tm_duration": duration_us
    }
    meta_path = os.path.join(draft_path, "draft_meta_info.json")
    with open(meta_path, "w", encoding="utf-8") as f:
        _json.dump(meta, f, ensure_ascii=False)
    log("   → Đã ghi draft_meta_info.json")

    # ── 5. Cập nhật root_meta_info.json ──────────────────────────────────────
    root_meta_path = os.path.join(draft_folder, "root_meta_info.json")
    if os.path.exists(root_meta_path):
        with open(root_meta_path, "r", encoding="utf-8") as f:
            root_meta = _json.load(f)
    else:
        root_meta = {"all_draft_store": [], "draft_ids": 0, "root_path": draft_root_path}

    # Xoá entry cũ nếu cùng tên
    root_meta["all_draft_store"] = [
        d for d in root_meta.get("all_draft_store", [])
        if d.get("draft_fold_path", "").replace("\\", "/").split("/")[-1] != draft_name
    ]

    # Thêm entry mới ở ĐẦU danh sách (hiển thị đầu tiên)
    new_entry = {
        "cloud_draft_cover": False,
        "cloud_draft_sync": False,
        "draft_cloud_last_action_download": False,
        "draft_cloud_purchase_info": "",
        "draft_cloud_template_id": "",
        "draft_cloud_tutorial_info": "",
        "draft_cloud_videocut_purchase_info": "",
        "draft_cover": draft_fold_path + "/draft_cover.jpg",
        "draft_fold_path": draft_fold_path,
        "draft_id": meta["draft_id"],
        "draft_is_ai_shorts": False,
        "draft_is_cloud_temp_draft": False,
        "draft_is_invisible": False,
        "draft_is_web_article_video": False,
        "draft_json_file": draft_fold_path + "/draft_content.json",
        "draft_name": draft_name,
        "draft_new_version": "",
        "draft_root_path": draft_root_path,
        "draft_timeline_materials_size": os.path.getsize(content_path),
        "draft_type": "",
        "draft_web_article_video_enter_from": "",
        "streaming_edit_draft_ready": True,
        "tm_draft_cloud_completed": "",
        "tm_draft_cloud_entry_id": -1,
        "tm_draft_cloud_modified": 0,
        "tm_draft_cloud_parent_entry_id": -1,
        "tm_draft_cloud_space_id": -1,
        "tm_draft_cloud_user_id": -1,
        "tm_draft_create": now_us,
        "tm_draft_modified": now_us,
        "tm_draft_removed": 0,
        "tm_duration": duration_us
    }
    root_meta["all_draft_store"].insert(0, new_entry)
    root_meta["draft_ids"] = len(root_meta["all_draft_store"])
    root_meta["root_path"] = draft_root_path

    with open(root_meta_path, "w", encoding="utf-8") as f:
        _json.dump(root_meta, f, ensure_ascii=False)
    log(f"   → Đã đăng ký vào root_meta_info.json ({len(root_meta['all_draft_store'])} draft)")

    return {"draft_id": draft_id, "draft_path": draft_path}


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
        result = api_save_draft(draft_id, draft_folder, log_callback=log)
        prog(1.0)

        draft_path = os.path.join(draft_folder, draft_id)
        log(f"\n🎉 HOÀN TẤT! Draft đã tạo: {draft_id}")
        log(f"   → Mở CapCut → Draft của tôi → Tìm '{draft_id[:8]}...'")
        return draft_path

    finally:
        stop_capcut_server()
