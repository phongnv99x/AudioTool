"""
Công cụ càn quét nhạc Pixabay tự động (Vui vẻ không quạu)
Yêu cầu cài đặt: 
1. pip install playwright
2. playwright install chromium
"""

import time
from playwright.sync_api import sync_playwright

def scrape_pixabay_music(keyword="ambient", limit=3):
    with sync_playwright() as p:
        # headless=False để mở trình duyệt lên cho bạn xem nó tự động click "bằng mắt" luôn cho ngầu
        browser = p.chromium.launch(headless=False) 
        
        # Giả lập User-Agent giống người dùng thật nhất có thể để đánh lừa Cloudflare
        context = browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
            viewport={'width': 1280, 'height': 720}
        )
        page = context.new_page()
        
        print(f"🌍 Đang điều khiển trình duyệt truy cập Pixabay với từ khóa: '{keyword}'...")
        page.goto(f"https://pixabay.com/music/search/{keyword.replace(' ', '%20')}/")
        
        # Đợi vài giây cho trang tải xong toàn bộ nội dung và vượt qua bài test Cloudflare (nếu có)
        page.wait_for_timeout(5000) 
        
        print("🔍 Đang đếm số lượng bài hát trên trang...")
        # Tìm tất cả các nút có tên là "Download" hoặc thẻ a chứa nút tải (Pixabay hay dùng aria-label)
        download_buttons = page.locator('button[aria-label="Download"], a[download]')
        count = download_buttons.count()
        
        print(f"🎵 Đã quét thấy {count} nút Tải Xuống!")
        
        downloaded = 0
        for i in range(min(count, limit)):
            print(f"⬇️ Đang ra lệnh click tải bài hát thứ {i+1}...")
            
            try:
                # Bắt sự kiện trình duyệt tải file về
                with page.expect_download(timeout=15000) as download_info:
                    # Click vào nút tải
                    download_buttons.nth(i).click()
                
                download = download_info.value
                file_name = download.suggested_filename
                
                # Lưu file thẳng vào thư mục hiện tại
                download.save_as(file_name)
                print(f"✅ Đã bú thành công file: {file_name}")
                
            except Exception as e:
                print(f"❌ Bài thứ {i+1} bị lỗi hoặc yêu cầu capcha: {str(e)[:50]}...")
            
            # Đợi 3 giây giữa mỗi lần tải để tránh bị Cloudflare khóa mõm
            time.sleep(3)
            downloaded += 1
            
        print(f"\n🎉 KẾT THÚC CHIẾN DỊCH: Đã hack được {downloaded} bài hát mang về kho. Haha!")
        browser.close()

if __name__ == "__main__":
    # Test thử tải 3 bài với từ khóa epic
    scrape_pixabay_music("epic", 3)
