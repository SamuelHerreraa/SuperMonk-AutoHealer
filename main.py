# main.py (en la carpeta raíz SuperMonk) - LANZADOR FINAL DEFINITIVO
import threading
import time
import sys
from pathlib import Path

# Ruta absoluta a la carpeta raíz del proyecto
ROOT_DIR = Path(__file__).parent.resolve()

def run_module(module_name, subfolder):
    module_dir = ROOT_DIR / subfolder
    if not module_dir.exists():
        print(f"❌ Carpeta no encontrada: {module_dir}")
        return False

    # Añadir al path para importaciones
    sys.path.insert(0, str(module_dir))

    try:
        import importlib
        main_mod = importlib.import_module("main")
        if hasattr(main_mod, "main"):
            print(f"✅ {module_name} iniciado correctamente")
            main_mod.main()
            return True
        else:
            print(f"❌ El main.py de {module_name} no tiene función 'main()'")
    except Exception as e:
        print(f"❌ Error al iniciar {module_name}: {e}")
        if "start_overlays" in str(e):
            print("   → Posible causa: archivo overlay_controller.py duplicado o incompatible en esta carpeta")
        if "config" in str(e).lower():
            print("   → Posible causa: falta config_ring.json o config.json en la carpeta img/")
    finally:
        if str(module_dir) in sys.path:
            sys.path.remove(str(module_dir))
    return False

def main():
    print("🚀 SUPERMONK COMPLETO - Iniciando todos los módulos")
    print("   Ataque: supermonkatk")
    print("   Curación: supermonkhealing\n")

    # Lanzar en hilos separados
    thread_attack = threading.Thread(target=run_module, args=("MÓDULO ATAQUE", "supermonkatk"), daemon=True)
    thread_healing = threading.Thread(target=run_module, args=("MÓDULO CURACIÓN", "supermonkhealing"), daemon=True)

    thread_attack.start()
    thread_healing.start()

    print("⏳ Intentando cargar ambos módulos...\n")

    try:
        while thread_attack.is_alive() or thread_healing.is_alive():
            time.sleep(1)
    except KeyboardInterrupt:
        print("\n🛑 SuperMonk detenido manualmente.")

if __name__ == "__main__":
    main()