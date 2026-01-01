# states.py
import threading

STATE = {
    "active": True  # Inicia activo por defecto (puedes cambiarlo)
}

state_lock = threading.Lock()