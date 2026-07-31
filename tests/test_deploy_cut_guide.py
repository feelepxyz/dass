from pathlib import Path


def test_deploy_stages_every_generated_public_page():
    script = (Path(__file__).parents[1] / "scripts" / "deploy-cut-guide.sh").read_text()

    assert 'cp build/how-it-started.html "$deploy_dir/how-it-started.html"' in script
    assert 'cp build/how-its-going.html "$deploy_dir/how-its-going.html"' in script
