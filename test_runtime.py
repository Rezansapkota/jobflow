import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
import runtime


class RuntimeTests(unittest.TestCase):
    def test_saved_port_is_validated(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'runtime.json'
            with patch.object(runtime, 'MANIFEST', path):
                self.assertEqual(runtime.remembered_port(), 8768)
                path.write_text('{"port":8778}')
                self.assertEqual(runtime.remembered_port(), 8778)
                for content in ('{"port":true}', '{"port":999999}', 'invalid'):
                    path.write_text(content)
                    self.assertEqual(runtime.remembered_port(), 8768)

    def test_source_change_changes_build(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root / 'static').mkdir()
            path = root / 'app.py'
            path.write_text('first build')
            with patch.object(runtime, 'ROOT', root):
                before = runtime.build_id()
                path.write_text('second build')
                self.assertNotEqual(before, runtime.build_id())
