import os
import sys
import subprocess

if hasattr(sys.stdout, 'reconfigure'):
    try:
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    except Exception:
        pass

def kill_by_port(port, service_name=""):
    try:
        out = subprocess.check_output(f'netstat -ano | findstr :{port}', shell=True).decode()
        pids = set()
        for line in out.strip().splitlines():
            parts = line.split()
            if len(parts) >= 5 and 'LISTENING' in line:
                pids.add(parts[-1])
        for pid in pids:
            try:
                subprocess.run(f'taskkill /F /PID {pid}', shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                label = f" ({service_name})" if service_name else ""
                print(f'[OK] Stopped process on port {port}{label} (PID: {pid})')
            except Exception:
                pass
    except Exception:
        pass

def main():
    print('Stopping CUA-Sentinel background services...')
    kill_by_port(8000, "Backend API")
    kill_by_port(5173, "Frontend Vite")

    if '--all' in sys.argv or '--with-ollama' in sys.argv:
        kill_by_port(11434, "Ollama AI")
        try:
            subprocess.run('taskkill /F /IM ollama.exe', shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            print('[OK] Stopped Ollama AI service.')
        except Exception:
            pass

    print('[OK] Sentinel shutdown complete.')

if __name__ == '__main__':
    main()
