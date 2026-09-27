import os
import sys
import time
import signal
import urllib.request
import subprocess
import webbrowser

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
ROOT_DIR = os.path.dirname(SCRIPT_DIR)
BACKEND_DIR = os.path.join(ROOT_DIR, 'backend')
FRONTEND_DIR = os.path.join(ROOT_DIR, 'frontend')

PYTHON_EXE = os.path.join(ROOT_DIR, '.venv', 'Scripts', 'python.exe')
if not os.path.exists(PYTHON_EXE):
    PYTHON_EXE = sys.executable

OLLAMA_EXE = os.path.expandvars(r'%LOCALAPPDATA%\Programs\Ollama\ollama.exe')
if not os.path.exists(OLLAMA_EXE):
    OLLAMA_EXE = 'ollama'

OLLAMA_URL = 'http://127.0.0.1:11434'
BACKEND_HEALTH_URL = 'http://127.0.0.1:8000/health'
FRONTEND_URL = 'http://127.0.0.1:5173'

spawned_processes = []

def check_url(url, timeout=1.0):
    try:
        req = urllib.request.Request(url, headers={'User-Agent': 'Sentinel-Launcher'})
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.status in (200, 301, 302, 304, 307, 404)
    except Exception:
        return False

def wait_for_service(name, url, max_retries=30, delay=0.5):
    for _ in range(max_retries):
        if check_url(url):
            return True
        time.sleep(delay)
    return False

if hasattr(sys.stdout, 'reconfigure'):
    try:
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    except Exception:
        pass

def cleanup(sig=None, frame=None):
    print('\n[!] Stopping CUA-Sentinel background services...')
    for p in spawned_processes:
        try:
            p.terminate()
        except Exception:
            pass
    time.sleep(0.5)
    for p in spawned_processes:
        try:
            p.kill()
        except Exception:
            pass
    print('[OK] Clean shutdown complete.')
    sys.exit(0)

def main():
    signal.signal(signal.SIGINT, cleanup)
    signal.signal(signal.SIGTERM, cleanup)

    if '--restart' in sys.argv or '-r' in sys.argv:
        print('[!] Restart requested: Stopping existing Sentinel services...')
        try:
            from stop_services import kill_by_port
            kill_by_port(8000, "Backend API")
            kill_by_port(5173, "Frontend Vite")
            time.sleep(1.0)
        except Exception as e:
            print(f'Warning during stop: {e}')

    print('=' * 65)
    print('          >> CUA-SENTINEL AUTONOMOUS AI LAUNCHER <<')
    print('=' * 65)

    # 1. Ollama Service
    print('[1/4] Checking Ollama AI Service...', end=' ', flush=True)
    if check_url(OLLAMA_URL):
        print('ALREADY ACTIVE (Port 11434)')
    else:
        print('STARTING...', end=' ', flush=True)
        try:
            p = subprocess.Popen([OLLAMA_EXE, 'serve'])
            spawned_processes.append(p)
            if wait_for_service('Ollama', OLLAMA_URL, max_retries=20, delay=0.5):
                print('READY (Port 11434)')
            else:
                print('WARNING: Slow startup, continuing...')
        except Exception as e:
            print(f'FAILED: {e}')

    # 2. Sentinel Backend
    print('[2/4] Checking Sentinel Backend (FastAPI)...', end=' ', flush=True)
    if check_url(BACKEND_HEALTH_URL):
        print('ALREADY ACTIVE (Port 8000)')
    else:
        print('STARTING...', end=' ', flush=True)
        try:
            p = subprocess.Popen([PYTHON_EXE, 'main.py'], cwd=BACKEND_DIR)
            spawned_processes.append(p)
            if wait_for_service('Backend', BACKEND_HEALTH_URL, max_retries=30, delay=0.5):
                print('READY (Port 8000)')
            else:
                print('WARNING: Slow startup, continuing...')
        except Exception as e:
            print(f'FAILED: {e}')

    # 3. Frontend Dashboard
    print('[3/4] Checking Frontend Dashboard (Vite)...', end=' ', flush=True)
    if check_url(FRONTEND_URL):
        print('ALREADY ACTIVE (Port 5173)')
    else:
        print('STARTING...', end=' ', flush=True)
        try:
            p = subprocess.Popen(['cmd.exe', '/c', 'npm', 'run', 'dev'], cwd=FRONTEND_DIR)
            spawned_processes.append(p)
            if wait_for_service('Frontend', FRONTEND_URL, max_retries=25, delay=0.5):
                print('READY (Port 5173)')
            else:
                print('WARNING: Slow startup, continuing...')
        except Exception as e:
            print(f'FAILED: {e}')

    # 4. Open in Web Browser
    print(f'[4/4] Launching Web Browser at {FRONTEND_URL}...', end=' ', flush=True)
    webbrowser.open(FRONTEND_URL)
    print('LAUNCHED!')

    print('=' * 65)
    print(f'  [+] Dashboard:   {FRONTEND_URL}')
    print('  [+] Backend API: http://127.0.0.1:8000')
    print('  [+] Ollama AI:   http://127.0.0.1:11434')
    print('=' * 65)
    print('All services are operational. You can minimize this window.')
    print('To shut down all services, press Ctrl+C or close this window.')
    print('=' * 65)

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        cleanup()

if __name__ == '__main__':
    main()
