"""Start Jobflow, or print its address if it is already running."""
import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
import urllib.request


def main():
    parser = argparse.ArgumentParser(description='Start the local Jobflow workspace.')
    parser.add_argument('--port', type=int, default=8768)
    args = parser.parse_args()
    if not 1024 <= args.port <= 65535:
        parser.error('port must be between 1024 and 65535')
    root = Path(__file__).resolve().parent
    url = f'http://127.0.0.1:{args.port}'
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    try:
        with opener.open(url + '/api/automation', timeout=2) as response:
            state = json.load(response)
            if isinstance(state, dict) and 'status' in state and 'events' in state:
                print(f'Jobflow is already running at {url}')
                return 0
    except (OSError, ValueError):
        pass
    env = {**os.environ, 'PORT': str(args.port)}
    print('Keep this terminal open while using Jobflow. Press Ctrl+C to stop it.', flush=True)
    try:
        return subprocess.call([sys.executable, str(root / 'app.py')], cwd=root, env=env)
    except KeyboardInterrupt:
        return 0


if __name__ == '__main__':
    raise SystemExit(main())
