# battle.py - Spamea tecla "3" cada segundo, toggle con "4"
from pynput import keyboard
from pynput.keyboard import Controller, Key
import threading
import time

# ========================
# CONFIGURACIÓN EDITABLE
# ========================
SPAM_KEY = "3"          # ← Cambia esta tecla si quieres otra (ej: "f3", "5", etc.)
TOGGLE_KEY = "-"        # ← Tecla para activar/desactivar
SPAM_INTERVAL = 1.0     # ← Segundos entre cada presión (1 = cada segundo)

# ========================
kbd = Controller()
active = False
running = True

def press_spam_key():
    while running:
        if active:
            kbd.press(SPAM_KEY)
            kbd.release(SPAM_KEY)
            print(f"🔥 Battle spam → '{SPAM_KEY}' presionada")
        time.sleep(SPAM_INTERVAL)

def on_press(key):
    global active
    try:
        if key.char == TOGGLE_KEY.lower():
            active = not active
            status = "ACTIVADO" if active else "DESACTIVADO"
            print(f"⚔️ BATTLE MODE = {status} (tecla '{SPAM_KEY}' cada {SPAM_INTERVAL}s)")
    except AttributeError:
        pass  # Teclas especiales (ctrl, alt, etc.)

def main():
    global running

    print("⚔️ Battle Spam iniciado")
    print(f"   → Presiona '{TOGGLE_KEY}' para activar/desactivar")
    print(f"   → Spamea '{SPAM_KEY}' cada {SPAM_INTERVAL} segundos cuando está activo\n")
    print("   → Presiona Ctrl+C para salir\n")

    # Hilo para spamear la tecla
    spam_thread = threading.Thread(target=press_spam_key, daemon=True)
    spam_thread.start()

    # Listener de teclado
    with keyboard.Listener(on_press=on_press) as listener:
        try:
            listener.join()
        except KeyboardInterrupt:
            print("\n🛑 Battle Spam detenido.")
            running = False

if __name__ == "__main__":
    main()