import http.server
import threading
from unittest import mock
from urllib.request import urlopen

import pytest

from dass import serve


@pytest.fixture
def cleared_staging_cache():
    """`serve.staging` is cached; clear it before and after the test so a
    patched loader does not leak into another test."""
    serve.staging.cache_clear()
    yield
    serve.staging.cache_clear()


# Staging


def test_a_stager_that_cannot_be_loaded_names_the_path_it_tried(cleared_staging_cache):
    """`scripts/` is loaded by path, and spec_from_file_location answers
    None for a source it has no loader for. Reading `.loader` off that None
    raised an AttributeError that said nothing about the missing file."""
    with (
        mock.patch.object(
            serve.importlib.util, "spec_from_file_location", return_value=None
        ),
        pytest.raises(ImportError) as caught,
    ):
        serve.staging()
    assert "build_web_assets.py" in str(caught.value)


# Stage routing


def test_a_saved_file_runs_only_the_stages_that_read_it():
    def named(paths):
        return [stage.name for stage in serve.stages_for(paths)]

    # The geometry feeds every stage that measures the building.
    assert named([serve.SRC / "model.py"]) == ["schedules", "pages", "models"]
    # The guide is drawn from the model but does not change it, and the
    # stager reads its gallery tables.
    assert named([serve.SRC / "build_guide.py"]) == ["pages", "assets"]
    assert named([serve.SRC / "cutlists.py"]) == ["schedules", "pages"]
    assert named([serve.SRC / "fastening.py"]) == ["schedules", "pages"]
    assert named([serve.ROOT / "web/media/progress/beam-cuts.jpg"]) == ["assets"]


def test_a_saved_file_no_stage_reads_builds_nothing():
    # The watcher covers whole trees, so most of what it reports is noise.
    assert serve.stages_for([serve.ROOT / "scripts/check-print.mjs"]) == []
    assert serve.stages_for([serve.ROOT / "web/render/render.mjs"]) == []
    assert serve.stages_for([]) == []


def test_every_stage_source_sits_under_a_watched_tree():
    # A stage whose sources are outside the watch would never rerun.
    for stage in serve.STAGES:
        for source in stage.sources:
            assert any(root in source.parents for root in serve.WATCH), (
                f"{stage.name} reads unwatched {source}"
            )


def test_the_build_stage_names_are_the_child_process_arguments():
    # `--build` takes these names; a rename has to move together.
    assert [stage.name for stage in serve.STAGES] == [
        "schedules",
        "pages",
        "models",
        "assets",
    ]


# Reload


def test_the_watcher_goes_inside_the_page_it_watches():
    page = serve.inject(b"<html><body><h1>Sheet</h1></body></html>", 7)

    assert b"/__build?seen=" in page
    assert b'})("7");' in page
    assert page.endswith(b"</body></html>")


def test_a_page_without_a_body_close_still_gets_the_watcher():
    assert b"/__build?seen=" in serve.inject(b"<h1>Sheet</h1>", 0)


def test_a_build_releases_the_pages_waiting_on_the_old_number():
    builds = serve.Builds()

    # Nothing has landed, so a page that has seen the current build waits.
    assert builds.after(builds.count, 0.05) == 0
    builds.land()
    assert builds.after(0, 0.05) == 1


# Ports


@pytest.fixture
def listening():
    """Bind a server through `serve.listen`, closing every one bound here."""
    servers: list[http.server.HTTPServer] = []

    def bind(
        port: int, builds: serve.Builds, tries: int = 20
    ) -> http.server.HTTPServer:
        server = serve.listen(port, builds, tries=tries)
        servers.append(server)
        return server

    yield bind
    for server in servers:
        server.server_close()


def test_the_server_steps_past_a_port_that_is_already_serving(listening):
    builds = serve.Builds()
    taken = listening(0, builds)

    moved = listening(taken.server_port, builds, tries=3)

    assert moved.server_port != taken.server_port
    assert moved.server_port < taken.server_port + 3


def test_a_full_range_of_ports_is_reported_rather_than_guessed_at(listening):
    builds = serve.Builds()
    taken = listening(0, builds)

    with pytest.raises(SystemExit):
        serve.listen(taken.server_port, builds, tries=1)


def test_the_server_serves_the_build_directory_and_writes_the_watcher_in():
    probe = serve.BUILD / "__serve-guide-probe.html"
    serve.BUILD.mkdir(parents=True, exist_ok=True)
    probe.write_text("<html><body>sheet</body></html>")
    try:
        builds = serve.Builds()
        server = serve.listen(0, builds)
        try:
            threading.Thread(target=server.serve_forever, daemon=True).start()
            origin = f"http://127.0.0.1:{server.server_port}"

            assert isinstance(server, http.server.ThreadingHTTPServer)
            page = urlopen(f"{origin}/{probe.name}", timeout=5).read()
            assert b"sheet" in page
            assert b"/__build?seen=" in page
            # The counter endpoint answers a page that is behind straight away.
            assert urlopen(f"{origin}/__build?seen=-1", timeout=5).read() == b"0"
        finally:
            server.shutdown()
            server.server_close()
    finally:
        probe.unlink()
