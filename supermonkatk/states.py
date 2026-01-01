# states.py
import threading

# =========================
# STATE COMPARTIDO (thread-safe)
# =========================
STATE = {
    "active": False
}

state_lock = threading.Lock()
