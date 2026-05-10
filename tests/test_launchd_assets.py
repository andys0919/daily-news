import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent


class LaunchdAssetsTests(unittest.TestCase):
    def test_launchd_wrapper_script_exists(self):
        script_path = ROOT / "launchd" / "run-daily-news.sh"
        self.assertTrue(script_path.exists())
        content = script_path.read_text(encoding="utf-8")
        self.assertIn("ensure-rsshub.sh", content)
        self.assertIn("generate-source-atlas.sh", content)

    def test_launchd_template_exists_with_calendar_schedule(self):
        template_path = ROOT / "launchd" / "com.andy.daily-news.plist.template"
        self.assertTrue(template_path.exists())
        content = template_path.read_text(encoding="utf-8")
        self.assertIn("StartCalendarInterval", content)
        self.assertIn("run-daily-news.sh", content)

    def test_rsshub_helper_script_exists(self):
        script_path = ROOT / "launchd" / "ensure-rsshub.sh"
        self.assertTrue(script_path.exists())

    def test_source_atlas_helper_script_exists(self):
        script_path = ROOT / "launchd" / "generate-source-atlas.sh"
        self.assertTrue(script_path.exists())


if __name__ == "__main__":
    unittest.main()
