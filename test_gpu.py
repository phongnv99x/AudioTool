import sys, os, site

# Đăng ký NVIDIA DLL dirs
site_packages = site.getsitepackages()
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
            except Exception as e:
                print(f'  WARN: {e}')

print(f'Da dang ky {len(added)} NVIDIA DLL dir(s):')
for d in added:
    print(f'  + {d}')

# Giờ mới import onnxruntime
import onnxruntime as ort
providers = ort.get_available_providers()
print(f'\nProviders: {providers}')
cuda_ok = 'CUDAExecutionProvider' in providers
print(f'CUDA available: {cuda_ok}')

if not cuda_ok:
    print('\n[FAIL] CUDAExecutionProvider van khong hoat dong. Kiem tra log phia tren.')
    sys.exit(1)

# Test RapidOCR voi GPU
from rapidocr_onnxruntime import RapidOCR
import numpy as np
print('\nDang khoi tao RapidOCR voi GPU...')
ocr = RapidOCR(det_use_cuda=True, cls_use_cuda=True, rec_use_cuda=True)
img = np.zeros((80, 300, 3), dtype=np.uint8)
result, _ = ocr(img)
print(f'GPU OCR test: OK')
print('\n=== THANH CONG! GPU OCR da san sang ===')
