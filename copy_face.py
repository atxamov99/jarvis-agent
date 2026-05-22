import shutil
from pathlib import Path

src = Path("/home/abdulaziz/.gemini/antigravity-cli/brain/9f0170cb-f5a3-481e-87fd-520692619361/face_1779450312154.png")
dst = Path(__file__).parent / "face.png"

try:
    if src.exists():
        shutil.copy(src, dst)
        print("✅ Ikonka (face.png) muvaffaqiyatli nusxalandi!")
    else:
        print(f"❌ Manba fayl topilmadi: {src}")
except Exception as e:
    print(f"❌ Xatolik yuz berdi: {e}")
