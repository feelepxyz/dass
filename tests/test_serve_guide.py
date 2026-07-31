import http.server
import threading
import unittest
from urllib.request import urlopen

from dass import serve


class StageRoutingTest(unittest.TestCase):
    def test_a_saved_file_runs_only_the_stages_that_read_it(self):
        named = lambda paths: [stage.name for stage in serve.stages_for(paths)]

        # The geometry feeds every stage that measures the building.
        self.assertEqual(
            named([serve.SRC / "model.py"]),
            ["schedules", "pages", "models"],
        )
        # The guide is drawn from the model but does not change it, and the
        # stager reads its gallery tables.
        self.assertEqual(named([serve.SRC / "build_guide.py"]), ["pages", "assets"])
        self.assertEqual(named([serve.SRC / "cutlists.py"]), ["schedules", "pages"])
        self.assertEqual(
            named([serve.ROOT / "web/media/progress/beam-cuts.jpg"]),
            ["assets"],
        )

    def test_a_saved_file_no_stage_reads_builds_nothing(self):
        # The watcher covers whole trees, so most of what it reports is noise.
        self.assertEqual(serve.stages_for([serve.ROOT / "scripts/check-print.mjs"]), [])
        self.assertEqual(serve.stages_for([serve.ROOT / "web/render/render.mjs"]), [])
        self.assertEqual(serve.stages_for([]), [])

    def test_every_stage_source_sits_under_a_watched_tree(self):
        # A stage whose sources are outside the watch would never rerun.
        for stage in serve.STAGES:
            for source in stage.sources:
                self.assertTrue(
                    any(root in source.parents for root in serve.WATCH),
                    f"{stage.name} reads unwatched {source}",
                )

    def test_the_build_stage_names_are_the_child_process_arguments(self):
        # `--build` takes these names; a rename has to move together.
        self.assertEqual(
            [stage.name for stage in serve.STAGES],
            ["schedules", "pages", "models", "assets"],
        )


class ReloadTest(unittest.TestCase):
    def test_the_watcher_goes_inside_the_page_it_watches(self):
        page = serve.inject(b"<html><body><h1>Sheet</h1></body></html>", 7)

        self.assertIn(b"/__build?seen=", page)
        self.assertIn(b'})("7");', page)
        self.assertTrue(page.endswith(b"</body></html>"))

    def test_a_page_without_a_body_close_still_gets_the_watcher(self):
        self.assertIn(b"/__build?seen=", serve.inject(b"<h1>Sheet</h1>", 0))

    def test_a_build_releases_the_pages_waiting_on_the_old_number(self):
        builds = serve.Builds()

        # Nothing has landed, so a page that has seen the current build waits.
        self.assertEqual(builds.after(builds.count, 0.05), 0)
        builds.land()
        self.assertEqual(builds.after(0, 0.05), 1)


class PortTest(unittest.TestCase):
    def test_the_server_steps_past_a_port_that_is_already_serving(self):
        builds = serve.Builds()
        taken = serve.listen(0, builds)
        self.addCleanup(taken.server_close)

        moved = serve.listen(taken.server_port, builds, tries=3)
        self.addCleanup(moved.server_close)

        self.assertNotEqual(moved.server_port, taken.server_port)
        self.assertLess(moved.server_port, taken.server_port + 3)

    def test_a_full_range_of_ports_is_reported_rather_than_guessed_at(self):
        builds = serve.Builds()
        taken = serve.listen(0, builds)
        self.addCleanup(taken.server_close)

        with self.assertRaises(SystemExit):
            serve.listen(taken.server_port, builds, tries=1)

    def test_the_server_serves_the_build_directory_and_writes_the_watcher_in(self):
        probe = serve.BUILD / "__serve-guide-probe.html"
        serve.BUILD.mkdir(parents=True, exist_ok=True)
        probe.write_text("<html><body>sheet</body></html>")
        self.addCleanup(probe.unlink)

        builds = serve.Builds()
        server = serve.listen(0, builds)
        self.addCleanup(server.server_close)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        self.addCleanup(server.shutdown)
        origin = f"http://127.0.0.1:{server.server_port}"

        self.assertIsInstance(server, http.server.ThreadingHTTPServer)
        page = urlopen(f"{origin}/{probe.name}", timeout=5).read()
        self.assertIn(b"sheet", page)
        self.assertIn(b"/__build?seen=", page)
        # The counter endpoint answers a page that is behind straight away.
        self.assertEqual(urlopen(f"{origin}/__build?seen=-1", timeout=5).read(), b"0")


if __name__ == "__main__":
    unittest.main()
