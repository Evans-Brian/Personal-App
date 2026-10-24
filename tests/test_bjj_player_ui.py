import unittest
from pathlib import Path


HTML = (Path(__file__).resolve().parents[1] / "static" / "index.html").read_text(encoding="utf-8")


class BJJPlayerUITests(unittest.TestCase):
    def test_hold_target_is_positioned_over_the_video(self):
        self.assertIn('id="bjj-speed-hold" class="bjj-speed-hold"', HTML)

    def test_fast_forward_can_be_set_to_one_point_seven_five(self):
        self.assertIn('<option value="1.75">1.75×</option>', HTML)


if __name__ == "__main__":
    unittest.main()
