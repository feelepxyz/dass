"""Build the cut guide, serve it, and rebuild it as its sources change.

    uv run serve-guide                 # build, serve, and open the browser
    uv run serve-guide --port 8080
    uv run serve-guide --renders       # re-photograph the model first (slow)
    uv run serve-guide --no-open

One command in place of the generate-and-stage chain the guide needs: the cut
schedules, the guide and progress pages, the GLB variants the model viewer
loads, and the staged browser assets. It is served over HTTP because the page
reads ES modules, models, and textures that a `file://` page cannot. Saving a
source file rebuilds only the stages that read it, and the open page reloads
itself when the build lands.

Each stage calls the same entry point the shell would, so there is one
definition of what each one writes. The stages run in a child process, not this
one: a saved module only takes effect in an interpreter that has not already
imported it, and a rebuild against the code the server started with is worse
than no rebuild at all. That leaves this process holding nothing heavier than a
socket, so it starts at once and survives a source file that will not import.

The photographs under `build/renders` are the one thing a save never rebuilds.
They are minutes of headless Chromium, so they are made once with `--renders`
(or `uv run render-photo`) and reused.
"""

from __future__ import annotations

import argparse
import errno
import http.server
import importlib.util
import io
import socketserver
import subprocess
import sys
import threading
import traceback
import webbrowser
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from functools import cache, partial
from pathlib import Path
from types import ModuleType
from typing import BinaryIO
from urllib.parse import parse_qs, urlparse

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "src/dass"
BUILD = ROOT / "build"
RENDERS = BUILD / "renders"
RENDERER = ROOT / "web/render"
PAGE = "cut-guide.html"
# The trees a save can land in. Every stage source below sits under one of them,
# and watchfiles skips node_modules and __pycache__ on its own.
WATCH = (ROOT / "src", ROOT / "web", ROOT / "scripts", ROOT / "docs")
# Long enough that an idle page is not asking every second, short enough that a
# proxy or a sleeping laptop never leaves the request hanging for good.
POLL_SECONDS = 25.0


@cache
def staging() -> ModuleType:
    """The asset stager, loaded by path: `scripts/` is not an importable package."""
    source = ROOT / "scripts/build_web_assets.py"
    spec = importlib.util.spec_from_file_location("build_web_assets", source)
    if spec is None or spec.loader is None:
        raise ImportError(f"cannot load the asset stager from {source}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def call(main: Callable[[], None], *arguments: str) -> None:
    """Run a console-script `main()` as if the shell had passed these arguments.

    The stages already own their defaults, their argument parsing, and the list
    of files they write; borrowing them keeps one definition of each.
    """
    argv = sys.argv
    sys.argv = [main.__module__, *arguments]
    try:
        main()
    finally:
        sys.argv = argv


# The stage bodies import their own modules. Only the child process that builds
# ever calls them, and the server is not worth a CadQuery import it never uses.


def build_schedules() -> None:
    from . import cutlists, fastening

    call(cutlists.main, "--output", str(BUILD))
    (BUILD / "fastening-audit.md").write_text(
        fastening.fastening_report(fastening.Design())
    )


def build_pages() -> None:
    from . import build_guide

    call(build_guide.main, "--output", str(BUILD / "cut-guide.html"))


def build_models() -> None:
    """The two GLB variants the page's model viewer loads, and nothing else.

    `render-photo` writes these on its way to the photographs, but the geometry
    alone is a second of CadQuery, so a saved model is worth re-exporting here.
    """
    from . import model, photo_render

    RENDERS.mkdir(parents=True, exist_ok=True)
    photo_render.build_variants(
        model.Design(),
        RENDERS,
        photo_render.DOOR_ANGLE,
        photo_render.ROOF_LIFT_ANGLE,
    )
    print(f"Wrote the viewer GLB variants to {RENDERS}")


def stage_assets() -> None:
    call(staging().main)


@dataclass(frozen=True)
class Stage:
    """One build step, and the sources whose change makes it stale."""

    name: str
    build: Callable[[], None]
    sources: tuple[Path, ...]

    def reads(self, path: Path) -> bool:
        return any(path == source or source in path.parents for source in self.sources)


STAGES = (
    Stage(
        "schedules",
        build_schedules,
        (SRC / "cutlists.py", SRC / "fastening.py", SRC / "model.py"),
    ),
    Stage("pages", build_pages, (SRC,)),
    Stage("models", build_models, (SRC / "model.py",)),
    # The stager reads the gallery tables out of the guide, so a change there
    # can rename or reorder the images it is staging.
    Stage(
        "assets",
        stage_assets,
        (
            ROOT / "web/media",
            ROOT / "docs/original-drawing",
            ROOT / "docs/verification/evolution",
            ROOT / "web/render/materials.mjs",
            ROOT / "scripts/build_web_assets.py",
            SRC / "build_guide.py",
        ),
    ),
)


def stages_for(paths: Iterable[Path]) -> list[Stage]:
    saved = list(paths)
    return [stage for stage in STAGES if any(stage.reads(path) for path in saved)]


def run_stages(names: Iterable[str]) -> bool:
    """Build, reporting rather than raising: a source file that will not import
    should cost the next reload, not the watch loop with it."""
    wanted = list(names)
    done = True
    for stage in STAGES:
        if stage.name not in wanted:
            continue
        try:
            stage.build()
        except SystemExit as stop:
            # How the stages report a missing input, such as an unrendered view.
            print(f"{stage.name}: {stop}")
            done = False
        # Any other failure is reported and stepped over, so that one bad stage
        # does not take the watch loop down with it.
        except Exception:  # noqa: BLE001
            traceback.print_exc()
            done = False
    return done


def rebuild(stages: Iterable[Stage]) -> bool:
    """Run the stale stages in a child, against the sources as they are now."""
    names = [stage.name for stage in stages]
    child = subprocess.run(
        [sys.executable, "-m", "dass.serve", "--build", *names], cwd=ROOT, check=False
    )
    return child.returncode == 0


def install_renderer() -> None:
    """three.js is vendored out of the renderer's own node_modules, so the
    staging step has nothing to copy until they are installed."""
    if (RENDERER / "node_modules/three").exists():
        return
    print("installing the renderer's node modules ...")
    subprocess.run(["npm", "install"], cwd=RENDERER, check=True)


def photograph() -> None:
    """The photo-real views, in the renderer's own process."""
    subprocess.run([sys.executable, "-m", "dass.photo_render"], cwd=ROOT, check=True)


class Builds:
    """The build counter an open page waits on."""

    def __init__(self) -> None:
        self.count = 0
        self._landed = threading.Condition()

    def land(self) -> None:
        with self._landed:
            self.count += 1
            self._landed.notify_all()

    def after(self, seen: int, timeout: float) -> int:
        """The build number once it moves past `seen`, or the current one if
        nothing lands inside `timeout`."""
        with self._landed:
            self._landed.wait_for(lambda: self.count != seen, timeout)
            return self.count


# Held open by the server until the next build lands, so a saved source file
# refreshes the page it is showing without a hand on the keyboard.
RELOAD = """
<script>
(function watch(seen) {
  fetch("/__build?seen=" + seen)
    .then((response) => response.text())
    .then((build) => (build === seen ? watch(seen) : location.reload()))
    .catch(() => setTimeout(() => watch(seen), 1000));
})("%d");
</script>
"""


def inject(page: bytes, build_count: int) -> bytes:
    """Put the reload watcher in the page it is watching."""
    script = (RELOAD % build_count).encode()
    if b"</body>" in page:
        return page.replace(b"</body>", script + b"</body>", 1)
    return page + script


class Guide(http.server.SimpleHTTPRequestHandler):
    """Serves `build/`, holding `/__build` open until the next build lands."""

    def __init__(
        self,
        request: socketserver._RequestType,
        client_address: tuple[str, int] | str,
        server: socketserver.BaseServer,
        *,
        builds: Builds,
    ) -> None:
        # The base class runs the whole request from its constructor.
        self.builds = builds
        super().__init__(request, client_address, server, directory=str(BUILD))

    def do_GET(self) -> None:
        if urlparse(self.path).path == "/__build":
            self.send_build()
            return
        super().do_GET()

    def send_build(self) -> None:
        asked = parse_qs(urlparse(self.path).query).get("seen", ["-1"])[0]
        seen = int(asked) if asked.lstrip("-").isdigit() else -1
        body = str(self.builds.after(seen, POLL_SECONDS)).encode()
        self.send_response(200)
        self.send_header("Content-Type", "text/plain")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def send_head(self) -> io.BytesIO | BinaryIO | None:
        page = Path(self.translate_path(self.path))
        if page.suffix != ".html" or not page.is_file():
            return super().send_head()
        body = inject(page.read_bytes(), self.builds.count)
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        # The page is rewritten under the browser on every build.
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        return io.BytesIO(body)

    def log_request(self, code: int | str = "-", size: int | str = "-") -> None:
        # A rebuild re-fetches every asset; only a failure is worth a line.
        if isinstance(code, int) and code >= 400:
            super().log_request(code, size)


def listen(port: int, builds: Builds, tries: int = 20) -> http.server.HTTPServer:
    """Bind the first free port at or after `port`.

    Binding is the check: a port that answers a probe can still be taken by the
    time the server asks for it.
    """
    handler = partial(Guide, builds=builds)
    for candidate in range(port, port + tries):
        try:
            return http.server.ThreadingHTTPServer(("127.0.0.1", candidate), handler)
        except OSError as error:
            if error.errno != errno.EADDRINUSE:
                raise
            print(f"port {candidate} is already in use")
    raise SystemExit(f"no free port between {port} and {port + tries - 1}")


def serve(port: int, page: str, open_browser: bool) -> Builds:
    builds = Builds()
    server = listen(port, builds)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    url = f"http://127.0.0.1:{server.server_port}/{page}"
    print(f"serving {BUILD} at {url}")
    if open_browser:
        webbrowser.open(url)
    return builds


def watch_sources(builds: Builds) -> None:
    from watchfiles import watch

    print("watching " + ", ".join(str(root.relative_to(ROOT)) for root in WATCH))
    for changes in watch(*WATCH):
        saved = {Path(path) for _, path in changes}
        stale = stages_for(saved)
        if not stale:
            continue
        names = ", ".join(stage.name for stage in stale)
        print(f"\n{', '.join(sorted({path.name for path in saved}))} -> {names}")
        if rebuild(stale):
            builds.land()


def main() -> None:
    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--port",
        type=int,
        default=8000,
        help="preferred port; the next free one is used if it is taken",
    )
    parser.add_argument("--page", default=PAGE, help="page to open")
    parser.add_argument("--no-open", action="store_true", help="do not open a browser")
    parser.add_argument(
        "--renders",
        action="store_true",
        help="re-photograph the model first (minutes; needs node)",
    )
    parser.add_argument(
        "--build",
        nargs="*",
        metavar="STAGE",
        choices=[stage.name for stage in STAGES],
        help="run these stages and exit; how the server builds",
    )
    args = parser.parse_args()
    # Piped into a log or a tee, stdout would otherwise hold each build's report
    # back until the buffer filled.
    # typeshed declares sys.stdout as TextIO; the real object is a TextIOWrapper.
    sys.stdout.reconfigure(line_buffering=True)  # ty: ignore[unresolved-attribute]

    if args.build is not None:
        raise SystemExit(0 if run_stages(args.build) else 1)

    BUILD.mkdir(parents=True, exist_ok=True)
    install_renderer()
    if args.renders:
        photograph()
    rebuild(STAGES)

    builds = serve(args.port, args.page, not args.no_open)
    try:
        watch_sources(builds)
    except KeyboardInterrupt:
        print()


if __name__ == "__main__":
    main()
