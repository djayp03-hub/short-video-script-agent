"""Exercise the source entry point from an IDE's non-root working directory."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]


class Startup(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="video-startup-")
        self.addCleanup(self.temp.cleanup)
        self.project = Path(self.temp.name) / "project"
        self.project.mkdir()
        shutil.copy2(ROOT / "run.py", self.project / "run.py")
        for name in ("src", "data"):
            shutil.copytree(ROOT / name, self.project / name, ignore=shutil.ignore_patterns("__pycache__"))
        (self.project / "docs").mkdir()

    def launch(self, *args):
        return subprocess.run([sys.executable, "-B", str(self.project / "run.py"), *args],
            cwd=self.project / "docs", capture_output=True, text=True, encoding="utf-8",
            env={**os.environ, "PYTHONIOENCODING": "utf-8", "PYTHONDONTWRITEBYTECODE": "1"})

    def test_default_data_resolves_from_script_not_ide_working_directory(self):
        destination = Path(self.temp.name) / "explicit-output"
        result = self.launch("--mode", "mock", "--output", str(destination))
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(json.loads((destination / "output.json").read_text(encoding="utf-8"))["status"], "completed")

    def test_click_run_without_arguments_creates_unique_project_outputs(self):
        folders = []
        for _ in range(2):
            result = self.launch()
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            output = Path(json.loads(result.stdout)["output"])
            self.assertEqual(output.parent.resolve(), (self.project / "runs").resolve())
            self.assertTrue((output / "script.md").exists())
            folders.append(output)
        self.assertNotEqual(*folders)


if __name__ == "__main__":
    unittest.main()
