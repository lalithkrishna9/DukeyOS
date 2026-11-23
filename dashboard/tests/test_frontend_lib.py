import shutil
import subprocess
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent


@unittest.skipUnless(shutil.which("node"), "node is not installed (only needed to test the front-end helpers)")
class FrontendLib(unittest.TestCase):
    def test_helpers(self):
        r = subprocess.run(["node", str(HERE / "frontend_lib_test.js")], capture_output=True, text=True, timeout=30)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)

    def test_app_js_parses(self):
        for f in ("lib.js", "app.js"):
            r = subprocess.run(["node", "--check", str(HERE.parent / "frontend" / f)], capture_output=True, text=True, timeout=30)
            self.assertEqual(r.returncode, 0, f + ": " + r.stderr)


if __name__ == "__main__":
    unittest.main()
