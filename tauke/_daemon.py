"""
Daemon entry point: python -m tauke._daemon
Launched as a background subprocess by `tauke worker start`.
"""
from tauke.lib.worker import start_daemon

if __name__ == "__main__":
    start_daemon()
