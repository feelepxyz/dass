import errno
import http.server
import subprocess
import sys
import threading
from types import SimpleNamespace
from unittest import mock
from urllib.error import HTTPError
from urllib.request import urlopen

import pytest
import watchfiles

from dass import model, photo_render, serve


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


# Argument injection


def test_call_sets_argv_to_the_module_and_arguments_then_restores_it():
    seen = []

    def fake_main() -> None:
        seen.append(list(sys.argv))

    fake_main.__module__ = "fake.module"
    original = list(sys.argv)

    serve.call(fake_main, "--output", "there")

    assert seen == [["fake.module", "--output", "there"]]
    assert sys.argv == original


def test_call_restores_argv_even_when_main_raises():
    def fake_main() -> None:
        raise ValueError("boom")

    original = list(sys.argv)

    with pytest.raises(ValueError, match="boom"):
        serve.call(fake_main, "--flag")

    assert sys.argv == original


# The stager, loaded for real


def test_the_stager_loads_the_real_asset_script(cleared_staging_cache):
    module = serve.staging()

    assert callable(module.main)
    # Proof it is the real script, at the path the docstring names, not a stub.
    assert module.ROOT == serve.ROOT


# Build stages
#
# Each stage borrows another module's own `main()` to write into `build/`; these
# point it at `tmp_path` instead and check what actually landed there.


def test_build_schedules_writes_the_cut_lists_and_the_fastening_audit(
    monkeypatch, tmp_path
):
    monkeypatch.setattr(serve, "BUILD", tmp_path)

    serve.build_schedules()

    assert (tmp_path / "beam-pieces.csv").is_file()
    assert (tmp_path / "cladding-pieces.csv").is_file()
    assert (tmp_path / "stock-cut-plan.csv").is_file()
    assert (tmp_path / "stock-summary.csv").is_file()
    audit = (tmp_path / "fastening-audit.md").read_text()
    assert audit.startswith("# Frame fastening audit")


def test_build_pages_writes_the_guide_and_its_story_pages(monkeypatch, tmp_path):
    monkeypatch.setattr(serve, "BUILD", tmp_path)

    serve.build_pages()

    guide = (tmp_path / "cut-guide.html").read_text()
    assert guide.startswith("<!doctype html>")
    assert (tmp_path / "how-it-started.html").is_file()
    assert (tmp_path / "how-its-going.html").is_file()


def test_build_models_writes_the_two_glb_variants_photo_render_builds(
    monkeypatch, tmp_path, capsys
):
    renders = tmp_path / "renders"
    monkeypatch.setattr(serve, "RENDERS", renders)
    calls = []

    def fake_build_variants(design, output, door_angle, roof_lift_angle):
        calls.append((design, output, door_angle, roof_lift_angle))
        return {"variants": {}, "parts": {}}

    monkeypatch.setattr(photo_render, "build_variants", fake_build_variants)

    serve.build_models()

    assert renders.is_dir()
    assert calls == [
        (model.Design(), renders, photo_render.DOOR_ANGLE, photo_render.ROOF_LIFT_ANGLE)
    ]
    assert f"Wrote the viewer GLB variants to {renders}" in capsys.readouterr().out


def test_stage_assets_runs_the_cached_stager_with_no_extra_arguments(monkeypatch):
    seen_argv = []

    def fake_main() -> None:
        seen_argv.append(list(sys.argv))

    monkeypatch.setattr(serve, "staging", lambda: SimpleNamespace(main=fake_main))

    serve.stage_assets()

    assert seen_argv == [[fake_main.__module__]]


# Stage running


def test_run_stages_builds_only_the_requested_stages_in_declared_order(monkeypatch):
    built = []
    stages = (
        serve.Stage("first", lambda: built.append("first"), ()),
        serve.Stage("second", lambda: built.append("second"), ()),
        serve.Stage("third", lambda: built.append("third"), ()),
    )
    monkeypatch.setattr(serve, "STAGES", stages)

    done = serve.run_stages(["third", "first"])

    assert done is True
    # Declaration order, not request order, and "second" never asked for.
    assert built == ["first", "third"]


def test_run_stages_reports_a_missing_input_and_keeps_going(monkeypatch, capsys):
    def missing_render():
        raise SystemExit("missing render; run render-photo first")

    built = []
    stages = (
        serve.Stage("models", missing_render, ()),
        serve.Stage("pages", lambda: built.append("pages"), ()),
    )
    monkeypatch.setattr(serve, "STAGES", stages)

    done = serve.run_stages(["models", "pages"])

    assert done is False
    assert built == ["pages"]
    assert "models: missing render; run render-photo first" in capsys.readouterr().out


def test_run_stages_reports_an_unexpected_exception_and_keeps_going(
    monkeypatch, capsys
):
    def blows_up():
        raise ValueError("boom")

    built = []
    stages = (
        serve.Stage("schedules", blows_up, ()),
        serve.Stage("pages", lambda: built.append("pages"), ()),
    )
    monkeypatch.setattr(serve, "STAGES", stages)

    done = serve.run_stages(["schedules", "pages"])

    assert done is False
    assert built == ["pages"]
    assert "ValueError: boom" in capsys.readouterr().err


# Rebuilding in a child process


def test_rebuild_runs_the_named_stages_in_a_child_process(monkeypatch):
    calls = []

    def fake_run(args, cwd, check):
        calls.append((args, cwd, check))
        return subprocess.CompletedProcess(args, returncode=0)

    monkeypatch.setattr(serve.subprocess, "run", fake_run)

    ok = serve.rebuild([serve.STAGES[0], serve.STAGES[2]])

    assert ok is True
    ((args, cwd, check),) = calls
    assert args == [
        sys.executable,
        "-m",
        "dass.serve",
        "--build",
        "schedules",
        "models",
    ]
    assert cwd == serve.ROOT
    assert check is False


def test_rebuild_reports_failure_when_the_child_process_exits_nonzero(monkeypatch):
    def fake_run(args, cwd, check):
        return subprocess.CompletedProcess(args, returncode=1)

    monkeypatch.setattr(serve.subprocess, "run", fake_run)

    assert serve.rebuild(serve.STAGES) is False


# Renderer install and photography


def test_install_renderer_skips_npm_install_when_three_is_already_vendored(
    monkeypatch, tmp_path
):
    (tmp_path / "node_modules/three").mkdir(parents=True)
    monkeypatch.setattr(serve, "RENDERER", tmp_path)
    calls = []
    monkeypatch.setattr(serve.subprocess, "run", lambda *a, **k: calls.append((a, k)))

    serve.install_renderer()

    assert calls == []


def test_install_renderer_runs_npm_install_when_three_is_missing(monkeypatch, tmp_path):
    monkeypatch.setattr(serve, "RENDERER", tmp_path)
    calls = []

    def fake_run(args, cwd, check):
        calls.append((args, cwd, check))

    monkeypatch.setattr(serve.subprocess, "run", fake_run)

    serve.install_renderer()

    assert calls == [(["npm", "install"], tmp_path, True)]


def test_photograph_runs_the_renderer_module_in_its_own_process(monkeypatch):
    calls = []

    def fake_run(args, cwd, check):
        calls.append((args, cwd, check))

    monkeypatch.setattr(serve.subprocess, "run", fake_run)

    serve.photograph()

    assert calls == [([sys.executable, "-m", "dass.photo_render"], serve.ROOT, True)]


# Handler branches


def test_a_missing_page_falls_back_to_the_default_handler_and_is_logged(capsys):
    builds = serve.Builds()
    server = serve.listen(0, builds)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        origin = f"http://127.0.0.1:{server.server_port}"
        with pytest.raises(HTTPError) as caught:
            urlopen(f"{origin}/__serve-guide-missing.html", timeout=5)
        assert caught.value.code == 404
        caught.value.close()
    finally:
        server.shutdown()
        thread.join(timeout=2)
        server.server_close()

    # A rebuild re-fetches every asset; only the failure is worth a line.
    assert "404" in capsys.readouterr().err


def test_listen_reraises_a_bind_failure_that_is_not_port_in_use(monkeypatch):
    def refuses(address, handler):
        raise OSError(errno.EACCES, "permission denied")

    monkeypatch.setattr(http.server, "ThreadingHTTPServer", refuses)

    with pytest.raises(OSError) as caught:
        serve.listen(0, serve.Builds())

    assert caught.value.errno == errno.EACCES


# Serving


def test_serve_binds_a_real_port_starts_a_background_thread_and_prints_the_url(
    monkeypatch, capsys
):
    real_listen = serve.listen
    bound: list[http.server.HTTPServer] = []

    def capturing_listen(port, builds, tries=20):
        server = real_listen(port, builds, tries=tries)
        bound.append(server)
        return server

    monkeypatch.setattr(serve, "listen", capturing_listen)
    opened = []
    monkeypatch.setattr(serve.webbrowser, "open", lambda url: opened.append(url))

    before = set(threading.enumerate())
    try:
        builds = serve.serve(0, "cut-guide.html", True)

        assert isinstance(builds, serve.Builds)
        server = bound[0]
        url = f"http://127.0.0.1:{server.server_port}/cut-guide.html"
        assert opened == [url]
        assert f"serving {serve.BUILD} at {url}" in capsys.readouterr().out
    finally:
        for server in bound:
            server.shutdown()
        for thread in set(threading.enumerate()) - before:
            thread.join(timeout=2)
        for server in bound:
            server.server_close()


def test_serve_does_not_open_a_browser_when_asked_not_to(monkeypatch):
    real_listen = serve.listen
    bound: list[http.server.HTTPServer] = []

    def capturing_listen(port, builds, tries=20):
        server = real_listen(port, builds, tries=tries)
        bound.append(server)
        return server

    monkeypatch.setattr(serve, "listen", capturing_listen)
    opened = []
    monkeypatch.setattr(serve.webbrowser, "open", lambda url: opened.append(url))

    before = set(threading.enumerate())
    try:
        serve.serve(0, "cut-guide.html", False)

        assert opened == []
    finally:
        for server in bound:
            server.shutdown()
        for thread in set(threading.enumerate()) - before:
            thread.join(timeout=2)
        for server in bound:
            server.server_close()


# Watching


def test_watch_sources_rebuilds_only_stale_stages_and_lands_only_on_success(
    monkeypatch, capsys
):
    # A noise change no stage reads, then the same real change twice: once
    # rebuilt cleanly, once the child process fails.
    changes = [
        {(1, str(serve.ROOT / "scripts/check-print.mjs"))},
        {(1, str(serve.SRC / "model.py"))},
        {(1, str(serve.SRC / "model.py"))},
    ]

    def fake_watch(*roots):
        assert roots == serve.WATCH
        yield from changes

    monkeypatch.setattr(watchfiles, "watch", fake_watch)
    results = iter([True, False])
    rebuilt = []

    def fake_rebuild(stale):
        rebuilt.append([stage.name for stage in stale])
        return next(results)

    monkeypatch.setattr(serve, "rebuild", fake_rebuild)

    builds = serve.Builds()
    serve.watch_sources(builds)

    assert rebuilt == [
        ["schedules", "pages", "models"],
        ["schedules", "pages", "models"],
    ]
    # Only the successful rebuild lands a build the open page waits on.
    assert builds.count == 1
    output = capsys.readouterr().out
    assert "watching src, web, scripts, docs" in output
    assert "check-print.mjs" not in output
    assert "model.py -> schedules, pages, models" in output


# Entry point


def test_main_build_flag_exits_zero_when_every_requested_stage_builds(monkeypatch):
    monkeypatch.setattr(sys, "argv", ["serve-guide", "--build", "schedules", "pages"])
    seen = []
    monkeypatch.setattr(
        serve, "run_stages", lambda names: (seen.append(list(names)), True)[1]
    )

    with pytest.raises(SystemExit) as caught:
        serve.main()

    assert caught.value.code == 0
    assert seen == [["schedules", "pages"]]


def test_main_build_flag_exits_one_when_a_stage_fails(monkeypatch):
    monkeypatch.setattr(sys, "argv", ["serve-guide", "--build", "models"])
    monkeypatch.setattr(serve, "run_stages", lambda names: False)

    with pytest.raises(SystemExit) as caught:
        serve.main()

    assert caught.value.code == 1


def test_main_serves_and_exits_quietly_on_keyboard_interrupt(
    monkeypatch, tmp_path, capsys
):
    monkeypatch.setattr(sys, "argv", ["serve-guide"])
    monkeypatch.setattr(serve, "BUILD", tmp_path / "build")
    calls = []
    monkeypatch.setattr(
        serve, "install_renderer", lambda: calls.append("install_renderer")
    )
    monkeypatch.setattr(serve, "photograph", lambda: calls.append("photograph"))
    monkeypatch.setattr(
        serve,
        "rebuild",
        lambda stages: (calls.append(("rebuild", list(stages))), True)[1],
    )
    sentinel = object()

    def fake_serve(port, page, open_browser):
        calls.append(("serve", port, page, open_browser))
        return sentinel

    monkeypatch.setattr(serve, "serve", fake_serve)

    def fake_watch(builds):
        calls.append(("watch_sources", builds))
        raise KeyboardInterrupt

    monkeypatch.setattr(serve, "watch_sources", fake_watch)

    serve.main()

    assert (tmp_path / "build").is_dir()
    # --renders was not passed, so photograph() never runs; the default port,
    # page, and open-browser flag are threaded straight through.
    assert calls == [
        "install_renderer",
        ("rebuild", list(serve.STAGES)),
        ("serve", 8000, serve.PAGE, True),
        ("watch_sources", sentinel),
    ]
    assert capsys.readouterr().out == "\n"


def test_main_with_renders_flag_photographs_first_and_threads_port_and_page_through(
    monkeypatch, tmp_path
):
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "serve-guide",
            "--renders",
            "--port",
            "9001",
            "--page",
            "other.html",
            "--no-open",
        ],
    )
    monkeypatch.setattr(serve, "BUILD", tmp_path / "build")
    calls = []
    monkeypatch.setattr(
        serve, "install_renderer", lambda: calls.append("install_renderer")
    )
    monkeypatch.setattr(serve, "photograph", lambda: calls.append("photograph"))
    monkeypatch.setattr(serve, "rebuild", lambda stages: True)
    sentinel = object()

    def fake_serve(port, page, open_browser):
        calls.append(("serve", port, page, open_browser))
        return sentinel

    monkeypatch.setattr(serve, "serve", fake_serve)
    monkeypatch.setattr(
        serve, "watch_sources", lambda builds: calls.append(("watch_sources", builds))
    )

    serve.main()

    assert calls == [
        "install_renderer",
        "photograph",
        ("serve", 9001, "other.html", False),
        ("watch_sources", sentinel),
    ]
