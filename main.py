import customtkinter as ctk
from tkinter import filedialog, messagebox
import json
import os
import pysrt
import threading
import time
import requests
from google import genai
from google.genai import types
import yt_dlp
import subprocess
import PIL.Image
import sys

# Xac dinh thu muc goc (hoat dong ca khi chay script vao chay file .exe)
if getattr(sys, 'frozen', False):
    APP_DIR = os.path.dirname(sys.executable)
else:
    APP_DIR = os.path.dirname(os.path.abspath(__file__))

KHO_NHAC_DIR = os.path.join(APP_DIR, "Downloads", "Kho_nhac")
# Cấu hình UI cơ bản
ctk.set_appearance_mode("Dark")
ctk.set_default_color_theme("blue")

CONFIG_FILE = "config.json"
DOWNLOAD_DIR = "Downloads"

if not os.path.exists(DOWNLOAD_DIR):
    os.makedirs(DOWNLOAD_DIR)

def load_config():
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        except:
            return {}
    return {}

def save_config(data):
    with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=4)

class App(ctk.CTk):
    def __init__(self):
        super().__init__()

        self.title("AudioTool - Trợ Lý Đạo Diễn AI (Pixabay & Video Upload)")
        self.geometry("1000x750")
        
        self.config_data = load_config()
        self.gemini_api_key = self.config_data.get("gemini_api_key", "")
        self.pixabay_api_key = self.config_data.get("pixabay_api_key", "")
        
        self.loaded_subs = None
        self.translated_subs = None
        self.video_path1 = None
        self.video_path = None
        self.music_subs = None
        self.ref_image_path = None
        self.music_attributions = []

        # --- Sidebar ---
        self.sidebar_frame = ctk.CTkFrame(self, width=250, corner_radius=0)
        self.sidebar_frame.pack(side="left", fill="y")
        self.sidebar_frame.pack_propagate(False)

        self.logo_label = ctk.CTkLabel(self.sidebar_frame, text="AudioTool AI", font=ctk.CTkFont(size=20, weight="bold"))
        self.logo_label.pack(pady=20)

        # Gemini Key
        self.gemini_label = ctk.CTkLabel(self.sidebar_frame, text="Gemini API Key:")
        self.gemini_label.pack(padx=20, pady=(10, 0), anchor="w")
        self.gemini_entry = ctk.CTkEntry(self.sidebar_frame, show="*")
        self.gemini_entry.pack(padx=20, pady=5, fill="x")
        if self.gemini_api_key:
            self.gemini_entry.insert(0, self.gemini_api_key)
            
        # Pixabay Key
        self.pixabay_label = ctk.CTkLabel(self.sidebar_frame, text="Pixabay API Key:")
        self.pixabay_label.pack(padx=20, pady=(10, 0), anchor="w")
        self.pixabay_entry = ctk.CTkEntry(self.sidebar_frame, show="*")
        self.pixabay_entry.pack(padx=20, pady=5, fill="x")
        if self.pixabay_api_key:
            self.pixabay_entry.insert(0, self.pixabay_api_key)
        
        self.save_api_btn = ctk.CTkButton(self.sidebar_frame, text="Lưu Các Key", command=self.save_keys)
        self.save_api_btn.pack(padx=20, pady=20, fill="x")

        # --- Main Content (Tabs) ---
        self.tabview = ctk.CTkTabview(self)
        self.tabview.pack(side="right", fill="both", expand=True, padx=20, pady=20)

        self.tab1 = self.tabview.add("Dịch Phụ Đề")
        self.tab2 = self.tabview.add("Gợi Ý & Tải Nhạc")
        self.tab3 = self.tabview.add("SEO & Thumbnail")
        self.tab4 = self.tabview.add("Tạo Intro 30s")
        self.tab5 = self.tabview.add("Cào Phụ Đề (OCR)")
        self.tab6 = self.tabview.add("Tải Video")
        self.tab7 = self.tabview.add("CapCut Reup")

        self.setup_tab1()
        self.setup_tab2()
        self.setup_tab3()
        self.setup_tab4()
        self.setup_tab5()
        self.setup_tab6()
        self.setup_tab7()

    def save_keys(self):
        gk = self.gemini_entry.get()
        pk = self.pixabay_entry.get()
        self.config_data["gemini_api_key"] = gk
        self.config_data["pixabay_api_key"] = pk
        save_config(self.config_data)
        self.gemini_api_key = gk
        self.pixabay_api_key = pk
        messagebox.showinfo("Thành công", "Đã lưu cấu hình API Keys!")

    # ================= TAB 1: DỊCH THUẬT =================
    def setup_tab1(self):
        self.btn_frame = ctk.CTkFrame(self.tab1, fg_color="transparent")
        self.btn_frame.pack(fill="x", pady=10)

        self.btn_load_srt = ctk.CTkButton(self.btn_frame, text="1. Chọn SRT TQ", command=self.load_srt)
        self.btn_load_srt.pack(side="left", padx=5)

        self.btn_load_vid1 = ctk.CTkButton(self.btn_frame, text="1.5. Chọn Media (Tùy chọn)", command=self.load_media1)
        self.btn_load_vid1.pack(side="left", padx=5)

        self.vid_lbl1 = ctk.CTkLabel(self.btn_frame, text="")
        self.vid_lbl1.pack(side="left", padx=5)

        self.btn_translate = ctk.CTkButton(self.btn_frame, text="2. Bắt đầu Dịch", command=self.start_translation, state="disabled")
        self.btn_translate.pack(side="left", padx=5)

        self.btn_save_srt = ctk.CTkButton(self.btn_frame, text="3. Lưu SRT Tiếng Việt", command=self.save_srt, state="disabled")
        self.btn_save_srt.pack(side="right", padx=5)

        self.status_label = ctk.CTkLabel(self.tab1, text="Trạng thái: Đang chờ...")
        self.status_label.pack(anchor="w", pady=5)
        
        self.progress_bar = ctk.CTkProgressBar(self.tab1)
        self.progress_bar.pack(fill="x", pady=5)
        self.progress_bar.set(0)

        self.table_frame = ctk.CTkScrollableFrame(self.tab1)
        self.table_frame.pack(fill="both", expand=True, pady=10)

        hdr = ctk.CTkFrame(self.table_frame, corner_radius=0)
        hdr.pack(fill="x")
        ctk.CTkLabel(hdr, text="ID", width=40).pack(side="left")
        ctk.CTkLabel(hdr, text="Thời gian", width=120).pack(side="left")
        ctk.CTkLabel(hdr, text="Tiếng Trung", width=250, anchor="w").pack(side="left", padx=10)
        ctk.CTkLabel(hdr, text="Tiếng Việt", width=250, anchor="w").pack(side="left", padx=10)

        self.rows_frame = ctk.CTkFrame(self.table_frame, fg_color="transparent")
        self.rows_frame.pack(fill="both", expand=True)
        self.translation_widgets = {} # Map index to string var
        
        # Pagination variables and UI
        self.current_page1 = 0
        self.items_per_page1 = 50
        
        self.pagination_frame = ctk.CTkFrame(self.tab1, fg_color="transparent")
        self.pagination_frame.pack(fill="x", pady=5)
        
        self.btn_prev_page1 = ctk.CTkButton(self.pagination_frame, text="< Trang trước", width=100, command=self.prev_page1, state="disabled")
        self.btn_prev_page1.pack(side="left", padx=20)
        
        self.lbl_page1 = ctk.CTkLabel(self.pagination_frame, text="Trang 1 / 1")
        self.lbl_page1.pack(side="left", expand=True)
        
        self.btn_next_page1 = ctk.CTkButton(self.pagination_frame, text="Trang sau >", width=100, command=self.next_page1, state="disabled")
        self.btn_next_page1.pack(side="right", padx=20)

    def load_srt(self):
        file_path = filedialog.askopenfilename(filetypes=[("SRT Files", "*.srt")])
        if file_path:
            try:
                self.current_srt_file_path = file_path
                self.edited_by_phase2 = set()
                self.loaded_subs = pysrt.open(file_path)
                self.translated_subs = pysrt.open(file_path) 
                self.render_srt_table()
                self.btn_translate.configure(state="normal")
                self.status_label.configure(text=f"Đã tải {len(self.loaded_subs)} dòng. Sẵn sàng dịch.")
            except Exception as e:
                messagebox.showerror("Lỗi", f"Không thể đọc file SRT:\n{str(e)}")

    def load_media1(self):
        path = filedialog.askopenfilename(filetypes=[("Media Files", "*.mp4 *.avi *.mkv *.mp3 *.wav")])
        if path:
            self.video_path1 = path
            self.vid_lbl1.configure(text=os.path.basename(path))

    def prev_page1(self):
        if self.current_page1 > 0:
            self.current_page1 -= 1
            self.render_srt_table()

    def next_page1(self):
        total_pages = (len(self.loaded_subs) + self.items_per_page1 - 1) // self.items_per_page1
        if self.current_page1 < total_pages - 1:
            self.current_page1 += 1
            self.render_srt_table()

    def render_srt_table(self):
        for widget in self.rows_frame.winfo_children():
            widget.destroy()
        # Keep translation_widgets dictionary so we can update them in real-time, just clear the UI widgets mapping
        self.translation_widgets.clear()

        total_items = len(self.loaded_subs)
        total_pages = max(1, (total_items + self.items_per_page1 - 1) // self.items_per_page1)
        
        self.lbl_page1.configure(text=f"Trang {self.current_page1 + 1} / {total_pages}")
        self.btn_prev_page1.configure(state="normal" if self.current_page1 > 0 else "disabled")
        self.btn_next_page1.configure(state="normal" if self.current_page1 < total_pages - 1 else "disabled")

        start_idx = self.current_page1 * self.items_per_page1
        end_idx = min(start_idx + self.items_per_page1, total_items)

        for i in range(start_idx, end_idx):
            sub = self.loaded_subs[i]
            row = ctk.CTkFrame(self.rows_frame, corner_radius=0, fg_color=("gray80", "gray20") if i % 2 == 0 else "transparent")
            row.pack(fill="x", pady=1)

            ctk.CTkLabel(row, text=str(sub.index), width=40).pack(side="left")
            time_str = f"{sub.start.to_time().strftime('%H:%M:%S')} -> {sub.end.to_time().strftime('%H:%M:%S')}"
            ctk.CTkLabel(row, text=time_str, width=120).pack(side="left")
            
            src_lbl = ctk.CTkLabel(row, text=sub.text.replace("\n", " ")[:40]+"...", width=250, anchor="w")
            src_lbl.pack(side="left", padx=10)
            
            # Khởi tạo giá trị dịch hiện tại
            current_translated_text = self.translated_subs[i].text if i < len(self.translated_subs) else "..."
            var = ctk.StringVar(value=current_translated_text)
            
            # Cập nhật ngược lại object khi người dùng gõ phím
            def on_edit(*args, idx=i, v=var):
                if idx < len(self.translated_subs):
                    self.translated_subs[idx].text = v.get()
                    
            var.trace_add("write", on_edit)
            
            is_edited = hasattr(self, 'edited_by_phase2') and i in self.edited_by_phase2
            text_color = "#00FF00" if is_edited else "yellow"
            tgt_entry = ctk.CTkEntry(row, textvariable=var, width=250, text_color=text_color)
            tgt_entry.pack(side="left", padx=10, fill="x", expand=True)
            self.translation_widgets[i] = {"var": var, "entry": tgt_entry}

    def start_translation(self):
        if not self.gemini_api_key:
            messagebox.showwarning("Cảnh báo", "Vui lòng lưu Gemini API Key!")
            return
        
        self.btn_translate.configure(state="disabled")
        self.btn_load_srt.configure(state="disabled")
        threading.Thread(target=self.process_translation, daemon=True).start()

    def process_translation(self):
        uploaded_file = None
        try:
            client = genai.Client(api_key=self.gemini_api_key)
            
            if self.video_path1:
                self.status_label.configure(text="Đang nén âm thanh để tải lên siêu tốc...")
                import tempfile
                temp_dir = tempfile.gettempdir()
                compressed_audio = os.path.join(temp_dir, "temp_gemini_audio.mp3")
                try:
                    cmd = ["ffmpeg", "-y", "-i", self.video_path1, "-vn", "-ac", "1", "-b:a", "16k", compressed_audio]
                    subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, creationflags=subprocess.CREATE_NO_WINDOW)
                    upload_target = compressed_audio if os.path.exists(compressed_audio) else self.video_path1
                except:
                    upload_target = self.video_path1

                self.status_label.configure(text="Đang tải Media lên Gemini (Bản nén nhẹ)...")
                uploaded_file = client.files.upload(file=upload_target)
                
                self.status_label.configure(text="Đang chờ Google xử lý âm thanh...")
                wait_time = 0
                while uploaded_file.state.name == "PROCESSING":
                    if wait_time > 600: # 10 phút timeout
                        raise Exception("Lỗi: Quá thời gian chờ Google xử lý âm thanh (10 phút).")
                    time.sleep(5)
                    wait_time += 5
                    uploaded_file = client.files.get(name=uploaded_file.name)
                
                if uploaded_file.state.name == "FAILED":
                    raise Exception("Lỗi: Google không thể xử lý video/audio này.")

            texts = [sub.text.replace("\n", " ") for sub in self.loaded_subs]
            batch_size = 150 # Tăng batch size để giảm số lượng request
            total_batches = (len(texts) + batch_size - 1) // batch_size
            
            translated_results = [""] * len(texts)
            
            # Sử dụng các model cao cấp và thông minh hơn để dịch chuẩn (thay vì flash-lite)
            models_to_try = ['gemini-2.5-flash', 'gemini-2.5-pro', 'gemini-2.0-flash']
            
            import concurrent.futures
            
            def translate_batch(batch_idx):
                start_idx = batch_idx * batch_size
                end_idx = min(start_idx + batch_size, len(texts))
                batch = texts[start_idx:end_idx]
                
                prompt = f"""
Bạn là một dịch giả phim truyền hình chuyên nghiệp. Nhiệm vụ của bạn là dịch các câu phụ đề phim từ Tiếng Trung sang Tiếng Việt.
YÊU CẦU QUAN TRỌNG:
- Giữ nguyên ngữ cảnh phim cổ trang, kiếm hiệp, ngôn tình.
- Chú ý giới tính: Khi thấy chữ 奴才 / 奴婢 / 我, hãy tự phân tích ngữ cảnh để dịch ĐỒNG NHẤT là "nô tài" (nếu là nam/thái giám) hoặc "nô tỳ" (nếu là nữ/nha hoàn). TUYỆT ĐỐI không dịch lộn xộn lúc thì nô tài, lúc thì nô tỳ cho cùng 1 nhân vật hoặc bối cảnh.
- Sử dụng chính xác các từ xưng hô cổ trang như: công tử, tại hạ, huynh đài, muội muội...
- Dịch mượt mà, tự nhiên như phim lồng tiếng chuyên nghiệp.
- Tên nhân vật phải được THỐNG NHẤT xuyên suốt. BẮT BUỘC viết Hoa chữ cái đầu của mỗi âm tiết trong tên người (Ví dụ: Tiêu Viêm, Đường Tam, Hàn Lập...). Không được viết thường tên riêng.

Đầu vào là mảng JSON các câu cần dịch:
{json.dumps(batch, ensure_ascii=False)}
"""         
                if uploaded_file:
                    prompt += "\nLƯU Ý ĐẶC BIỆT: HÃY NGHE FILE MEDIA ĐÍNH KÈM! Hãy chú ý các mốc thời gian (timestamp) của từng câu phụ đề để nghe giọng nói thực tế. Nếu giọng nam xưng 奴才 thì phải dịch là 'nô tài', nếu giọng nữ xưng 奴婢/奴才 thì phải dịch là 'nô tỳ'. Việc nghe âm thanh là BẮT BUỘC để phân biệt giới tính!"

                contents_to_send = [uploaded_file, prompt] if uploaded_file else prompt
                
                for attempt in range(4): # Thử tối đa 4 lần nếu bị rate limit
                    for model_name in models_to_try:
                        try:
                            response = client.models.generate_content(
                                model=model_name,
                                contents=contents_to_send,
                                config=types.GenerateContentConfig(
                                    response_mime_type="application/json",
                                    response_schema={"type": "ARRAY", "items": {"type": "STRING"}}
                                )
                            )
                            res_json = json.loads(response.text)
                            return batch_idx, res_json, None
                        except Exception as e:
                            err_str = str(e)
                            if "429" in err_str or "RESOURCE_EXHAUSTED" in err_str:
                                time.sleep(15) # Nghỉ 15s nếu dính limit
                                continue
                            elif "503" in err_str or "UNAVAILABLE" in err_str:
                                time.sleep(5)
                                continue
                return batch_idx, ["[Lỗi Dịch]"] * len(batch), "Failed"

            completed_batches = 0
            
            # Xử lý đa luồng để tăng tốc độ dịch lên gấp nhiều lần
            with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
                futures = [executor.submit(translate_batch, i) for i in range(total_batches)]
                for future in concurrent.futures.as_completed(futures):
                    b_idx, res_json, err = future.result()
                    
                    start_idx = b_idx * batch_size
                    for j, text in enumerate(res_json):
                        idx = start_idx + j
                        if idx < len(translated_results):
                            translated_results[idx] = text
                            if idx < len(self.translated_subs):
                                self.translated_subs[idx].text = text
                    
                    completed_batches += 1
                    def update_ui(c=completed_batches):
                        self.status_label.configure(text=f"Đang dịch đoạn {c}/{total_batches}...")
                        self.progress_bar.set(c / total_batches * 0.8)
                    self.after(0, update_ui)
                    self.after(0, self.update_visible_translations)
            
            # PHASE 2: REVIEW Toàn bộ kịch bản
            self.status_label.configure(text="Giai đoạn 2: Đang rà soát toàn bộ xưng hô và tên nhân vật...")
            self.progress_bar.set(0.85)
            
            review_input = [{"id": idx, "zh": self.loaded_subs[idx].text.replace('\n', ' '), "vi": txt} for idx, txt in enumerate(translated_results)]
            
            review_prompt = f"""
Đọc kỹ toàn bộ kịch bản phim cổ trang (kèm nguyên tác Tiếng Trung) dưới đây.
Nhiệm vụ: Phát hiện và sửa lại các câu Tiếng Việt bị dịch sai lệch xưng hô (đặc biệt: lúc xưng "nô tài" lúc xưng "nô tỳ" lung tung, hoặc xưng hô không nhất quán) hoặc tên nhân vật bị viết sai/chưa đồng nhất.
Hãy dựa vào bối cảnh chung để CHUẨN HÓA lại MỘT CÁCH XƯNG HÔ DUY NHẤT cho cùng một người/nhóm người. (Ví dụ: Nếu bối cảnh là cung nữ/nha hoàn đang nói, phải thống nhất sửa hết thành "nô tỳ", không để lộn xộn với "nô tài").
Hãy đảm bảo giữ nguyên văn phong cổ trang.

CHỈ TRẢ VỀ một mảng JSON chứa các câu CẦN SỬA, tuyệt đối không trả về các câu đúng.
Định dạng bắt buộc:
[
  {{"id": 15, "text": "Phu quân, chàng đi đâu vậy?"}},
  {{"id": 89, "text": "Tiêu Viêm ca ca, huynh cẩn thận!"}}
]
Nếu không có câu nào sai, trả về mảng rỗng [].

Kịch bản:
{json.dumps(review_input, ensure_ascii=False)}
"""
        
            review_response = None
            models_to_try_phase2 = ['gemini-2.5-flash', 'gemini-2.5-pro', 'gemini-2.0-flash']
            
            # Khử file media ở Phase 2 để tránh nặng server và lỗi Timeout
            review_contents_to_send = review_prompt
            
            while not review_response:
                for model_name in models_to_try_phase2:
                    try:
                        review_response = client.models.generate_content(
                            model=model_name,
                            contents=review_contents_to_send,
                            config=types.GenerateContentConfig(
                                response_mime_type="application/json",
                                response_schema={"type": "ARRAY", "items": {"type": "OBJECT", "properties": {"id": {"type": "INTEGER"}, "text": {"type": "STRING"}}}}
                            )
                        )
                        break
                    except Exception as e:
                        err_str = str(e)
                        if "429" in err_str or "RESOURCE_EXHAUSTED" in err_str:
                            print(f"Lỗi 429 ({model_name}): Đổi model...")
                            continue
                        elif "503" in err_str or "UNAVAILABLE" in err_str:
                            print(f"Lỗi 503 ({model_name}): Server bận, đổi model...")
                            time.sleep(5)
                            continue
                        else:
                            print(f"Lỗi ({model_name}): {err_str}")
                            continue
                
                if not review_response:
                    print("Tất cả model đều lỗi ở Phase 2. Ngủ đông 60s...")
                    self.status_label.configure(text="Tất cả model lỗi. Ngủ đông 60s trước khi thử lại Review...")
                    time.sleep(60)
            
            if review_response:
                try:
                    corrections = json.loads(review_response.text)
                    for correction in corrections:
                        idx = correction.get("id")
                        new_text = correction.get("text")
                        if idx is not None and new_text and 0 <= idx < len(translated_results):
                            translated_results[idx] = new_text
                            if idx < len(self.translated_subs):
                                self.translated_subs[idx].text = new_text
                                self.edited_by_phase2.add(idx)
                                
                    self.after(0, self.update_visible_translations)
                except Exception as e:
                    print("Lỗi parse review JSON:", e)

            self.status_label.configure(text="Dịch và Kiểm duyệt hoàn tất!")
            self.progress_bar.set(1.0)
            self.btn_save_srt.configure(state="normal")
            
        except Exception as e:
            self.status_label.configure(text="Có lỗi xảy ra trong quá trình dịch.")
            messagebox.showerror("Lỗi Dịch", str(e))
        finally:
            if uploaded_file:
                try:
                    client.files.delete(name=uploaded_file.name)
                except:
                    pass
            self.btn_translate.configure(state="normal")
            self.btn_load_srt.configure(state="normal")

    def update_visible_translations(self):
        # Update các ô Entry đang hiển thị trên trang hiện tại nếu có kết quả mới
        for idx, widget_data in self.translation_widgets.items():
            if idx < len(self.translated_subs):
                var = widget_data["var"]
                entry = widget_data["entry"]
                if var.get() != self.translated_subs[idx].text:
                    var.set(self.translated_subs[idx].text)
                if hasattr(self, 'edited_by_phase2') and idx in self.edited_by_phase2:
                    entry.configure(text_color="#00FF00")

    def save_srt(self):
        default_name = "translated.srt"
        if hasattr(self, 'current_srt_file_path') and self.current_srt_file_path:
            base, ext = os.path.splitext(os.path.basename(self.current_srt_file_path))
            default_name = f"{base}_translate{ext}"

        file_path = filedialog.asksaveasfilename(
            initialfile=default_name,
            defaultextension=".srt", 
            filetypes=[("SRT Files", "*.srt")]
        )
        if file_path and self.translated_subs:
            self.translated_subs.save(file_path, encoding='utf-8')
            messagebox.showinfo("Thành công", "Đã lưu file Tiếng Việt!")

    # ================= TAB 2: GỢI Ý & TẢI NHẠC =================
    def setup_tab2(self):
        self.btn_frame2 = ctk.CTkFrame(self.tab2, fg_color="transparent")
        self.btn_frame2.pack(fill="x", pady=10)

        self.btn_load_srt2 = ctk.CTkButton(self.btn_frame2, text="1. Chọn Phụ Đề Tiếng Việt", command=self.load_srt2)
        self.btn_load_srt2.pack(side="left", padx=5)

        self.btn_load_vid = ctk.CTkButton(self.btn_frame2, text="2. Chọn Video/Audio Gốc", command=self.load_video)
        self.btn_load_vid.pack(side="left", padx=5)

        self.vid_lbl = ctk.CTkLabel(self.btn_frame2, text="Chưa chọn file")
        self.vid_lbl.pack(side="left", padx=5)

        self.btn_suggest = ctk.CTkButton(self.tab2, text="3. Phân tích Video & Tải Nhạc", command=self.start_music_pipeline)
        self.btn_suggest.pack(pady=10)

        self.status_label2 = ctk.CTkLabel(self.tab2, text="Sẵn sàng.")
        self.status_label2.pack(anchor="w", pady=5)

        self.progress_bar2 = ctk.CTkProgressBar(self.tab2)
        self.progress_bar2.pack(fill="x", pady=5)
        self.progress_bar2.set(0)

        self.result_textbox = ctk.CTkTextbox(self.tab2, wrap="word", font=ctk.CTkFont(size=13))
        self.result_textbox.pack(fill="both", expand=True, pady=10)
        
        self.music_subs = None

    def load_srt2(self):
        path = filedialog.askopenfilename(filetypes=[("SRT Files", "*.srt")])
        if path:
            try:
                self.music_subs = pysrt.open(path)
                messagebox.showinfo("Thành công", f"Đã tải SRT Tiếng Việt với {len(self.music_subs)} dòng.")
            except Exception as e:
                messagebox.showerror("Lỗi", f"Không thể đọc file SRT:\n{str(e)}")

    def load_video(self):
        path = filedialog.askopenfilename(filetypes=[("Media Files", "*.mp4 *.avi *.mkv *.mp3 *.wav")])
        if path:
            self.video_path = path
            self.vid_lbl.configure(text=os.path.basename(path))

    def start_music_pipeline(self):
        subs_to_use = self.music_subs if self.music_subs else self.translated_subs
        
        if not subs_to_use:
            messagebox.showwarning("Cảnh báo", "Vui lòng Chọn Phụ Đề Tiếng Việt (hoặc dịch ở Tab 1 trước)!")
            return
        if not self.video_path:
            messagebox.showwarning("Cảnh báo", "Vui lòng chọn Video!")
            return
        if not self.gemini_api_key or not self.pixabay_api_key:
            messagebox.showwarning("Cảnh báo", "Vui lòng lưu Gemini API Key và Pixabay API Key!")
            return
            
        self.btn_suggest.configure(state="disabled")
        self.result_textbox.delete("1.0", "end")
        self.music_attributions = []
        threading.Thread(target=self.process_music_pipeline, daemon=True).start()

    def append_log(self, text):
        self.result_textbox.insert("end", text + "\n")
        self.result_textbox.see("end")

    def process_music_pipeline(self):
        try:
            # SỬA LỖI CODE: Lỗi 1s deadline là do thư viện Python hiểu `600.0` là mili-giây (0.6 giây) chứ không phải giây!
            # Xóa sạch cài đặt timeout thủ công, dùng cấu hình vô cực mặc định của Google để nó tự do "suy nghĩ".
            client = genai.Client(api_key=self.gemini_api_key)
            
            # 1. EXTRACT MP3 AND UPLOAD
            self.status_label2.configure(text="Đang bóc tách Âm thanh (Sẽ nhanh thôi)...")
            self.progress_bar2.set(0.05)
            self.append_log("[1/4] Đang trích xuất MP3 để giảm tải cho AI...")
            
            import tempfile, shutil, subprocess, time, os
            safe_ascii_name = f"gemini_upload_temp_{int(time.time())}.mp3"
            ascii_safe_path = os.path.join(os.path.dirname(self.video_path), safe_ascii_name)
            
            uploaded_file = None
            try:
                # Nếu file gốc đã là audio thì copy sang, còn nếu là video thì tách MP3
                if self.video_path.lower().endswith(('.mp3', '.wav', '.m4a')):
                    try:
                        os.link(self.video_path, ascii_safe_path)
                    except:
                        shutil.copy2(self.video_path, ascii_safe_path)
                else:
                    cmd = [
                        "ffmpeg", "-y", "-i", self.video_path,
                        "-vn", "-acodec", "libmp3lame", "-ab", "64k",
                        ascii_safe_path
                    ]
                    # creationflags=subprocess.CREATE_NO_WINDOW (0x08000000)
                    subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, creationflags=0x08000000)
                
                if not os.path.exists(ascii_safe_path):
                    raise Exception("Lỗi khi dùng FFmpeg để tách MP3.")

                self.append_log("   -> Tách MP3 xong. Đang tải lên Gemini...")
                self.status_label2.configure(text="Đang tải Audio lên Gemini...")
                self.progress_bar2.set(0.1)
                
                uploaded_file = client.files.upload(file=ascii_safe_path)
            finally:
                try:
                    if os.path.exists(ascii_safe_path):
                        os.remove(ascii_safe_path)
                except:
                    pass
            
            if not uploaded_file:
                raise Exception("Không thể tải file lên Gemini.")
                
            self.append_log(f"Đã tải lên thành công. Tên File API: {uploaded_file.name}")
            self.status_label2.configure(text="Đang chờ Google xử lý video...")
            
            # Poll state
            while uploaded_file.state.name == "PROCESSING":
                time.sleep(5)
                uploaded_file = client.files.get(name=uploaded_file.name)
            
            if uploaded_file.state.name == "FAILED":
                raise Exception("Lỗi: Google không thể xử lý video này.")
                
            self.append_log("[2/4] Video đã xử lý xong. Chuẩn bị phân tích kịch bản...")
            self.progress_bar2.set(0.4)
            
            # 2. GENERATE SCRIPT SUMMARY
            script_summary = ""
            subs_to_use = self.music_subs if self.music_subs else self.translated_subs
            
            for sub in subs_to_use:
                t_start = sub.start.to_time().strftime('%H:%M:%S')
                script_summary += f"[{t_start}] {sub.text.replace(chr(10), ' ')}\n"

            # KHÔNG truncate script_summary vì Gemini 2.5 Flash hỗ trợ tới 1-2 triệu token.
            # Điều này đảm bảo AI đọc đến tận cùng phút thứ 60 của phim.

            # Lấy danh sách thư mục cảm xúc (mood folders) từ Kho_nhac
            import glob, os
            offline_music_dir = r"E:\Tool\AudioTool\Downloads\Kho_nhac"
            mood_folders = []
            if os.path.exists(offline_music_dir):
                for item in os.listdir(offline_music_dir):
                    if os.path.isdir(os.path.join(offline_music_dir, item)):
                        mood_folders.append(item)
            
            if not mood_folders:
                mood_folders_str = "bất kỳ (bạn tự nghĩ ra)"
            else:
                mood_folders_str = ", ".join(mood_folders)

            # 3. CALL GEMINI
            self.status_label2.configure(text="Đang dùng AI phân tích cảm xúc (Dòng Flash siêu tốc)...")
            self.append_log(f"[3/4] AI đang phân tích toàn bộ file Media... (Có thể mất 2-3 phút, vui lòng kiên nhẫn)")
            
            prompt = f"""
Bạn là Đạo diễn Âm nhạc cho một video tóm tắt/kể chuyện dài. Hãy lắng nghe file Media và đọc toàn bộ kịch bản thoại dưới đây (không bỏ sót bất kỳ phút nào).
Nhiệm vụ của bạn là chia bộ phim thành các CHƯƠNG LỚN (Chỉ từ 3 đến 5 phân cảnh âm nhạc cho toàn bộ phim). 
TUYỆT ĐỐI KHÔNG chia nhỏ lắt nhắt. Mỗi phân cảnh âm nhạc phải dài ít nhất 10-20 phút, bao trùm một giai đoạn cảm xúc lớn (ví dụ: Đoạn đầu bình yên, Đoạn giữa cao trào chiến đấu, Đoạn cuối bi thương).
Với mỗi chương lớn, hãy xác định cảm xúc chủ đạo và CHỈ ĐƯỢC PHÉP phân loại vào 1 trong các thư mục cảm xúc sau đây: [{mood_folders_str}]. Hãy trả về chính xác tên thư mục đó vào trường `mood_folder`.

LƯU Ý QUAN TRỌNG: 
- Phân cảnh ĐẦU TIÊN phải bắt đầu từ "00:00:00".
- Phân cảnh CUỐI CÙNG phải có thời gian `end` (kết thúc) khớp chính xác với timestamp cuối cùng của kịch bản. Tuyệt đối không được bỏ dở kịch bản ở giữa chừng! Toàn bộ các phân cảnh cộng lại phải bằng chính xác TỔNG thời lượng của phim.
- Trường `mood_folder` phải khớp chính xác 100% với một trong các tên thư mục đã cho.

Định dạng trả về BẮT BUỘC là 1 mảng JSON (không có markdown code block), với cấu trúc:
[
  {{"start": "00:00:00", "end": "00:20:00", "desc": "Giới thiệu bối cảnh làng quê yên bình và biến cố đầu tiên", "mood_folder": "{mood_folders[0] if mood_folders else 'binhyen'}"}},
  ...
]

Kịch bản thoại (từ đầu đến cuối):
{script_summary}
"""
            response = None
            # Vì tài khoản Free bị khóa dòng Pro (Limit: 0), ta chuyển sang dùng toàn bộ dòng Flash
            models_to_try = ['gemini-3.1-flash-lite', 'gemini-2.5-flash', 'gemini-2.0-flash', 'gemini-flash-latest']
            
            for model_name in models_to_try:
                try:
                    self.append_log(f"   -> Đang gọi model {model_name}...")
                    response = client.models.generate_content(
                        model=model_name, 
                        contents=[uploaded_file, prompt],
                        config=types.GenerateContentConfig(
                            response_mime_type="application/json",
                            response_schema={"type": "ARRAY", "items": {"type": "OBJECT", "properties": {
                                "start": {"type": "STRING"},
                                "end": {"type": "STRING"},
                                "desc": {"type": "STRING"},
                                "mood_folder": {"type": "STRING"}
                            }}}
                        )
                    )
                    self.append_log(f"   -> [THÀNH CÔNG] Nhận được kết quả từ {model_name}!")
                    break
                except Exception as e:
                    err_str = str(e)
                    self.append_log(f"   -> [LỖI Model {model_name}]: {err_str[:50]}...")
                    if "429" in err_str or "RESOURCE_EXHAUSTED" in err_str:
                        self.append_log("   -> Lỗi 429: Đang chờ 60s để phục hồi API...")
                        time.sleep(60)
                    elif "503" in err_str or "UNAVAILABLE" in err_str:
                        time.sleep(5)
                    continue
            
            if not response:
                raise Exception("Tất cả các model API đều báo lỗi. Vui lòng kiểm tra lại hạn mức.")
            
            scenes = json.loads(response.text)
            self.append_log(f"Đã phân tích xong {len(scenes)} cảnh. Bắt đầu tải nhạc YouTube...")
            self.progress_bar2.set(0.7)
            
            # 4. DOWNLOAD FROM KHO NHẠC OFFLINE
            self.status_label2.configure(text="Đang lấy nhạc từ kho Offline...")
            processed_mp3s = []
            
            import glob, random
            offline_music_dir = KHO_NHAC_DIR
            
            # Tạo thư mục nếu chưa có
            if not os.path.exists(offline_music_dir):
                os.makedirs(offline_music_dir)
                
            available_music = []
            for root_dir, dirs, files in os.walk(offline_music_dir):
                for f in files:
                    if f.lower().endswith(('.mp3', '.m4a', '.wav')):
                        available_music.append(os.path.join(root_dir, f))
            
            if not available_music:
                raise Exception(f"Không tìm thấy file nhạc nào trong kho Offline ({offline_music_dir}). Vui lòng tải nhạc vào đây và thử lại!")
            
            expected_start_sec = 0
            for i, scene in enumerate(scenes):
                self.append_log(f"-> Cảnh {scene['start']} - {scene['end']}: {scene['desc']}")
                
                # Tính toán thời lượng cảnh (giây)
                def time_to_sec(t_str):
                    try:
                        p = t_str.strip().split(':')
                        return int(p[0])*3600 + int(p[1])*60 + int(p[2]) if len(p)==3 else int(p[0])*60 + int(p[1])
                    except: return 0
                
                start_sec = time_to_sec(scene.get('start', '00:00:00'))
                end_sec = time_to_sec(scene.get('end', '00:00:00'))
                
                # CƯỠNG CHẾ: Bắt AI phải nối tiếp thời gian (Tránh việc AI trả về thời gian bị chồng chéo)
                start_sec = max(start_sec, expected_start_sec)
                if end_sec <= start_sec:
                    end_sec = start_sec + 10 # Cảnh bét nhất dài 10s nếu AI lỗi
                
                target_duration = end_sec - start_sec
                expected_start_sec = end_sec # Cập nhật điểm nối cho cảnh sau
                
                # Xác định thư mục lưu trữ (Lưu vào cùng thư mục với video gốc)
                out_dir = os.path.dirname(self.video_path) if self.video_path else DOWNLOAD_DIR
                
                # Lấy nhạc theo Cảm Xúc (Mood) do AI phân tích
                chosen_mood = scene.get("mood_folder", "").strip()
                mood_music = []
                if chosen_mood and os.path.exists(os.path.join(offline_music_dir, chosen_mood)):
                    mood_dir = os.path.join(offline_music_dir, chosen_mood)
                    for f in os.listdir(mood_dir):
                        if f.lower().endswith(('.mp3', '.m4a', '.wav')):
                            mood_music.append(os.path.join(mood_dir, f))
                
                # Chọn bài hát
                if mood_music:
                    chosen_music = random.choice(mood_music)
                    video_title = os.path.basename(chosen_music)
                    self.append_log(f"   [Cảm xúc: {chosen_mood}] Chọn nhạc: {video_title[:30]}...")
                else:
                    chosen_music = random.choice(available_music)
                    video_title = os.path.basename(chosen_music)
                    self.append_log(f"   [Ngẫu nhiên] Chọn nhạc: {video_title[:30]}...")
                
                mp3_path = os.path.join(out_dir, f"Scene_{i+1}_{scene['start'].replace(':','')}-{scene['end'].replace(':','')}_Offline.mp3")
                
                try:
                    if target_duration > 0:
                        self.append_log(f"   Đang lặp & cắt nhạc cho khớp độ dài ({target_duration}s)...")
                        cmd = [
                            "ffmpeg", "-y", "-stream_loop", "-1", "-i", chosen_music,
                            "-t", str(target_duration), "-c:a", "libmp3lame", "-q:a", "2", mp3_path
                        ]
                        subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, creationflags=subprocess.CREATE_NO_WINDOW)
                        
                        if os.path.exists(mp3_path):
                            self.append_log(f"   [OK] Đã xuất file MP3 chuẩn: {video_title[:30]}...")
                            processed_mp3s.append(mp3_path)
                            self.music_attributions.append({
                                "title": video_title,
                                "url": "Kho nhạc Offline",
                                "uploader": "You"
                            })
                        else:
                            self.append_log(f"   [LỖI] FFmpeg không thể xử lý file: {video_title[:30]}")
                    else:
                        self.append_log(f"   [Bỏ qua] Cảnh có độ dài 0s.")
                except Exception as dl_e:
                    self.append_log(f"   [Lỗi Xử lý Offline]: {str(dl_e)[:40]}")
            
            # 5. TẢI NHẠC NỀN CHỐNG GẬY (30S CUỐI) VÀ VIDEO PHONG CẢNH
            self.append_log("\n[5/6] Đang lấy Nhạc nền 30s cuối và Video phong cảnh...")
            final_out_dir = os.path.dirname(self.video_path) if self.video_path else DOWNLOAD_DIR
            
            # 5.1 Lấy nhạc 30s từ kho Offline cho đoạn Outro
            self.append_log("   Đang lấy nhạc nền (30s) từ kho Offline cho đoạn Outro...")
            try:
                if available_music:
                    chosen_outro = random.choice(available_music)
                    video_title = os.path.basename(chosen_outro)
                    mp3_path = os.path.join(final_out_dir, "Scene_Outro_Offline.mp3")
                    
                    cmd = ["ffmpeg", "-y", "-stream_loop", "-1", "-i", chosen_outro, "-t", "30", "-c:a", "libmp3lame", "-q:a", "2", mp3_path]
                    subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, creationflags=subprocess.CREATE_NO_WINDOW)
                    
                    if os.path.exists(mp3_path):
                        processed_mp3s.append(mp3_path)
                        self.append_log("   [OK] Đã thêm nhạc Outro 30s vào danh sách Merge.")
                        self.music_attributions.append({
                            "title": video_title,
                            "url": "Kho nhạc Offline",
                            "uploader": "You"
                        })
                    else:
                        self.append_log("   [LỖI] Không thể xử lý nhạc Outro 30s.")
                else:
                    self.append_log("   [LỖI] Kho nhạc Offline trống, bỏ qua nhạc Outro.")
            except Exception as e:
                self.append_log(f"   [LỖI Xử lý nhạc Outro]: {str(e)[:50]}...")

            # 5.2 Tải Video chống gậy (thử Pixabay, nếu lỗi Cloudflare thì tải từ YouTube)
            try:
                import random
                pixabay_url = f"https://pixabay.com/api/videos/?key={self.pixabay_api_key}&q=nature+sky+clouds&video_type=film&per_page=5"
                headers = {'User-Agent': 'Mozilla/5.0'}
                res = requests.get(pixabay_url, headers=headers)
                if res.status_code != 200:
                    raise Exception(f"Lỗi Pixabay ({res.status_code})")
                pix_res = res.json()
                
                if int(pix_res.get('totalHits', 0)) > 0:
                    hits = pix_res['hits']
                    chosen_vid = random.choice(hits)
                    vid_url = ""
                    for quality in ['large', 'medium', 'small']:
                        if chosen_vid['videos'].get(quality, {}).get('url'):
                            vid_url = chosen_vid['videos'][quality]['url']
                            break
                            
                    if vid_url:
                        pixabay_file = os.path.join(final_out_dir, f"Pixabay_AntiCopyright_{chosen_vid['id']}.mp4")
                        self.append_log(f"   Đang tải video Pixabay: {vid_url[:50]}...")
                        with requests.get(vid_url, stream=True, headers=headers) as r:
                            r.raise_for_status()
                            with open(pixabay_file, 'wb') as f:
                                for chunk in r.iter_content(chunk_size=8192):
                                    f.write(chunk)
                                    
                        duration = chosen_vid.get('duration', 0)
                        if duration < 30:
                            looped_file = os.path.join(final_out_dir, f"Pixabay_AntiCopyright_{chosen_vid['id']}_Looped.mp4")
                            cmd = ["ffmpeg", "-y", "-stream_loop", "-1", "-i", pixabay_file, "-t", "30", "-c:v", "libx264", "-preset", "fast", looped_file]
                            subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, creationflags=subprocess.CREATE_NO_WINDOW)
                            if os.path.exists(looped_file):
                                os.remove(pixabay_file)
                                os.rename(looped_file, pixabay_file)
                        else:
                            cut_file = os.path.join(final_out_dir, f"Pixabay_AntiCopyright_{chosen_vid['id']}_Cut.mp4")
                            cmd = ["ffmpeg", "-y", "-i", pixabay_file, "-t", "30", "-c:v", "copy", cut_file]
                            subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, creationflags=subprocess.CREATE_NO_WINDOW)
                            if os.path.exists(cut_file):
                                os.remove(pixabay_file)
                                os.rename(cut_file, pixabay_file)
                        
                        self.append_log(f"   [THÀNH CÔNG] Đã lưu Video chống gậy Pixabay tại: {pixabay_file}")
                    else:
                        raise Exception("Không tìm thấy link MP4")
                else:
                    raise Exception("Không tìm thấy video nào")
            except Exception as e:
                self.append_log(f"   [LỖI Pixabay do Cloudflare/Mạng]: Chuyển sang tải Video từ YouTube...")
                ydl_opts_vid = {
                    'format': 'bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best',
                    'outtmpl': os.path.join(final_out_dir, f"YouTube_AntiCopyright_%(id)s.%(ext)s"),
                    'noplaylist': True,
                    'quiet': True,
                    'no_warnings': True
                }
                try:
                    with yt_dlp.YoutubeDL(ydl_opts_vid) as ydl:
                        info = ydl.extract_info("ytsearch1:30 second nature video copyright free", download=True)
                        if 'entries' in info and len(info['entries']) > 0:
                            entry = info['entries'][0]
                            vid_path = ydl.prepare_filename(entry)
                            
                            cut_vid_path = os.path.splitext(vid_path)[0] + "_Cut.mp4"
                            # Cắt video YouTube về đúng 30s
                            cmd = ["ffmpeg", "-y", "-i", vid_path, "-t", "30", "-c:v", "libx264", "-preset", "fast", "-an", cut_vid_path]
                            subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, creationflags=subprocess.CREATE_NO_WINDOW)
                            if os.path.exists(cut_vid_path):
                                os.remove(vid_path)
                                os.rename(cut_vid_path, vid_path)
                                
                            self.append_log(f"   [THÀNH CÔNG] Đã lưu Video chống gậy YouTube tại: {vid_path}")
                except Exception as ye:
                    self.append_log(f"   [LỖI YouTube Fallback]: {str(ye)[:50]}...")

            # 6. HỢP NHẤT (MERGE) MASTER TRACK
            if processed_mp3s:
                self.append_log("\n[6/6] Đang hợp nhất tất cả các bài thành 1 file duy nhất (Master Track)...")
                self.status_label2.configure(text="Đang trộn nhạc (Merging)...")
                
                final_out_dir = os.path.dirname(self.video_path) if self.video_path else DOWNLOAD_DIR
                base_name = os.path.basename(self.video_path) if self.video_path else "Audio"
                final_mp3_path = os.path.join(final_out_dir, f"Final_BGM_{os.path.splitext(base_name)[0]}.mp3")
                
                # Xây dựng lệnh FFmpeg
                cmd = ["ffmpeg", "-y"]
                for mp3 in processed_mp3s:
                    cmd.extend(["-i", mp3])
                    
                filter_str = "".join([f"[{i}:a]" for i in range(len(processed_mp3s))]) + f"concat=n={len(processed_mp3s)}:v=0:a=1[outa]"
                cmd.extend(["-filter_complex", filter_str, "-map", "[outa]", "-c:a", "libmp3lame", "-q:a", "2", final_mp3_path])
                
                try:
                    subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, creationflags=subprocess.CREATE_NO_WINDOW, check=True)
                    if os.path.exists(final_mp3_path):
                        self.append_log(f"\n   [THÀNH CÔNG] Đã xuất file Master Track hoàn chỉnh!")
                        self.append_log(f"   File Master được lưu tại: {final_mp3_path}")
                        # Dọn rác
                        for mp3 in processed_mp3s:
                            try:
                                os.remove(mp3)
                            except:
                                pass
                        self.append_log("   [OK] Đã dọn dẹp các mảnh ghép rác tạm thời.")
                    else:
                        self.append_log("\n   [LỖI] Không tìm thấy file Master sau khi trộn.")
                except Exception as e:
                    self.append_log(f"\n   [LỖI FFmpeg Merge]: Lỗi hợp nhất: {str(e)}")

            self.status_label2.configure(text="HOÀN TẤT!")
            self.progress_bar2.set(1.0)
            
            # Clean up the file on Google Server
            client.files.delete(name=uploaded_file.name)
            
        except Exception as e:
            self.status_label2.configure(text="Lỗi!")
            self.append_log(f"\n[LỖI NGHIÊM TRỌNG]: {str(e)}")
            messagebox.showerror("Lỗi", str(e))
        finally:
            self.btn_suggest.configure(state="normal")


    # ================= TAB 3: SEO & THUMBNAIL =================
    def setup_tab3(self):
        self.btn_frame3 = ctk.CTkFrame(self.tab3, fg_color="transparent")
        self.btn_frame3.pack(fill="x", pady=10)

        self.btn_load_img = ctk.CTkButton(self.btn_frame3, text="1. Tải Thumbnail Mẫu (Tùy chọn)", command=self.load_thumbnail)
        self.btn_load_img.pack(side="left", padx=5)
        
        self.img_label = ctk.CTkLabel(self.btn_frame3, text="Chưa chọn ảnh")
        self.img_label.pack(side="left", padx=10)

        self.btn_seo = ctk.CTkButton(self.btn_frame3, text="2. Bắt đầu tạo SEO", command=self.start_seo)
        self.btn_seo.pack(side="right", padx=5)

        self.status_label3 = ctk.CTkLabel(self.tab3, text="Trạng thái: Đang chờ...")
        self.status_label3.pack(anchor="w", pady=5)
        
        self.seo_result_box = ctk.CTkTextbox(self.tab3, wrap="word", font=ctk.CTkFont(size=14))
        self.seo_result_box.pack(fill="both", expand=True, pady=10)

    def load_thumbnail(self):
        file_path = filedialog.askopenfilename(filetypes=[("Image Files", "*.png;*.jpg;*.jpeg;*.webp")])
        if file_path:
            self.ref_image_path = file_path
            self.img_label.configure(text=os.path.basename(file_path))
            
    def start_seo(self):
        if not self.gemini_api_key:
            messagebox.showwarning("Cảnh báo", "Vui lòng lưu Gemini API Key!")
            return
        
        subs_to_use = getattr(self, 'music_subs', None)
        if not subs_to_use:
            subs_to_use = self.translated_subs
            
        if not subs_to_use:
            messagebox.showwarning("Cảnh báo", "Không tìm thấy kịch bản! Vui lòng tải file SRT ở Tab 1 hoặc Tab 2 trước.")
            return
            
        self.btn_seo.configure(state="disabled")
        self.seo_result_box.delete("1.0", "end")
        threading.Thread(target=self.process_seo_pipeline, args=(subs_to_use,), daemon=True).start()

    def process_seo_pipeline(self, subs_to_use):
        try:
            self.status_label3.configure(text="Đang thu thập kịch bản...")
            script_summary = ""
            for sub in subs_to_use:
                script_summary += f"{sub.text.replace(chr(10), ' ')}\n"
            if len(script_summary) > 30000:
                script_summary = script_summary[:30000] + "\n... (Còn tiếp)"

            client = genai.Client(api_key=self.gemini_api_key)
            self.status_label3.configure(text="Đang gọi AI (gemini-2.5-flash)...")
            
            prompt = f"""
Bạn là một chuyên gia YouTube SEO và Đạo diễn Nghệ thuật chuyên về mảng Hoạt hình 3D Trung Quốc (Đấu La Đại Lục, Đấu Phá Thương Khung, Tu Tiên, Xuyên Không).
Dựa vào nội dung kịch bản dưới đây (được trích xuất từ file phụ đề SRT, chủ yếu là lời thoại) và hình ảnh thumbnail mẫu (nếu có), hãy tạo:
1. 3 Tiêu đề video (giật tít, khơi gợi sự tò mò để tăng CTR cao nhất).
2. 3 Đoạn prompt bằng tiếng Anh (chi tiết, miêu tả ánh sáng, góc máy, chất lượng 8k) để tôi dùng làm lệnh vẽ AI Thumbnail. 

BẮT BUỘC 3 PROMPT PHẢI LÀ 3 CONCEPT HOÀN TOÀN KHÁC NHAU NHƯNG PHẢI ĐÚNG VỚI NỘI DUNG KỊCH BẢN:
- Concept 1 (Cao Trào/Chiến Đấu): Lấy cảnh hành động hoặc nhân vật nam chính/kẻ thù bùng nổ sức mạnh CÓ THẬT trong kịch bản (glowing aura, lightning). Bối cảnh tối, kỳ bí.
- Concept 2 (Nhân vật Nữ/Quyến rũ cực độ): Lựa chọn một nhân vật nữ XUẤT HIỆN trong kịch bản. BẮT BUỘC phái nhồi các từ khóa miêu tả sự quyến rũ tột độ vào prompt tiếng Anh: "extremely beautiful, hyper-seductive, wearing extremely revealing fantasy outfit, deep cleavage, voluptuous body, ultra high slit dress showing bare legs, bare shoulders". Nếu kịch bản không có nữ, hãy thay bằng một bảo vật/vũ khí quan trọng rực sáng.
- Concept 3 (Bí Ẩn/Boss/Toàn Cảnh): Lấy một nhân vật phụ bí ẩn, một quái thú, hoặc khung cảnh tông môn/di tích rộng lớn ĐƯỢC NHẮC ĐẾN trong kịch bản. Nếu kịch bản chỉ có đối thoại trong nhà, hãy biến tấu thành một khung cảnh nội thất tráng lệ.

YÊU CẦU VỀ CHỮ (TYPOGRAPHY) DỰA CHẶT CHẼ VÀO KỊCH BẢN (KHÔNG ĐƯỢC BỊA ĐẶT NẾU KỊCH BẢN KHÔNG CÓ):
- Text góc phải (Top Right Badge): Hãy TỰ PHÂN TÍCH THỂ LOẠI của kịch bản này để viết (Ví dụ: Nếu có nói về Hệ Thống thì ghi "HỆ THỐNG", nếu tu tiên thì ghi "TU TIÊN", nếu không rõ thể loại thì cứ ghi "TẬP MỚI" hoặc "CỰC HAY").
- Text chính (Bottom Title): Rút trích 1 câu siêu ngắn (3-6 chữ) mô tả ĐÚNG diễn biến sốc nhất của đoạn thoại này. (LƯU Ý QUAN TRỌNG: BẮT BUỘC PHẢI TỰ SUY LUẬN TỪ LỜI THOẠI, TUYỆT ĐỐI KHÔNG COPY CÁC TỪ NHƯ "TIÊU DIỆT TÔNG MÔN" HAY "THỨC TỈNH" NẾU TRONG THOẠI KHÔNG CÓ).
- Màu sắc chữ: Phải KHÁC NHAU giữa 3 prompt. (Ví dụ: Prompt 1 dùng chữ Vàng viền Đen tỏa sáng đỏ, Prompt 2 dùng chữ Tím viền Trắng tỏa sáng Neon Cyan, Prompt 3 dùng chữ Xanh lá viền Đen).
- Ví dụ cách chèn text: "Top right corner has text 'TRỌNG SINH' in purple badge. Bottom text: 'BẠI LỘ THÂN PHẬN' in large 3D bold font, yellow gradient with thick black stroke and fiery glow."

YÊU CẦU CHUNG:
- Chất lượng & Phong cách: "3D Chinese animation style, Donghua, Unreal Engine 5 render, highly detailed 3D masterpiece, cinematic lighting, extreme contrast".

3. 1 Đoạn mô tả video (Description) lôi cuốn, bao gồm các #hashtag thịnh hành.
4. 1 Chuỗi các thẻ từ khóa (Tags) cách nhau bằng dấu phẩy (không có #, hoàn toàn bằng tiếng Việt có dấu, bám sát nội dung).

Định dạng trả về BẮT BUỘC là 1 chuẩn JSON (không có markdown code block), cấu trúc như sau:
{{
  "titles": ["Tiêu đề 1", "Tiêu đề 2", "Tiêu đề 3"],
  "thumbnail_prompts": ["Prompt 1", "Prompt 2", "Prompt 3"],
  "description": "Nội dung mô tả... #hastag1 #hashtag2",
  "tags": "tag1, tag2, tag3"
}}

Kịch bản thoại:
{script_summary}
"""
            contents = []
            if getattr(self, 'ref_image_path', None) and os.path.exists(self.ref_image_path):
                img = PIL.Image.open(self.ref_image_path)
                contents.append(img)
            contents.append(prompt)

            response = None
            models_to_try = ['gemini-3.1-flash-lite', 'gemini-2.5-flash', 'gemini-2.0-flash']
            
            for model_name in models_to_try:
                try:
                    self.status_label3.configure(text=f"Đang gọi AI ({model_name})...")
                    response = client.models.generate_content(
                        model=model_name,
                        contents=contents,
                        config=types.GenerateContentConfig(
                            response_mime_type="application/json",
                            response_schema={
                                "type": "OBJECT",
                                "properties": {
                                    "titles": {
                                        "type": "ARRAY",
                                        "description": "3 Tiêu đề video giật tít, tăng CTR",
                                        "items": {"type": "STRING"}
                                    },
                                    "thumbnail_prompts": {
                                        "type": "ARRAY",
                                        "description": "3 Concepts chi tiết, mỗi concept là 1 JSON Object",
                                        "items": {
                                            "type": "OBJECT",
                                            "properties": {
                                                "concept_name": {"type": "STRING", "description": "Tên concept (VD: Nhân vật nữ, Chiến đấu, Toàn cảnh)"},
                                                "badge_text": {"type": "STRING", "description": "Text góc phải (VD: TẬP MỚI, TU TIÊN)"},
                                                "main_text": {"type": "STRING", "description": "Text chính giữa dưới cùng (3-6 chữ)"},
                                                "typography_style": {"type": "STRING", "description": "Mô tả màu sắc và hiệu ứng chữ bằng tiếng Anh (VD: large 3D bold font, green gradient...)"},
                                                "image_prompt": {"type": "STRING", "description": "Prompt chi tiết mô tả bối cảnh, nhân vật, ánh sáng bằng tiếng Anh (KHÔNG chứa text)"},
                                                "full_english_prompt": {"type": "STRING", "description": "Prompt hoàn chỉnh bằng tiếng Anh (Gộp cả text và image_prompt lại) để copy paste cho AI vẽ ảnh"}
                                            },
                                            "required": ["concept_name", "badge_text", "main_text", "typography_style", "image_prompt", "full_english_prompt"]
                                        }
                                    },
                                    "description": {
                                        "type": "STRING",
                                        "description": "Mô tả video lôi cuốn bao gồm hashtags"
                                    },
                                    "tags": {
                                        "type": "STRING",
                                        "description": "Chuỗi các thẻ từ khóa cách nhau bằng dấu phẩy"
                                    }
                                },
                                "required": ["titles", "thumbnail_prompts", "description", "tags"]
                            }
                        )
                    )
                    break
                except Exception as e:
                    err_str = str(e)
                    if "429" in err_str or "RESOURCE_EXHAUSTED" in err_str:
                        if hasattr(self, 'status_label3'):
                            self.status_label3.configure(text=f"Lỗi 429: Quá tải API. Đang chờ 60s...")
                        time.sleep(60)
                        continue
                    elif "503" in err_str or "UNAVAILABLE" in err_str:
                        time.sleep(5)
                        continue
                    else:
                        raise e
                        
            if not response:
                raise Exception("Tất cả các model đều thất bại hoặc hết Quota.")
            
            data = json.loads(response.text)
            
            # Format output
            out_text = "====== TIÊU ĐỀ VIDEO (TĂNG CTR) ======\n"
            for i, t in enumerate(data.get("titles", [])):
                out_text += f"{i+1}. {t}\n"
                
            out_text += "\n====== PROMPT TẠO THUMBNAIL (JSON CHI TIẾT) ======\n"
            for i, t in enumerate(data.get("thumbnail_prompts", [])):
                if isinstance(t, dict):
                    out_text += f"--- CONCEPT {i+1}: {t.get('concept_name', '')} ---\n"
                    out_text += json.dumps(t, indent=2, ensure_ascii=False) + "\n\n"
                else:
                    out_text += f"{i+1}. {t}\n\n"
                
            out_text += "====== MÔ TẢ VIDEO (DESCRIPTION) ======\n"
            out_text += f"{data.get('description', '')}\n\n"
            
            if getattr(self, 'music_attributions', None) and len(self.music_attributions) > 0:
                out_text += "====== THÔNG TIN BẢN QUYỀN ÂM NHẠC (BẮT BUỘC COPY VÀO MÔ TẢ) ======\n"
                out_text += "🎵 Background Music in this video:\n"
                for attr in self.music_attributions:
                    out_text += f"- {attr['title']} by {attr['uploader']}\n  Link: {attr['url']}\n"
                out_text += "\nLicensed under Creative Commons: By Attribution 3.0 License\n"
                out_text += "http://creativecommons.org/licenses/by/3.0/\n\n"
            
            out_text += "====== TỪ KHÓA (TAGS) ======\n"
            out_text += f"{data.get('tags', '')}\n"
            
            self.seo_result_box.insert("1.0", out_text)
            self.status_label3.configure(text="HOÀN TẤT!")
            
        except Exception as e:
            self.status_label3.configure(text="Lỗi!")
            messagebox.showerror("Lỗi", f"Có lỗi xảy ra: {str(e)}")
        finally:
            self.btn_seo.configure(state="normal")

    # ================= TAB 4: TẠO INTRO CHỐNG GẬY =================
    def setup_tab4(self):
        self.btn_frame4 = ctk.CTkFrame(self.tab4, fg_color="transparent")
        self.btn_frame4.pack(fill="x", pady=10)

        self.btn_load_vid4 = ctk.CTkButton(self.btn_frame4, text="1. Chọn Video Gốc", command=self.load_video4)
        self.btn_load_vid4.pack(side="left", padx=5)
        self.vid_lbl4 = ctk.CTkLabel(self.btn_frame4, text="Chưa chọn video")
        self.vid_lbl4.pack(side="left", padx=5)

        self.btn_load_srt4 = ctk.CTkButton(self.btn_frame4, text="2. Chọn SRT (Tiếng Việt)", command=self.load_srt4)
        self.btn_load_srt4.pack(side="left", padx=5)
        self.srt_lbl4 = ctk.CTkLabel(self.btn_frame4, text="Chưa chọn SRT")
        self.srt_lbl4.pack(side="left", padx=5)

        self.btn_create_intro = ctk.CTkButton(self.btn_frame4, text="3. TẠO INTRO 30S", command=self.start_intro, state="disabled")
        self.btn_create_intro.pack(side="right", padx=5)

        self.status_label4 = ctk.CTkLabel(self.tab4, text="Trạng thái: Đang chờ...")
        self.status_label4.pack(anchor="w", pady=5)
        self.progress_bar4 = ctk.CTkProgressBar(self.tab4)
        self.progress_bar4.pack(fill="x", padx=10, pady=5)
        self.progress_bar4.set(0)

        self.intro_log_box = ctk.CTkTextbox(self.tab4, wrap="word", font=ctk.CTkFont(size=14))
        self.intro_log_box.pack(fill="both", expand=True, pady=10)
        
        self.video_path4 = None
        self.srt_path4 = None

    def load_video4(self):
        path = filedialog.askopenfilename(filetypes=[("Video Files", "*.mp4 *.mkv *.avi")])
        if path:
            self.video_path4 = path
            self.vid_lbl4.configure(text=os.path.basename(path))
            self.check_intro_ready()

    def load_srt4(self):
        path = filedialog.askopenfilename(filetypes=[("SRT Files", "*.srt")])
        if path:
            self.srt_path4 = path
            self.srt_lbl4.configure(text=os.path.basename(path))
            self.check_intro_ready()

    def check_intro_ready(self):
        if self.video_path4 and self.srt_path4:
            self.btn_create_intro.configure(state="normal")

    def append_log4(self, message):
        self.intro_log_box.insert("end", message + "\n")
        self.intro_log_box.see("end")

    def start_intro(self):
        if not self.gemini_api_key:
            messagebox.showwarning("Cảnh báo", "Vui lòng nhập Gemini API Key!")
            return
        self.btn_create_intro.configure(state="disabled")
        self.progress_bar4.set(0.1)
        self.intro_log_box.delete("1.0", "end")
        threading.Thread(target=self.process_intro_creation, daemon=True).start()

    def process_intro_creation(self):
        try:
            self.status_label4.configure(text="Đang phân tích kịch bản bằng AI...")
            self.append_log4("[1/5] Đọc file SRT và gửi cho AI...")
            
            subs = pysrt.open(self.srt_path4)
            # Truyền toàn bộ kịch bản (hoặc tối đa 5000 câu) để AI có cái nhìn toàn cảnh, không bị ảo giác thời gian
            full_text = "\n".join([f"[{str(sub.start).split(',')[0]}] {sub.text.replace(chr(10), ' ')}" for sub in subs[:5000]])
            
            prompt = f"""
Bạn là một đạo diễn chuyên nghiệp làm Intro tóm tắt cho phim trên YouTube.
Hãy đọc một phần kịch bản phim dưới đây (có kèm mốc thời gian dạng [HH:MM:SS]).
Nhiệm vụ 1: Dựa vào nội dung, hãy chọn ra đúng 6 mốc thời gian (start_time) của 6 phân cảnh CÓ KHẢ NĂNG CAO NHẤT LÀ hành động, đánh nhau, bỏ chạy, cãi vã kịch tính. Mỗi cảnh sẽ kéo dài khoảng 5 giây nên bạn chỉ cần chọn mốc bắt đầu.
CỰC KỲ QUAN TRỌNG: Mốc thời gian phải được COPY CHÍNH XÁC Y HỆT từ kịch bản bên dưới. Ví dụ kịch bản ghi [00:01:14], bạn phải trả về chính xác "00:01:14". TUYỆT ĐỐI KHÔNG ĐƯỢC tự ý dịch chuyển các con số thành "01:14:00". Định dạng luôn là HH:MM:SS.

Nhiệm vụ 2: Tự sáng tác một kịch bản lồng tiếng dài khoảng 60 từ (tương đương 30 giây đọc) với form cố định sau:
"Chào mừng bạn đến với Bo Bắp Media, hôm nay chúng ta cùng xem bộ phim [tên bộ phim tự suy ra từ kịch bản]... [tóm tắt 1-2 câu cực kỳ giật gân về cốt truyện]... Hãy cùng xem và cảm nhận, cũng đừng quên cho mình xin 1 đăng ký kênh để ủng hộ kênh phát triển nhé."
Kịch bản này cần được chia thành 6 câu ngắn, mỗi câu tương ứng với 5 giây để làm file SRT mới. Định dạng thời gian là HH:MM:SS.

KỊCH BẢN PHIM:
{full_text}
"""
            client = genai.Client(api_key=self.gemini_api_key)
            models_to_try = ['gemini-3.1-flash-lite', 'gemini-2.5-flash', 'gemini-2.0-flash']
            response = None
            
            schema = {
                "type": "OBJECT",
                "properties": {
                    "highlights": {
                        "type": "ARRAY",
                        "items": {
                            "type": "OBJECT",
                            "properties": {"start_time": {"type": "STRING", "description": "HH:MM:SS"}}
                        }
                    },
                    "intro_script": {
                        "type": "ARRAY",
                        "items": {
                            "type": "OBJECT",
                            "properties": {
                                "start_time": {"type": "STRING", "description": "HH:MM:SS"},
                                "end_time": {"type": "STRING", "description": "HH:MM:SS"},
                                "text": {"type": "STRING"}
                            }
                        }
                    }
                },
                "required": ["highlights", "intro_script"]
            }

            for model_name in models_to_try:
                try:
                    response = client.models.generate_content(
                        model=model_name,
                        contents=prompt,
                        config=types.GenerateContentConfig(
                            response_mime_type="application/json",
                            response_schema=schema
                        )
                    )
                    break
                except Exception as e:
                    self.append_log4(f"  - Lỗi {model_name}: {str(e)}")
                    time.sleep(5)
            
            if not response:
                raise Exception("Tất cả API đều lỗi.")
                
            res_json = json.loads(response.text)
            highlights = res_json.get("highlights", [])
            intro_script = res_json.get("intro_script", [])
            
            self.progress_bar4.set(0.3)
            self.append_log4("[2/5] Đã nhận phân tích từ AI. Đang lưu file SRT cho Intro...")
            
            # Lấy thư mục chứa file SRT tiếng Việt làm thư mục xuất (theo yêu cầu của user)
            out_dir = os.path.dirname(self.srt_path4) if self.srt_path4 else os.path.dirname(self.video_path4)
            
            # Lưu file SRT intro
            intro_srt_path = os.path.join(out_dir, "Intro_BoBapMedia.srt")
            with open(intro_srt_path, "w", encoding="utf-8") as f:
                for idx, line in enumerate(intro_script):
                    f.write(f"{idx+1}\n{line['start_time']},000 --> {line['end_time']},000\n{line['text']}\n\n")
            self.append_log4(f"   Đã tạo file: {intro_srt_path}")
            
            # --- 3. LẤY BGM TỪ KHO NHẠC OFFLINE ---
            self.status_label4.configure(text="Đang lấy nhạc nền Intro từ Kho Offline...")
            self.progress_bar4.set(0.4)
            self.append_log4("[3/5] Đang lấy nhạc nền Epic từ kho Offline...")
            
            bgm_path = None
            import glob, random
            offline_music_dir = KHO_NHAC_DIR
            available_music = []
            
            if os.path.exists(offline_music_dir):
                for root_dir, dirs, files in os.walk(offline_music_dir):
                    for f in files:
                        if f.lower().endswith(('.mp3', '.m4a', '.wav')):
                            available_music.append(os.path.join(root_dir, f))
            
            if available_music:
                # Ưu tiên nhạc hành động, cảm hứng cho Intro
                epic_music = [m for m in available_music if 'epic' in m.lower() or 'hanhdong' in m.lower() or 'truyen_cam_hung' in m.lower()]
                if epic_music:
                    bgm_path = random.choice(epic_music)
                else:
                    bgm_path = random.choice(available_music)
                self.append_log4(f"   Đã chọn nhạc Intro: {os.path.basename(bgm_path)}")
            else:
                self.append_log4("   [Cảnh báo] Kho nhạc trống, tạo Intro không có nhạc nền.")
            
            # --- 4. CUT VIDEO CLIPS ---
            self.status_label4.configure(text="Đang cắt ghép Video (Có thể hơi lâu)...")
            self.progress_bar4.set(0.6)
            self.append_log4("[4/5] Đang dùng FFmpeg để trích xuất 6 khung cảnh...")
            
            clips = []
            import re
            def clean_time_format(ts):
                # Thử tìm định dạng HH:MM:SS
                m = re.search(r'(\d{1,2}):(\d{2}):(\d{2})', str(ts))
                if m: return f"{int(m.group(1)):02d}:{m.group(2)}:{m.group(3)}"
                # Thử tìm định dạng MM:SS
                m2 = re.search(r'(\d{1,2}):(\d{2})', str(ts))
                if m2: return f"00:{int(m2.group(1)):02d}:{m2.group(2)}"
                return "00:00:00"

            for i, hl in enumerate(highlights[:6]):
                raw_time = hl.get('start_time', '00:00:00')
                start_time = clean_time_format(raw_time)
                clip_path = os.path.join(out_dir, f"temp_clip_{i}.mp4")
                cmd = f'ffmpeg -y -i "{self.video_path4}" -ss {start_time} -t 5 -c:v libx264 -an -preset ultrafast "{clip_path}"'
                self.append_log4(f"   Đang cắt clip {i+1} tại {start_time} (gốc: {raw_time})...")
                subprocess.run(cmd, shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                if os.path.exists(clip_path):
                    clips.append(clip_path)
            
            self.progress_bar4.set(0.8)
            self.append_log4("[5/5] Đang trộn Video và Nhạc nền...")
            
            concat_txt = os.path.join(out_dir, "concat.txt")
            with open(concat_txt, "w", encoding="utf-8") as f:
                for c in clips:
                    f.write(f"file '{os.path.basename(c)}'\n")
            
            merged_no_audio = os.path.join(out_dir, "temp_merged.mp4")
            # Set cwd=out_dir so FFmpeg can correctly resolve relative paths in concat.txt
            concat_cmd = f'ffmpeg -y -f concat -safe 0 -i "concat.txt" -c copy "{os.path.basename(merged_no_audio)}"'
            subprocess.run(concat_cmd, shell=True, cwd=out_dir, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            
            final_intro = os.path.join(out_dir, "Intro_BoBapMedia_30s.mp4")
            if bgm_path and os.path.exists(merged_no_audio):
                # Sử dụng -map 0:v:0 -map 1:a:0 để ngăn FFmpeg lấy nhầm ảnh bìa (cover art) của file MP3 làm stream Video
                cmd_final = f'ffmpeg -y -i "{os.path.basename(merged_no_audio)}" -stream_loop -1 -i "{bgm_path}" -map 0:v:0 -map 1:a:0 -t 30 -c:v copy -c:a aac -af "afade=t=out:st=27:d=3" -shortest "{os.path.basename(final_intro)}"'
                p_merge = subprocess.run(cmd_final, shell=True, cwd=out_dir, capture_output=True, text=True)
                if p_merge.returncode != 0:
                    self.append_log4(f"   [Lỗi FFmpeg Merge Intro]: {p_merge.stderr}")
            elif os.path.exists(merged_no_audio):
                os.rename(merged_no_audio, final_intro)
                
            # Cleanup
            try:
                for c in clips: os.remove(c)
                if os.path.exists(concat_txt): os.remove(concat_txt)
                if os.path.exists(merged_no_audio): os.remove(merged_no_audio)
            except: pass
            
            if os.path.exists(final_intro):
                self.progress_bar4.set(1.0)
                self.status_label4.configure(text="HOÀN TẤT TẠO INTRO!")
                self.append_log4(f"\n🎉 THÀNH CÔNG! Đã xuất file Intro:\n- Video: {os.path.basename(final_intro)}\n- Kịch bản SRT: {os.path.basename(intro_srt_path)}")
            else:
                raise Exception("Lỗi: FFmpeg không xuất được video Intro!\nNguyên nhân có thể do:\n1. AI đọc sai mốc thời gian (vượt quá độ dài video).\n2. Bạn chọn NHẦM file MP3 hoặc đoạn video quá ngắn thay vì chọn file Video gốc dài.")
        except Exception as e:
            self.status_label4.configure(text="Lỗi!")
            self.append_log4(f"\n[LỖI]: {str(e)}")
            messagebox.showerror("Lỗi", str(e))
        finally:
            self.btn_create_intro.configure(state="normal")

    # ================= TAB 5: SIÊU CÀO PHỤ ĐỀ (OCR) =================
    def setup_tab5(self):
        self.btn_frame5 = ctk.CTkFrame(self.tab5, fg_color="transparent")
        self.btn_frame5.pack(fill="x", pady=10)

        self.btn_load_vid5 = ctk.CTkButton(self.btn_frame5, text="1. Chọn Video Gốc", command=self.load_video5)
        self.btn_load_vid5.pack(side="left", padx=5)
        self.vid_lbl5 = ctk.CTkLabel(self.btn_frame5, text="Chưa chọn video")
        self.vid_lbl5.pack(side="left", padx=5)
        
        self.chk_nvenc_var = ctk.BooleanVar(value=True)
        self.chk_nvenc = ctk.CTkCheckBox(self.btn_frame5, text="Dùng NVIDIA GPU (NVENC)", variable=self.chk_nvenc_var)
        self.chk_nvenc.pack(side="left", padx=15)

        self.ocr_bbox = None
        self.btn_choose_roi = ctk.CTkButton(self.btn_frame5, text="🎯 Chọn Vùng Chữ", command=self.choose_roi, state="disabled")
        self.btn_choose_roi.pack(side="left", padx=5)

        self.btn_create_ocr = ctk.CTkButton(self.btn_frame5, text="BẮT ĐẦU CÀO PHỤ ĐỀ", command=self.start_ocr, state="disabled")
        self.btn_create_ocr.pack(side="right", padx=5)

        self.status_label5 = ctk.CTkLabel(self.tab5, text="Trạng thái: Đang chờ...")
        self.status_label5.pack(anchor="w", pady=5)
        self.progress_bar5 = ctk.CTkProgressBar(self.tab5)
        self.progress_bar5.pack(fill="x", padx=10, pady=5)
        self.progress_bar5.set(0)

        self.ocr_log_box = ctk.CTkTextbox(self.tab5, wrap="word", font=ctk.CTkFont(size=14))
        self.ocr_log_box.pack(fill="both", expand=True, pady=10)
        
        self.video_path5 = None

    def load_video5(self):
        path = filedialog.askopenfilename(filetypes=[("Video Files", "*.mp4 *.mkv *.avi")])
        if path:
            self.video_path5 = path
            self.vid_lbl5.configure(text=os.path.basename(path))
            self.btn_choose_roi.configure(state="normal")
            self.btn_create_ocr.configure(state="normal")

    def choose_roi(self):
        if not self.video_path5: return
        import cv2
        cap = cv2.VideoCapture(self.video_path5)
        if not cap.isOpened():
            messagebox.showerror("Lỗi", "Không thể đọc video!")
            return
            
        fps = cap.get(cv2.CAP_PROP_FPS)
        cap.set(cv2.CAP_PROP_POS_MSEC, 5000) # Tua qua 5s đầu
        
        messagebox.showinfo("Hướng dẫn Khoanh vùng", "1. Kéo chuột khoanh ô vuông ôm trọn dòng chữ rồi nhấn ENTER/SPACE để Lưu.\n2. Nếu màn hình chưa có chữ, nhấn ENTER/SPACE (không khoanh) để tua qua 2 giây.\n\nĐỂ HỦY BỎ: Hãy bấm nút [X] góc phải trên cùng để đóng cửa sổ.")
        
        cv2.namedWindow("Chon vung phu de", cv2.WINDOW_NORMAL)
        first_frame = True
        
        while True:
            ret, frame = cap.read()
            if not ret:
                break
                
            disp = frame.copy()
            cv2.putText(disp, "Keo chuot khoanh roi ENTER/SPACE de Luu.", (20, 50), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 255, 0), 2)
            cv2.putText(disp, "Khong khoanh gi ma an ENTER/SPACE de Tua 2s.", (20, 90), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 255, 0), 2)
            cv2.putText(disp, "Click [X] tren cung ben phai cua so de HUY.", (20, 130), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 0, 255), 2)
            
            if first_frame:
                h, w = frame.shape[:2]
                scale = min(1280/w, 720/h)
                if scale < 1:
                    cv2.resizeWindow("Chon vung phu de", int(w*scale), int(h*scale))
                first_frame = False
            
            bbox = cv2.selectROI("Chon vung phu de", disp, fromCenter=False, showCrosshair=True)
            
            if cv2.getWindowProperty("Chon vung phu de", cv2.WND_PROP_VISIBLE) < 1:
                # Nguoi dung tat cua so
                self.ocr_bbox = None
                self.btn_choose_roi.configure(text="🎯 Đã hủy (Chế độ Tự động)", fg_color="gray")
                break
                
            if bbox == (0, 0, 0, 0):
                # Người dùng ấn Space hoặc Enter nhưng chưa vẽ
                # Tua qua 2 giây
                current_frame = cap.get(cv2.CAP_PROP_POS_FRAMES)
                cap.set(cv2.CAP_PROP_POS_FRAMES, current_frame + int(fps * 2))
                continue
            else:
                self.ocr_bbox = bbox
                self.btn_choose_roi.configure(text="🎯 Đã khoanh vùng", fg_color="green")
                break
                
        try:
            cv2.destroyWindow("Chon vung phu de")
        except:
            pass
        cap.release()

    def append_log5(self, message):
        self.ocr_log_box.insert("end", message + "\n")
        self.ocr_log_box.see("end")

    def start_ocr(self):
        self.btn_create_ocr.configure(state="disabled")
        self.progress_bar5.set(0.1)
        self.ocr_log_box.delete("1.0", "end")
        threading.Thread(target=self.process_ocr_creation, daemon=True).start()

    def process_ocr_creation(self):
        temp_slow_video = None
        try:
            out_dir = os.path.dirname(self.video_path5)
            base_name = os.path.splitext(os.path.basename(self.video_path5))[0]
            temp_slow_video = os.path.join(out_dir, f"{base_name}_temp_slow.mp4")
            output_srt = os.path.join(out_dir, f"{base_name}_OCR.srt")
            clean_video = os.path.join(out_dir, f"{base_name}_Clean.mp4")

            use_nvenc = self.chk_nvenc_var.get()

            # ============================================================
            # BƯỚC 1: GIẢM TỐC ĐỘ VIDEO XUỐNG 0.8x → temp_slow.mp4
            # ============================================================
            self.status_label5.configure(text="Bước 1/3: Đang giảm tốc video (0.8x)...")
            self.append_log5("[1/3] Đang dùng FFmpeg giảm tốc video gốc xuống 0.8x...")
            self.append_log5("   → Giữ nguyên hình ảnh (chưa lật), chỉ giảm tốc để timing khớp thoại.")

            if use_nvenc:
                self.append_log5("   → Dùng GPU NVIDIA (NVENC) để encode...")
                cmd_slow = [
                    "ffmpeg", "-y", "-i", self.video_path5,
                    "-filter_complex", "[0:v]setpts=1.25*PTS[v]",
                    "-map", "[v]", "-vsync", "vfr", "-an",
                    "-c:v", "h264_nvenc", "-preset", "p6", "-cq", "28",
                    temp_slow_video
                ]
            else:
                self.append_log5("   → Dùng CPU để encode (có thể hơi lâu)...")
                cmd_slow = [
                    "ffmpeg", "-y", "-i", self.video_path5,
                    "-filter_complex", "[0:v]setpts=1.25*PTS[v]",
                    "-map", "[v]", "-vsync", "vfr", "-an",
                    "-c:v", "libx264", "-preset", "fast",
                    temp_slow_video
                ]

            proc1 = subprocess.run(cmd_slow, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, text=True, encoding='utf-8')

            if proc1.returncode != 0 and use_nvenc:
                self.append_log5(f"   → [Cảnh báo] NVENC lỗi (code {proc1.returncode}), chuyển sang CPU...")
                self.append_log5(f"   → NVENC stderr: {proc1.stderr[-300:]}")
                cmd_slow_cpu = [
                    "ffmpeg", "-y", "-i", self.video_path5,
                    "-filter_complex", "[0:v]setpts=1.25*PTS[v]",
                    "-map", "[v]", "-vsync", "vfr", "-an",
                    "-c:v", "libx264", "-preset", "fast",
                    temp_slow_video
                ]
                proc1 = subprocess.run(cmd_slow_cpu, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, text=True, encoding='utf-8')

            if proc1.returncode != 0:
                raise Exception(f"FFmpeg giảm tốc thất bại:\n{proc1.stderr[-500:]}")
            if not os.path.exists(temp_slow_video) or os.path.getsize(temp_slow_video) == 0:
                raise Exception("File video giảm tốc tạo ra bị rỗng hoặc không tồn tại.")

            # Đọc kích thước thực tế của video sau giảm tốc để validate ROI
            import cv2
            cap_check = cv2.VideoCapture(temp_slow_video)
            vid_w = int(cap_check.get(cv2.CAP_PROP_FRAME_WIDTH))
            vid_h = int(cap_check.get(cv2.CAP_PROP_FRAME_HEIGHT))
            cap_check.release()
            self.append_log5(f"   → Kích thước video sau giảm tốc: {vid_w}x{vid_h}")

            self.progress_bar5.set(0.3)
            self.append_log5("   ✅ Đã tạo xong video 0.8x. Sẵn sàng quét OCR.\n")

            # ============================================================
            # BƯỚC 2: OCR TỪ VIDEO ĐÃ GIẢM TỐC (timing khớp chính xác)
            # ============================================================
            self.status_label5.configure(text="Bước 2/3: Đang quét OCR từ video 0.8x...")
            self.append_log5("[2/3] Bắt đầu quét OCR từ video đã giảm tốc (chữ đúng chiều)...")
            if self.ocr_bbox:
                x, y, w, h_box = self.ocr_bbox
                self.append_log5(f"   → Vùng quét ROI: x={x}, y={y}, w={w}, h={h_box}")
            else:
                self.append_log5("   → Chế độ tự động (không khoanh vùng).")

            import ocr_extractor

            def ocr_progress(p):
                self.after(0, lambda v=p: self.progress_bar5.set(0.3 + v * 0.5))

            def ocr_text_found(line):
                self.after(0, lambda l=line: self.append_log5(l))

            success = ocr_extractor.extract_subtitles_from_video(
                temp_slow_video,
                output_srt,
                log_callback=lambda msg: self.after(0, lambda m=msg: self.append_log5(m)),
                progress_callback=ocr_progress,
                roi_bbox=self.ocr_bbox,
                text_callback=ocr_text_found
            )

            if not success:
                raise Exception("Quét OCR thất bại. Vui lòng kiểm tra lại video.")

            self.progress_bar5.set(0.8)
            self.append_log5(f"\n   ✅ OCR hoàn tất! Đã lưu SRT: {os.path.basename(output_srt)}\n")

            # ============================================================
            # BƯỚC 3: LẬT HÌNH + BLUR ROI trên video đã giảm tốc → Clean
            # ============================================================
            self.status_label5.configure(text="Bước 3/3: Đang lật hình + làm mờ phụ đề...")
            self.append_log5("[3/3] Đang tạo video sạch: lật hình (hflip) + làm mờ vùng phụ đề...")

            if self.ocr_bbox:
                x, y, w, h_box = self.ocr_bbox

                # Clamp ROI vào trong kích thước thực tế của video (tránh lỗi -22 Invalid argument)
                x     = max(0, min(x, vid_w - 1))
                y     = max(0, min(y, vid_h - 1))
                w     = max(1, min(w, vid_w - x))
                h_box = max(1, min(h_box, vid_h - y))

                # Ép các tọa độ và kích thước về số chẵn để an toàn tuyệt đối với subsampling yuv420p
                x = int(x - (x % 2))
                y = int(y - (y % 2))
                w = int(w - (w % 2))
                h_box = int(h_box - (h_box % 2))
                
                # Đảm bảo width và height tối thiểu là 2
                w = max(2, w)
                h_box = max(2, h_box)

                self.append_log5(f"   → Làm mờ vùng ROI: ({w}x{h_box} tại {x},{y}) trên frame {vid_w}x{vid_h}")

                # Dùng gblur thay vì boxblur vì boxblur sẽ crash (lỗi -22) nếu h_box quá nhỏ so với radius
                filter_str = (
                    f"[0:v]split=2[main][ref];"
                    f"[ref]crop=w={w}:h={h_box}:x={x}:y={y},"
                    f"gblur=sigma=15,"
                    f"format=yuv420p[blurred];"
                    f"[main]format=yuv420p[mainf];"
                    f"[mainf][blurred]overlay=x={x}:y={y},"
                    f"hflip[v]"
                )
            else:
                filter_str = "[0:v]hflip[v]"
                self.append_log5("   → Chỉ lật hình (không có vùng ROI để blur).")

            if use_nvenc:
                cmd_clean = [
                    "ffmpeg", "-y", "-i", temp_slow_video,
                    "-filter_complex", filter_str,
                    "-map", "[v]", "-an",
                    "-c:v", "h264_nvenc", "-preset", "p6", "-cq", "28",
                    clean_video
                ]
            else:
                cmd_clean = [
                    "ffmpeg", "-y", "-i", temp_slow_video,
                    "-filter_complex", filter_str,
                    "-map", "[v]", "-an",
                    "-c:v", "libx264", "-preset", "fast",
                    clean_video
                ]

            proc3 = subprocess.run(cmd_clean, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, text=True, encoding='utf-8')

            if proc3.returncode != 0 and use_nvenc:
                self.append_log5("   → [Cảnh báo] NVENC lỗi, chuyển sang CPU...")
                cmd_clean_cpu = [
                    "ffmpeg", "-y", "-i", temp_slow_video,
                    "-filter_complex", filter_str,
                    "-map", "[v]", "-an",
                    "-c:v", "libx264", "-preset", "fast",
                    clean_video
                ]
                proc3 = subprocess.run(cmd_clean_cpu, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, text=True, encoding='utf-8')

            if proc3.returncode != 0:
                # Log stderr chi tiết ra UI để dễ debug
                self.append_log5(f"   → FFmpeg stderr (bước 3):\n{proc3.stderr[-800:]}")
                raise Exception(f"FFmpeg tạo video sạch thất bại:\n{proc3.stderr[-500:]}")

            if not os.path.exists(clean_video) or os.path.getsize(clean_video) == 0:
                raise Exception("File video sạch tạo ra bị rỗng hoặc không tồn tại.")

            self.progress_bar5.set(1.0)
            self.status_label5.configure(text="✅ HOÀN TẤT!")
            self.append_log5(
                f"\n🎉 QUÁ TRÌNH HOÀN TẤT MỸ MÃN!\n"
                f"  📄 File SRT   : {os.path.basename(output_srt)}\n"
                f"  🎬 Video sạch : {os.path.basename(clean_video)}\n"
                f"\n👉 Mang file SRT sang Tab 1 để dịch ngay!"
            )

        except Exception as e:
            self.status_label5.configure(text="❌ Lỗi!")
            self.append_log5(f"\n[LỖI]: {str(e)}")
            messagebox.showerror("Lỗi", str(e))
        finally:
            # Dọn file tạm
            if temp_slow_video and os.path.exists(temp_slow_video):
                try:
                    os.remove(temp_slow_video)
                    self.append_log5("   🗑 Đã xóa file tạm temp_slow.mp4")
                except Exception:
                    pass
            self.btn_create_ocr.configure(state="normal")

    # ================= TAB 6: TẢI VIDEO =================
    def setup_tab6(self):
        # --- Hàng 1: Cookies File ---
        cookie_frame = ctk.CTkFrame(self.tab6, fg_color="transparent")
        cookie_frame.pack(fill="x", padx=10, pady=(10, 0))
        ctk.CTkLabel(cookie_frame, text="File Cookies (Tuỳ chọn):", width=160, anchor="w").pack(side="left")
        default_cookie = os.path.join(APP_DIR, "Downloads", "account.bilibili.com_cookies.txt")
        self.cookie_path6 = ctk.StringVar(value=default_cookie if os.path.exists(default_cookie) else "")
        ctk.CTkEntry(cookie_frame, textvariable=self.cookie_path6, placeholder_text="Chọn file cookies.txt nếu cần đăng nhập...").pack(side="left", fill="x", expand=True, padx=5)
        ctk.CTkButton(cookie_frame, text="Chọn", width=70, command=self.choose_cookie_file6).pack(side="left")

        # --- Hàng 2: URL ---
        url_frame = ctk.CTkFrame(self.tab6, fg_color="transparent")
        url_frame.pack(fill="x", padx=10, pady=5)
        ctk.CTkLabel(url_frame, text="Link Video:", width=160, anchor="w").pack(side="left")
        self.url_entry6 = ctk.CTkEntry(url_frame, placeholder_text="Dán link video vào đây (YouTube, Bilibili, TikTok...)")
        self.url_entry6.pack(side="left", fill="x", expand=True, padx=5)

        # --- Hàng 3: Thư mục lưu ---
        save_frame = ctk.CTkFrame(self.tab6, fg_color="transparent")
        save_frame.pack(fill="x", padx=10, pady=5)
        ctk.CTkLabel(save_frame, text="Thư mục lưu:", width=160, anchor="w").pack(side="left")
        self.save_dir6 = ctk.StringVar(value=os.path.join(APP_DIR, "Downloads"))
        ctk.CTkEntry(save_frame, textvariable=self.save_dir6).pack(side="left", fill="x", expand=True, padx=5)
        ctk.CTkButton(save_frame, text="Chọn", width=70, command=self.choose_save_dir6).pack(side="left")

        # --- Hàng 4: Nút bấm + Status ---
        btn_frame6 = ctk.CTkFrame(self.tab6, fg_color="transparent")
        btn_frame6.pack(fill="x", padx=10, pady=5)
        self.btn_download6 = ctk.CTkButton(btn_frame6, text="⬇ Bắt Đầu Tải", command=self.start_download6, fg_color="#1a7f37", hover_color="#155d27")
        self.btn_download6.pack(side="left", padx=5)
        self.status_label6 = ctk.CTkLabel(btn_frame6, text="Trạng thái: Đang chờ...")
        self.status_label6.pack(side="left", padx=15)

        # --- Thanh tiến trình ---
        self.progress_bar6 = ctk.CTkProgressBar(self.tab6)
        self.progress_bar6.pack(fill="x", padx=10, pady=5)
        self.progress_bar6.set(0)

        # --- Log box ---
        self.log_box6 = ctk.CTkTextbox(self.tab6, state="disabled", font=("Consolas", 12))
        self.log_box6.pack(fill="both", expand=True, padx=10, pady=5)

    def choose_cookie_file6(self):
        path = filedialog.askopenfilename(filetypes=[("Text Files", "*.txt"), ("All Files", "*.*")])
        if path:
            self.cookie_path6.set(path)

    def choose_save_dir6(self):
        path = filedialog.askdirectory()
        if path:
            self.save_dir6.set(path)

    def append_log6(self, text):
        self.log_box6.configure(state="normal")
        self.log_box6.insert("end", text + "\n")
        self.log_box6.see("end")
        self.log_box6.configure(state="disabled")

    def start_download6(self):
        url = self.url_entry6.get().strip()
        if not url:
            messagebox.showwarning("Thiếu thông tin", "Vui lòng nhập link video!")
            return
        self.btn_download6.configure(state="disabled")
        self.progress_bar6.set(0.05)
        self.log_box6.configure(state="normal")
        self.log_box6.delete("1.0", "end")
        self.log_box6.configure(state="disabled")
        threading.Thread(target=self.process_download6, args=(url,), daemon=True).start()

    def process_download6(self, url):
        try:
            import yt_dlp as ytdlp_module
            save_dir = self.save_dir6.get()
            os.makedirs(save_dir, exist_ok=True)
            cookie_file = self.cookie_path6.get().strip() or None

            self.after(0, lambda: self.status_label6.configure(text="Đang lấy thông tin video..."))
            self.append_log6("[1/3] Đang lấy thông tin video...")

            # Lấy metadata trước
            ydl_opts_info = {"quiet": True, "skip_download": True, "cookiefile": cookie_file}
            with ytdlp_module.YoutubeDL(ydl_opts_info) as ydl:
                info = ydl.extract_info(url, download=False)
            
            original_title = info.get("title", "video")
            self.append_log6(f"   Tiêu đề gốc: {original_title}")
            self.after(0, lambda: self.progress_bar6.set(0.15))

            # Dịch tên video sang tiếng Việt bằng Gemini
            vi_title = original_title
            if self.gemini_api_key:
                self.append_log6("[2/3] Đang dịch tên video sang Tiếng Việt bằng AI...")
                self.after(0, lambda: self.status_label6.configure(text="Đang dịch tên video..."))
                try:
                    client = genai.Client(api_key=self.gemini_api_key)
                    translate_prompt = f"""Dịch tiêu đề video sau sang Tiếng Việt. Chỉ trả về đúng 1 dòng là tên đã dịch, không giải thích gì thêm. Giữ lại các từ đặc biệt, tên riêng nếu cần. Tiêu đề: {original_title}"""
                    resp = client.models.generate_content(model="gemini-2.5-flash", contents=translate_prompt)
                    vi_title = resp.text.strip().strip('"').strip()
                    # Xóa ký tự không hợp lệ trong tên file Windows
                    for ch in r'\/:*?"<>|':
                        vi_title = vi_title.replace(ch, "")
                    self.append_log6(f"   Tên Tiếng Việt: {vi_title}")
                except Exception as e:
                    self.append_log6(f"   [Cảnh báo] Không dịch được tên: {e}. Dùng tên gốc.")
            else:
                self.append_log6("[2/3] Bỏ qua dịch tên (Chưa nhập Gemini API Key).")

            self.after(0, lambda: self.progress_bar6.set(0.2))

            # Chuyển đổi tên sang Tieng_viet_khong_dau, bỏ ký tự đặc biệt
            import unicodedata, re
            vi_title = unicodedata.normalize('NFKD', vi_title).encode('ASCII', 'ignore').decode('utf-8')
            vi_title = re.sub(r'[^\w\s-]', '', vi_title)
            vi_title = re.sub(r'[-\s]+', '_', vi_title).strip('_')
            if not vi_title:
                vi_title = f"video_tai_ve_{int(time.time())}"

            # Tải video với max băng thông (16 luồng)
            self.append_log6(f"[3/3] Bắt đầu tải video (16 luồng song song)...")
            self.after(0, lambda: self.status_label6.configure(text="Đang tải video..."))

            output_template = os.path.join(save_dir, f"{vi_title}.%(ext)s")

            def progress_hook(d):
                if d["status"] == "downloading":
                    total = d.get("total_bytes") or d.get("total_bytes_estimate") or 1
                    downloaded = d.get("downloaded_bytes", 0)
                    speed = d.get("_speed_str", "N/A")
                    eta = d.get("_eta_str", "N/A")
                    frag = d.get("fragment_index")
                    frag_count = d.get("fragment_count")
                    ratio = min(downloaded / total, 1.0)
                    # Map từ 0.2 -> 0.95 cho bước tải
                    self.after(0, lambda r=ratio: self.progress_bar6.set(0.2 + r * 0.75))
                    frag_str = f" | Mảnh: {frag}/{frag_count}" if frag else ""
                    self.after(0, lambda s=speed, e=eta, fs=frag_str: self.status_label6.configure(
                        text=f"Tốc độ: {s} | ETA: {e}{fs}"))
                elif d["status"] == "finished":
                    self.append_log6(f"   ✓ Đã tải xong: {os.path.basename(d['filename'])}")

            ydl_opts = {
                "format": "bestvideo+bestaudio/best",
                "outtmpl": output_template,
                "merge_output_format": "mp4",
                "concurrent_fragment_downloads": 16,
                "http_chunk_size": 5242880,  # Băm nhỏ 5MB/lần để reset giới hạn băng thông của Bilibili
                "progress_hooks": [progress_hook],
                "cookiefile": cookie_file,
                "quiet": True,
                "no_warnings": True,
                "postprocessors": [{
                    "key": "FFmpegVideoConvertor",
                    "preferedformat": "mp4",
                }],
            }

            with ytdlp_module.YoutubeDL(ydl_opts) as ydl:
                ydl.download([url])

            final_path = os.path.join(save_dir, f"{vi_title}.mp4")
            self.after(0, lambda: self.progress_bar6.set(1.0))
            self.after(0, lambda: self.status_label6.configure(text="✅ Tải xong!"))
            self.append_log6(f"\n🎉 HOÀN TẤT! File đã lưu tại:\n   {final_path}")
            messagebox.showinfo("Thành công", f"Đã tải xong!\n\n{final_path}")

        except Exception as e:
            self.after(0, lambda: self.status_label6.configure(text="❌ Có lỗi xảy ra!"))
            self.append_log6(f"\n[LỖI]: {str(e)}")
            messagebox.showerror("Lỗi Tải Video", str(e))
        finally:
            self.after(0, lambda: self.btn_download6.configure(state="normal"))

    # ================= TAB 7: CAPCUT REUP =================

    def setup_tab7(self):
        """Tab 7: Tự động tạo CapCut Draft (Reup) từ video + SRT + nhạc nền."""
        tab = self.tab7
        tab.grid_columnconfigure(0, weight=1)

        # ── Header ───────────────────────────────────────────────────────────
        ctk.CTkLabel(tab, text="🎬 CapCut Reup Builder — Bo Bắp Media",
                     font=ctk.CTkFont(size=16, weight="bold")).pack(pady=(16, 4))
        ctk.CTkLabel(tab, text="Tự động tạo CapCut Draft với sub Việt + nhạc nền + hiệu ứng zoom theo nhịp",
                     font=ctk.CTkFont(size=11), text_color="gray").pack(pady=(0, 12))

        # ── Input frame ───────────────────────────────────────────────────────
        inp_frame = ctk.CTkFrame(tab)
        inp_frame.pack(fill="x", padx=20, pady=4)
        inp_frame.grid_columnconfigure(1, weight=1)

        def make_file_row(parent, row, label, attr_var, filetypes, placeholder):
            ctk.CTkLabel(parent, text=label, width=120, anchor="e").grid(
                row=row, column=0, padx=(12, 8), pady=6, sticky="e")
            entry = ctk.CTkEntry(parent, placeholder_text=placeholder)
            entry.grid(row=row, column=1, padx=(0, 8), pady=6, sticky="ew")
            setattr(self, attr_var, entry)

            def browse(e=entry, ft=filetypes):
                path = filedialog.askopenfilename(filetypes=ft)
                if path:
                    e.delete(0, "end")
                    e.insert(0, path)
            btn = ctk.CTkButton(parent, text="Chọn...", width=80, command=browse)
            btn.grid(row=row, column=2, padx=(0, 12), pady=6)

        make_file_row(inp_frame, 0, "📹 Video sạch:",
                      "tab7_video_entry",
                      [("Video", "*.mp4 *.avi *.mkv *.mov"), ("Tất cả", "*.*")],
                      "Chọn file video từ Tab 5 (_Clean.mp4)...")

        # Row 1: Nút khoanh vùng làm mờ
        self.tab7_rois = []
        roi_frame = ctk.CTkFrame(inp_frame, fg_color="transparent")
        roi_frame.grid(row=1, column=1, columnspan=2, sticky="ew", padx=(0, 12), pady=(0, 6))
        
        self.btn_tab7_roi = ctk.CTkButton(roi_frame, text="🎯 Khoanh vùng cần làm mờ (0)", 
                                          command=self.choose_multiple_rois_tab7,
                                          fg_color="#8d6e63", hover_color="#6d4c41")
        self.btn_tab7_roi.pack(side="left", padx=(0, 10))
        
        self.lbl_tab7_roi = ctk.CTkLabel(roi_frame, text="Tùy chọn: Làm mờ Logo, Watermark, v.v...", text_color="gray")
        self.lbl_tab7_roi.pack(side="left")

        make_file_row(inp_frame, 2, "📝 SRT Việt:",
                      "tab7_srt_entry",
                      [("SRT Subtitle", "*.srt"), ("Tất cả", "*.*")],
                      "Chọn file SRT đã dịch từ Tab 1...")

        make_file_row(inp_frame, 3, "🎵 Nhạc nền:",
                      "tab7_bgm_entry",
                      [("Audio", "*.mp3 *.wav *.m4a *.aac"), ("Tất cả", "*.*")],
                      "Chọn file nhạc nền từ Tab 2...")

        # Draft folder row
        ctk.CTkLabel(inp_frame, text="📂 Draft folder:", width=120, anchor="e").grid(
            row=4, column=0, padx=(12, 8), pady=6, sticky="e")
        self.tab7_draft_entry = ctk.CTkEntry(
            inp_frame, placeholder_text="Tự động detect hoặc chọn thư mục CapCut Draft...")
        self.tab7_draft_entry.grid(row=4, column=1, padx=(0, 8), pady=6, sticky="ew")

        def browse_draft():
            path = filedialog.askdirectory(title="Chọn thư mục CapCut Draft")
            if path:
                self.tab7_draft_entry.delete(0, "end")
                self.tab7_draft_entry.insert(0, path)

        def auto_detect_draft():
            try:
                from capcut_helper import get_capcut_draft_dir
                d = get_capcut_draft_dir()
                if d:
                    self.tab7_draft_entry.delete(0, "end")
                    self.tab7_draft_entry.insert(0, d)
                    messagebox.showinfo("Tìm thấy!", f"Draft folder:\n{d}")
                else:
                    messagebox.showwarning("Không tìm thấy",
                        "Không tìm thấy CapCut Draft folder tự động.\n"
                        "Vui lòng chọn thủ công.")
            except Exception as e:
                messagebox.showerror("Lỗi", str(e))

        draft_btn_frame = ctk.CTkFrame(inp_frame, fg_color="transparent")
        draft_btn_frame.grid(row=4, column=2, padx=(0, 12), pady=6)
        ctk.CTkButton(draft_btn_frame, text="Chọn...", width=70,
                      command=browse_draft).pack(side="left", padx=(0, 4))
        ctk.CTkButton(draft_btn_frame, text="🔍Auto", width=66,
                      fg_color="#2d6a4f", hover_color="#1b4332",
                      command=auto_detect_draft).pack(side="left")

        # ── Info banner ───────────────────────────────────────────────────────
        info_frame = ctk.CTkFrame(tab, fg_color=("#2B2B2B", "#1a1a2e"), corner_radius=10)
        info_frame.pack(fill="x", padx=20, pady=8)
        ctk.CTkLabel(info_frame,
            text="💡  Style Sub Bo Bắp Media: Kem vàng #FFF8E7 | Viền nâu kiếm hiệp #3D1A00\n"
                 "      Size 6px × 130% scale | Căn giữa màn hình | Cách đáy ~12.5%\n"
                 "      Zoom ngẫu nhiên [0.97x–1.07x] tự động sync theo nhịp nhạc (librosa)",
            font=ctk.CTkFont(size=11), justify="left", text_color="#adb5bd").pack(padx=16, pady=10)

        # ── Action button ─────────────────────────────────────────────────────
        self.btn_build7 = ctk.CTkButton(
            tab, text="🎬  TẠO CAPCUT DRAFT",
            height=44, font=ctk.CTkFont(size=14, weight="bold"),
            fg_color="#6a0dad", hover_color="#4a0090",
            command=self.start_capcut_build)
        self.btn_build7.pack(fill="x", padx=20, pady=8)

        # ── Progress ──────────────────────────────────────────────────────────
        self.progress_bar7 = ctk.CTkProgressBar(tab)
        self.progress_bar7.pack(fill="x", padx=20, pady=(0, 4))
        self.progress_bar7.set(0)

        self.status_label7 = ctk.CTkLabel(
            tab, text="Sẵn sàng. Chọn các file rồi nhấn Tạo Draft.",
            font=ctk.CTkFont(size=11), text_color="gray")
        self.status_label7.pack(anchor="w", padx=22)

        # ── Log area ──────────────────────────────────────────────────────────
        self.log_box7 = ctk.CTkTextbox(tab, height=220, font=ctk.CTkFont(family="Consolas", size=11))
        self.log_box7.pack(fill="both", expand=True, padx=20, pady=(4, 16))
        self.log_box7.configure(state="disabled")

    def append_log7(self, msg):
        self.log_box7.configure(state="normal")
        self.log_box7.insert("end", msg + "\n")
        self.log_box7.see("end")
        self.log_box7.configure(state="disabled")

    def choose_multiple_rois_tab7(self):
        video_path = self.tab7_video_entry.get().strip()
        if not video_path or not os.path.exists(video_path):
            messagebox.showerror("Lỗi", "Vui lòng chọn Video gốc hợp lệ trước!")
            return

        import cv2
        cap = cv2.VideoCapture(video_path)
        if not cap.isOpened():
            messagebox.showerror("Lỗi", "Không thể mở video!")
            return

        cap.set(cv2.CAP_PROP_POS_MSEC, 5000)
        ret, frame = cap.read()
        cap.release()

        if not ret:
            messagebox.showerror("Lỗi", "Không thể đọc frame từ video!")
            return

        messagebox.showinfo(
            "Hướng dẫn khoanh vùng",
            "1. Kéo chuột để khoanh vùng chữ/logo.\n"
            "2. Bấm ENTER hoặc SPACE để lưu vùng vừa khoanh.\n"
            "3. Nếu không khoanh gì mà bấm ENTER/SPACE, vòng lặp sẽ KẾT THÚC và lưu toàn bộ.\n"
            "4. Đóng cửa sổ (dấu X) để Hủy bỏ tất cả."
        )

        win_name = "Khoanh nhieu vung"
        cv2.namedWindow(win_name, cv2.WINDOW_NORMAL)
        
        # Thay đổi kích thước cửa sổ nếu video quá to
        h, w = frame.shape[:2]
        scale = min(1280/w, 720/h)
        if scale < 1:
            cv2.resizeWindow(win_name, int(w*scale), int(h*scale))

        rois = []
        while True:
            disp = frame.copy()
            # Vẽ các ROI đã chọn để user nhìn thấy
            for i, (rx, ry, rw, rh) in enumerate(rois):
                cv2.rectangle(disp, (rx, ry), (rx+rw, ry+rh), (0, 0, 255), 2)
                cv2.putText(disp, f"ROI {i+1}", (rx, ry-10), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 0, 255), 2)

            cv2.putText(disp, f"Da khoanh: {len(rois)} vung.", (20, 50), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 255, 0), 2)
            cv2.putText(disp, "Keo chuot khoanh vung moi roi an ENTER/SPACE de Luu.", (20, 90), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 255, 0), 2)
            cv2.putText(disp, "Khong khoanh gi ma an ENTER/SPACE de KET THUC.", (20, 130), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 255, 0), 2)
            cv2.putText(disp, "Click [X] tren cung ben phai de HUY TOAN BO.", (20, 170), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 0, 255), 2)

            bbox = cv2.selectROI(win_name, disp, showCrosshair=True, fromCenter=False)
            
            if cv2.getWindowProperty(win_name, cv2.WND_PROP_VISIBLE) < 1:
                # User closed the window
                rois = []
                break
                
            if bbox == (0, 0, 0, 0):
                # User pressed enter without drawing -> Finish
                break
            else:
                rois.append(bbox)

        try:
            cv2.destroyWindow(win_name)
        except:
            pass

        if len(rois) > 0:
            self.tab7_rois = rois
            self.btn_tab7_roi.configure(text=f"🎯 Đã khoanh ({len(rois)} vùng)", fg_color="green")
            self.lbl_tab7_roi.configure(text="Video sẽ được làm mờ trước khi Reup.")
        else:
            self.tab7_rois = []
            self.btn_tab7_roi.configure(text="🎯 Khoanh vùng cần làm mờ (0)", fg_color="#8d6e63")
            self.lbl_tab7_roi.configure(text="Tùy chọn: Làm mờ Logo, Watermark, v.v...")

    def start_capcut_build(self):
        """Validate inputs và khởi chạy pipeline trong thread riêng."""
        video_path = self.tab7_video_entry.get().strip()
        srt_path   = self.tab7_srt_entry.get().strip()
        bgm_path   = self.tab7_bgm_entry.get().strip()
        draft_dir  = self.tab7_draft_entry.get().strip()

        errors = []
        if not video_path or not os.path.exists(video_path):
            errors.append("• Chưa chọn file video hợp lệ")
        if not srt_path or not os.path.exists(srt_path):
            errors.append("• Chưa chọn file SRT hợp lệ")
        if not bgm_path or not os.path.exists(bgm_path):
            errors.append("• Chưa chọn file nhạc nền hợp lệ")
        if not draft_dir:
            errors.append("• Chưa chọn thư mục CapCut Draft (nhấn 🔍Auto hoặc chọn thủ công)")
        elif not os.path.isdir(draft_dir):
            errors.append(f"• Thư mục Draft không tồn tại:\n  {draft_dir}")

        if errors:
            messagebox.showerror("Thiếu thông tin", "\n".join(errors))
            return

        self.btn_build7.configure(state="disabled")
        self.progress_bar7.set(0)
        self.log_box7.configure(state="normal")
        self.log_box7.delete("1.0", "end")
        self.log_box7.configure(state="disabled")
        self.status_label7.configure(text="Đang xử lý...")

        threading.Thread(
            target=self.process_capcut_reup,
            args=(video_path, srt_path, bgm_path, draft_dir),
            daemon=True
        ).start()

    def process_capcut_reup(self, video_path, srt_path, bgm_path, draft_dir):
        """Pipeline chính chạy trong background thread."""
        try:
            from capcut_helper import build_capcut_draft

            capcut_api_dir = os.path.join(APP_DIR, "capcut_api")
            if not os.path.isdir(capcut_api_dir):
                self.after(0, lambda: messagebox.showerror(
                    "Thiếu CapCutAPI",
                    f"Không tìm thấy thư mục capcut_api tại:\n{capcut_api_dir}\n\n"
                    "Hãy chạy lệnh trong thư mục AudioTool:\n"
                    "  git clone https://github.com/ashreo/CapCutAPI.git capcut_api"
                ))
                return

            def log(msg):
                self.after(0, lambda m=msg: self.append_log7(m))

            def prog(v):
                self.after(0, lambda p=v: self.progress_bar7.set(p))
                self.after(0, lambda p=v: self.status_label7.configure(
                    text=f"Đang xử lý... {int(p * 100)}%"))

            # --- Pre-processing: Blurring Multiple ROIs ---
            if getattr(self, 'tab7_rois', None):
                log(f"🎬 Đang làm mờ {len(self.tab7_rois)} vùng đã chọn bằng FFmpeg (gblur)...")
                prog(0.1)
                import subprocess, cv2
                
                cap = cv2.VideoCapture(video_path)
                vid_w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
                vid_h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
                cap.release()

                filter_chains = []
                splits = len(self.tab7_rois) + 1
                filter_chains.append(f"[0:v]split={splits}[main]" + "".join([f"[ref{i}]" for i in range(len(self.tab7_rois))]))
                
                for i, (x, y, w, h_box) in enumerate(self.tab7_rois):
                    x = int(max(0, min(x, vid_w - 1)))
                    y = int(max(0, min(y, vid_h - 1)))
                    w = int(max(2, min(w, vid_w - x)))
                    h_box = int(max(2, min(h_box, vid_h - y)))
                    
                    x = x - (x % 2)
                    y = y - (y % 2)
                    w = w - (w % 2)
                    h_box = h_box - (h_box % 2)
                    w = max(2, w)
                    h_box = max(2, h_box)
                    
                    # Gán lại cho an toàn ở bước overlay
                    self.tab7_rois[i] = (x, y, w, h_box)
                    filter_chains.append(f"[ref{i}]crop=w={w}:h={h_box}:x={x}:y={y},gblur=sigma=20,format=yuv420p[b{i}]")
                
                filter_chains.append("[main]format=yuv420p[mainf]")
                last_out = "[mainf]"
                for i, (x, y, w, h_box) in enumerate(self.tab7_rois):
                    out_name = f"[tmp{i}]" if i < len(self.tab7_rois) - 1 else "[v]"
                    filter_chains.append(f"{last_out}[b{i}]overlay=x={x}:y={y}{out_name}")
                    last_out = out_name
                    
                filter_str = ";".join(filter_chains)
                blurred_vid_path = video_path.rsplit('.', 1)[0] + "_blurred_reup.mp4"
                
                cmd = [
                    "ffmpeg", "-y", "-i", video_path,
                    "-filter_complex", filter_str,
                    "-map", "[v]", "-map", "0:a?",
                    "-c:v", "libx264", "-preset", "fast", "-crf", "23",
                    "-c:a", "copy",
                    blurred_vid_path
                ]
                
                proc = subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, text=True, encoding='utf-8')
                if proc.returncode != 0:
                    raise Exception(f"Lỗi FFmpeg khi làm mờ nhiều vùng:\n{proc.stderr[-500:]}")
                
                video_path = blurred_vid_path
                log(f"✅ Đã làm mờ xong, lưu tại: {os.path.basename(blurred_vid_path)}")
                prog(0.2)

            build_capcut_draft(
                video_path     = video_path,
                srt_path       = srt_path,
                audio_path     = bgm_path,
                draft_folder   = draft_dir,
                capcut_api_dir = capcut_api_dir,
                log_callback   = log,
                progress_callback = prog,
            )

            self.after(0, lambda: self.status_label7.configure(text="✅ Hoàn tất!"))
            self.after(0, lambda: messagebox.showinfo(
                "Thành công 🎉",
                "CapCut Draft đã tạo thành công!\n\n"
                "Mở CapCut → 'Draft của tôi' → Tìm draft mới nhất → Export."
            ))

        except Exception as e:
            err_msg = str(e)
            self.after(0, lambda m=err_msg: self.append_log7(f"\n[LỖI] {m}"))
            self.after(0, lambda: self.status_label7.configure(text="❌ Có lỗi xảy ra!"))
            self.after(0, lambda m=err_msg: messagebox.showerror("Lỗi CapCut Reup", m))
        finally:
            self.after(0, lambda: self.btn_build7.configure(state="normal"))


if __name__ == "__main__":
    app = App()
    app.mainloop()
