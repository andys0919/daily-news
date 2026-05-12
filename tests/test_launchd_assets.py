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
        self.assertIn("export-dashboard-data.sh", content)

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

    def test_dashboard_export_helper_rebuilds_static_site(self):
        script_path = ROOT / "launchd" / "export-dashboard-data.sh"
        self.assertTrue(script_path.exists())
        content = script_path.read_text(encoding="utf-8")
        self.assertIn("--db", content)
        self.assertIn("npm install", content)
        self.assertIn("npm run build", content)


if __name__ == "__main__":
    unittest.main()
