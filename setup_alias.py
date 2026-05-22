import os
from pathlib import Path

def setup_jarvis_alias():
    home = Path.home()
    # Loyiha va python interpreter yo'llari
    python_path = "/home/abdulaziz/Рабочий стол/Mark-XXXIX/venv/bin/python"
    main_path = "/home/abdulaziz/Рабочий стол/Mark-XXXIX/main.py"
    
    # Bo'shliqli yo'llar uchun alias o'rniga shell funksiyasi ishlatiladi
    func_line = (
        '\n# Jarvis launcher\n'
        'jarvis() {\n'
        f'    "{python_path}" "{main_path}" "$@"\n'
        '}\n'
    )

    shells = [".bashrc", ".zshrc"]
    updated = []

    for shell in shells:
        shell_path = home / shell
        if shell_path.exists():
            try:
                content = shell_path.read_text(encoding="utf-8", errors="ignore")
                if "jarvis()" not in content and "alias jarvis=" not in content:
                    with open(shell_path, "a", encoding="utf-8") as f:
                        f.write(func_line)
                    updated.append(shell)
                    print(f"✅ {shell} fayliga 'jarvis' buyrug'i qo'shildi.")
                else:
                    print(f"ℹ️ 'jarvis' buyrug'i allaqachon {shell} faylida mavjud.")
            except Exception as e:
                print(f"❌ {shell} fayliga yozishda xatolik: {e}")
                
    if updated:
        print("\n🎉 Muvaffaqiyatli sozlandi!")
        print("O'zgarishlar kuchga kirishi uchun terminalni yopib qayta oching yoki quyidagi buyruqni bering:")
        if ".zshrc" in updated:
            print("👉 source ~/.zshrc")
        else:
            print("👉 source ~/.bashrc")
    else:
        print("\nHech qanday shell konfiguratsiya fayli topilmadi yoki o'zgartirilmadi.")

if __name__ == "__main__":
    setup_jarvis_alias()
