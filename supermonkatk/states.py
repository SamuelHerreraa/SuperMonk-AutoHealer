import threading

STATE = {
    "active_hunt": False,
    "active_boss": False,
}

state_lock = threading.Lock()