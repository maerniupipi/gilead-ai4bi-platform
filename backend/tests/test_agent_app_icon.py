import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.utils.agent_app_icon import DEFAULT_AGENT_APP_ICON, normalize_agent_app_icon


class TestNormalizeAgentAppIcon(unittest.TestCase):
    def test_strips_supplementary_plane(self):
        self.assertEqual(normalize_agent_app_icon("🤖"), DEFAULT_AGENT_APP_ICON)

    def test_truncates_to_four(self):
        self.assertEqual(normalize_agent_app_icon("一二三四五六"), "一二三四")

    def test_keeps_bmp_mixed(self):
        self.assertEqual(normalize_agent_app_icon("A智*"), "A智*")


if __name__ == "__main__":
    unittest.main()
