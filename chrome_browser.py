"""Open the dashboard in Google Chrome without changing system browser settings."""
import os
from pathlib import Path
import shutil
import subprocess
import time
import urllib.request


def executable():
    candidates = [Path(os.environ.get('PROGRAMFILES', 'C:/Program Files')) / 'Google/Chrome/Application/chrome.exe',
                  Path(os.environ.get('PROGRAMFILES(X86)', 'C:/Program Files (x86)')) / 'Google/Chrome/Application/chrome.exe',
                  Path(os.environ.get('LOCALAPPDATA', '')) / 'Google/Chrome/Application/chrome.exe',
                  Path('/Applications/Google Chrome.app/Contents/MacOS/Google Chrome')]
    for path in candidates:
        if path.is_file():
            return str(path)
    for name in ('google-chrome', 'google-chrome-stable'):
        path = shutil.which(name)
        if path:
            return path
    raise ValueError('Install Google Chrome to open Jobflow and run the job agent.')


def open_dashboard(url):
    subprocess.Popen([executable(), '--new-window', url], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def when_ready(url):
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    for _ in range(40):
        try:
            with opener.open(url + '/api/automation', timeout=1):
                pass
            open_dashboard(url)
            return
        except OSError:
            time.sleep(.5)
        except ValueError as exc:
            print(str(exc), flush=True)
            return
    print(f'Open {url} in Google Chrome once the server is ready.', flush=True)
