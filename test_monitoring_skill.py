"""Test the packaged Skill independently of checkout imports and credentials."""

import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from zipfile import ZipFile


class SkillPackageTests(unittest.TestCase):
    def test_packaged_execution(self):
        root = Path(__file__).resolve().parent
        with tempfile.TemporaryDirectory() as tmp:
            archive = Path(tmp) / "skill.zip"
            subprocess.run([sys.executable, str(root / "build_monitoring_skill.py"),
                            "--output", str(archive)], check=True, capture_output=True)
            with ZipFile(archive) as bundle:
                self.assertEqual(set(bundle.namelist()), {
                    "cloud-monitoring/SKILL.md", "cloud-monitoring/scripts/monitor.py",
                    "cloud-monitoring/scripts/requirements.txt",
                    "cloud-monitoring/scripts/tools.py", "cloud-monitoring/scripts/byteplus_tools.py"})
                bundle.extractall(tmp)
            script = Path(tmp) / "cloud-monitoring/scripts/monitor.py"
            result = subprocess.run([sys.executable, str(script), "self-test"],
                                    cwd=tmp, capture_output=True, text=True, check=True)
            data = json.loads(result.stdout)
            self.assertTrue(data["synthetic"])
            self.assertFalse(data["live_query"])
            status = subprocess.run([sys.executable, str(script), "credential-status"],
                                    env={**os.environ, "BYTEPLUS_ACCESS_KEY": "test-secret-not-for-output"},
                                    cwd=tmp, capture_output=True, text=True, check=True)
            self.assertNotIn("test-secret-not-for-output", status.stdout + status.stderr)
            self.assertTrue(json.loads(status.stdout)["environment_variables_present"]["BYTEPLUS_ACCESS_KEY"])
            env = dict(os.environ)
            for key in ("BYTEPLUS_ACCESS_KEY", "BYTEPLUS_SECRET_KEY", "BYTEPLUS_SESSION_TOKEN"):
                env.pop(key, None)
            failed = subprocess.run([sys.executable, str(script), "byteplus-alerts"],
                                    cwd=tmp, env=env, capture_output=True, text=True)
            self.assertEqual(failed.returncode, 1)
            self.assertFalse(json.loads(failed.stdout)["ok"])
            invalid = subprocess.run([sys.executable, str(script), "aws-context", "--args", "[]"],
                                     cwd=tmp, capture_output=True, text=True)
            self.assertEqual(invalid.returncode, 1)
            self.assertFalse(json.loads(invalid.stdout)["ok"])


if __name__ == "__main__":
    unittest.main()
