import unittest
from pathlib import Path


class DeployCutGuideTest(unittest.TestCase):
    def test_deploy_stages_every_generated_public_page(self):
        script = (
            Path(__file__).parents[1] / "scripts" / "deploy-cut-guide.sh"
        ).read_text()

        self.assertIn(
            'cp build/how-it-started.html "$deploy_dir/how-it-started.html"',
            script,
        )
        self.assertIn(
            'cp build/how-its-going.html "$deploy_dir/how-its-going.html"',
            script,
        )


if __name__ == "__main__":
    unittest.main()
