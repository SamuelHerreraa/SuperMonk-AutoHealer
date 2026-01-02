# main.py (raíz SuperMonk) - Lanzando Ataque + Curación + Battle Spam
import subprocess
import threading
import time
from pathlib import Path

ROOT_DIR = Path(__file__).parent.resolve()

def run_attack():
    attack_dir = ROOT_DIR / "supermonkatk"
    if not attack_dir.exists():
        print("❌ No se encontró la carpeta supermonkatk")
        return

    print("✅ Iniciando MÓDULO ATAQUE...")
    subprocess.Popen(["python", "main.py"], cwd=str(attack_dir))

def run_healing():
    healing_dir = ROOT_DIR / "supermonkhealing"
    if not healing_dir.exists():
        print("❌ No se encontró la carpeta supermonkhealing")
        return

    print("✅ Iniciando MÓDULO CURACIÓN...")
    subprocess.Popen(["python", "main.py"], cwd=str(healing_dir))

def run_battle():
    battle_file = ROOT_DIR / "battle.py"
    if not battle_file.exists():
        print("❌ No se encontró battle.py en la raíz")
        return

    print("✅ Iniciando BATTLE SPAM (tecla '3' cada segundo, toggle con '4')...")
    subprocess.Popen(["python", "battle.py"], cwd=str(ROOT_DIR))

def main():
    print("🚀 SUPERMONK GOD MODE - Lanzando todo el arsenal")
    print("   → supermonkatk (Ataque inteligente)")
    print("   → supermonkhealing (Curación automática)")
    print("   → battle.py (Spam '3' toggle con '4')\n")

    # Lanzar los tres módulos
    thread_attack = threading.Thread(target=run_attack)
    thread_healing = threading.Thread(target=run_healing)
    thread_battle = threading.Thread(target=run_battle)

    thread_attack.start()
    thread_healing.start()
    thread_battle.start()

    print("✅ Los tres módulos lanzados en ventanas separadas.")
    print("   → \\ y * = ataque")
    print("   → Hotkeys del healing = curación")
    print("   → 4 = activar/desactivar spam de '3'\n")
    print("   → Cierra las ventanas o Ctrl+C aquí para detener todo.\n")

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\n🛑 SuperMonk God Mode detenido. ¡Has conquistado Tibia!")

if __name__ == "__main__":
    main()