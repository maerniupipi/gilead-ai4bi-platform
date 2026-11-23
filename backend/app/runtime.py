"""Supervise the API and platform background process in one deployment unit."""
import os
import signal
import subprocess
import sys
import time


def main():
    environment = {**os.environ, "PLATFORM_BACKGROUND_MODE": "external"}
    children = []
    stopping = False

    def stop(signum, frame):
        nonlocal stopping
        stopping = True

    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)
    try:
        # Perform additive schema upgrades and seed data once before starting
        # multiple API workers, which would otherwise race on first startup.
        initializer = subprocess.Popen([sys.executable, "-c", "import app.main"],
            env={**environment, "PLATFORM_SCHEMA_INITIALIZED": "false"})
        children.append(initializer)
        while initializer.poll() is None and not stopping:
            time.sleep(0.1)
        if stopping or initializer.returncode != 0:
            return 0 if stopping else 1
        children.remove(initializer)
        environment["PLATFORM_SCHEMA_INITIALIZED"] = "true"
        api = subprocess.Popen([sys.executable, "-m", "uvicorn", "app.main:app",
            "--host", os.getenv("HOST", "0.0.0.0"), "--port", os.getenv("PORT", "8000"),
            "--workers", os.getenv("UVICORN_WORKERS", "2")], env=environment)
        children.append(api)
        # Background work starts once the API is ready to serve requests.
        import urllib.request
        while api.poll() is None and not stopping:
            try:
                with urllib.request.urlopen(f"http://127.0.0.1:{os.getenv('PORT', '8000')}/health", timeout=2):
                    break
            except Exception:
                time.sleep(1)
        if not stopping and api.poll() is None:
            worker_environment = {**environment, "DB_POOL_SIZE": os.getenv("PLATFORM_WORKER_DB_POOL_SIZE", "5"),
                                  "DB_MAX_OVERFLOW": "1"}
            children.append(subprocess.Popen([sys.executable, "-m", "app.worker"], env=worker_environment))
        while not stopping and all(child.poll() is None for child in children):
            time.sleep(0.5)
        return 0 if stopping else 1
    finally:
        for child in children:
            if child.poll() is None:
                child.terminate()
        for child in children:
            try:
                child.wait(timeout=20)
            except subprocess.TimeoutExpired:
                child.kill()
                child.wait()


if __name__ == "__main__":
    sys.exit(main())
