"""Identify the running build so the launcher does not open an outdated server."""
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent
MANIFEST = ROOT / 'data' / 'runtime.json'


def build_id():
    digest = hashlib.sha256()
    for path in sorted(list(ROOT.glob('*.py')) + list((ROOT / 'static').glob('*'))):
        if path.is_file():
            digest.update(path.name.encode())
            digest.update(path.read_bytes())
    return digest.hexdigest()[:16]


def remembered_port():
    try:
        value = json.loads(MANIFEST.read_text())['port']
        return value if type(value) is int and 1024 <= value <= 65535 else 8768
    except (OSError, ValueError, KeyError, TypeError):
        return 8768
