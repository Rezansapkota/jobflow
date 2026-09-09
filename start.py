"""Start Jobflow, or print its address if it is already running."""
import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
import urllib.request
import threading
import socket
import runtime
import chrome_browser


def main():
    parser = argparse.ArgumentParser(description='Start the local Jobflow workspace.')
    parser.add_argument('--port', type=int, default=None)
    args = parser.parse_args()
    explicit_port = args.port is not None
    args.port = args.port or runtime.remembered_port()
    if not 1024 <= args.port <= 65535:
        parser.error('port must be between 1024 and 65535')
    root = Path(__file__).resolve().parent
    url = f'http://127.0.0.1:{args.port}'
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    try:
        with opener.open(url + '/api/health', timeout=2) as response:
            current = json.load(response)
        if current.get('app') == 'jobflow' and current.get('build') == runtime.build_id():
            print(f'Jobflow is already running at {url}')
            try:
                chrome_browser.open_dashboard(url)
            except (OSError, ValueError) as exc:
                print(f'Open {url} in Google Chrome. {exc}')
            return 0
    except (OSError, ValueError):
        pass
    try:
        with opener.open(url + '/api/state', timeout=2) as response:
            previous = json.load(response)
        if previous.get('running') or previous.get('preparing'):
            print(f'An older server is busy at {url}. Stop its run before launching this update.')
            return 1
    except (OSError, ValueError):
        pass
    # Keep idle older processes intact; select an available port for this build.
    with socket.socket() as probe:
        try:
            probe.bind(('127.0.0.1', args.port))
        except OSError:
            if explicit_port:
                print(f'Port {args.port} is occupied by a different build. Run without --port to select an available port.')
                return 1
            probe.bind(('127.0.0.1', 0))
            args.port = probe.getsockname()[1]
    url = f'http://127.0.0.1:{args.port}'
    env = {**os.environ, 'PORT': str(args.port)}
    print('Keep this terminal open while using Jobflow. Press Ctrl+C to stop it.', flush=True)
    threading.Thread(target=chrome_browser.when_ready, args=(url,), daemon=True).start()
    try:
        return subprocess.call([sys.executable, str(root / 'app.py')], cwd=root, env=env)
    except KeyboardInterrupt:
        return 0


if __name__ == '__main__':
    raise SystemExit(main())
