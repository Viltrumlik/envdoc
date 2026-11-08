"""Har bir til uchun naqsh va har bir buyruq uchun xatti-harakat."""

import importlib.util
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
SCRIPT = os.path.join(HERE, os.pardir, "envdoc.py")

spec = importlib.util.spec_from_file_location("envdoc", SCRIPT)
ed = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ed)


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = os.path.realpath(tempfile.mkdtemp(prefix="envdoc-"))

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def write(self, rel, text):
        path = os.path.join(self.tmp, rel)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            f.write(text)

    def read(self, rel):
        with open(os.path.join(self.tmp, rel), encoding="utf-8") as f:
            return f.read()

    def run_cli(self, *args):
        return subprocess.run([sys.executable, SCRIPT, "-C", self.tmp, *args],
                              capture_output=True, text=True)

    def names(self, *args):
        out = self.run_cli("list", "--json", *args)
        return sorted(json.loads(out.stdout)["variables"])


class DetectionTest(Base):
    def test_python(self):
        self.write("app.py", 'import os\n'
                             'a = os.environ.get("ALPHA")\n'
                             'b = os.environ["BETA"]\n'
                             'c = os.getenv("GAMMA", "x")\n')
        self.assertEqual(self.names(), ["ALPHA", "BETA", "GAMMA"])

    def test_javascript_and_typescript(self):
        self.write("a.js", 'const a = process.env.ALPHA;\n'
                           'const b = process.env["BETA"];\n')
        self.write("b.ts", 'const c = import.meta.env.GAMMA;\n')
        self.assertEqual(self.names(), ["ALPHA", "BETA", "GAMMA"])

    def test_go(self):
        self.write("main.go", 'v := os.Getenv("ALPHA")\n'
                              'w, ok := os.LookupEnv("BETA")\n')
        self.assertEqual(self.names(), ["ALPHA", "BETA"])

    def test_ruby_and_php(self):
        self.write("a.rb", 'a = ENV["ALPHA"]\nb = ENV.fetch("BETA")\n')
        self.write("b.php", '<?php $c = getenv("GAMMA"); $d = $_ENV["DELTA"];\n')
        self.assertEqual(self.names(), ["ALPHA", "BETA", "DELTA", "GAMMA"])

    def test_docker_compose_interpolation(self):
        self.write("docker-compose.yml",
                   'services:\n  app:\n    image: x\n'
                   '    environment:\n      KEY: ${ALPHA}\n      OTHER: ${BETA:-fallback}\n')
        self.assertEqual(self.names(), ["ALPHA", "BETA"])

    def test_lowercase_names_are_not_picked_up(self):
        self.write("a.js", "const a = process.env.nodeEnv;\n")
        self.assertEqual(self.names(), [])

    def test_system_variables_are_hidden_unless_asked_for(self):
        self.write("a.py", 'import os\nh = os.environ["HOME"]\nk = os.environ["MY_KEY"]\n')
        self.assertEqual(self.names(), ["MY_KEY"])
        self.assertEqual(self.names("--all"), ["HOME", "MY_KEY"])

    def test_vendor_folders_are_skipped(self):
        self.write("node_modules/dep/index.js", 'process.env.FROM_DEP;\n')
        self.write(".venv/lib/mod.py", 'os.environ["FROM_VENV"]\n')
        self.write("app.py", 'os.environ["MINE"]\n')
        self.assertEqual(self.names(), ["MINE"])

    def test_minified_lines_are_skipped(self):
        self.write("bundle.js", "x;" * 1200 + 'process.env.HIDDEN;\n')
        self.assertEqual(self.names(), [])

    def test_the_first_location_is_reported(self):
        self.write("app.py", '\n\nos.environ["ALPHA"]\n')
        data = json.loads(self.run_cli("list", "--json").stdout)["variables"]
        self.assertEqual(data["ALPHA"][0]["file"], "app.py")
        self.assertEqual(data["ALPHA"][0]["line"], 3)


class CheckTest(Base):
    def test_a_variable_missing_from_the_example_fails(self):
        self.write("app.py", 'os.environ["ALPHA"]\nos.environ["BETA"]\n')
        self.write(".env.example", "ALPHA=\n")
        out = self.run_cli("check")
        self.assertEqual(out.returncode, 3)
        self.assertIn("BETA", out.stdout)

    def test_everything_documented_passes(self):
        self.write("app.py", 'os.environ["ALPHA"]\n')
        self.write(".env.example", "# comment\nALPHA=some-value\n")
        self.assertEqual(self.run_cli("check").returncode, 0)

    def test_an_extra_entry_passes_unless_strict(self):
        self.write("app.py", 'os.environ["ALPHA"]\n')
        self.write(".env.example", "ALPHA=\nGONE=\n")
        self.assertEqual(self.run_cli("check").returncode, 0)
        self.assertEqual(self.run_cli("check", "--strict").returncode, 3)
        self.assertIn("GONE", self.run_cli("check").stdout)

    def test_a_missing_example_file_is_reported(self):
        self.write("app.py", 'os.environ["ALPHA"]\n')
        out = self.run_cli("check")
        self.assertEqual(out.returncode, 3)
        self.assertIn(".env.example", out.stdout)

    def test_other_example_names_are_recognised(self):
        self.write("app.py", 'os.environ["ALPHA"]\n')
        self.write(".env.sample", "ALPHA=\n")
        self.assertEqual(self.run_cli("check").returncode, 0)

    def test_check_is_the_default_command(self):
        self.write("app.py", 'os.environ["ALPHA"]\n')
        self.assertEqual(self.run_cli().returncode, 3)


class WriteTest(Base):
    def test_missing_variables_are_appended_with_their_location(self):
        self.write("app.py", 'os.environ["ALPHA"]\nos.environ["BETA"]\n')
        self.write(".env.example", "# keep me\nALPHA=already\n")
        self.assertEqual(self.run_cli("write").returncode, 0)
        text = self.read(".env.example")
        self.assertIn("# keep me", text)
        self.assertIn("ALPHA=already", text)   # mavjud qiymat saqlanadi
        self.assertIn("BETA=", text)
        self.assertIn("app.py:2", text)        # qayerdan kelgani yoziladi

    def test_write_creates_the_file_when_there_is_none(self):
        self.write("app.py", 'os.environ["ALPHA"]\n')
        self.run_cli("write")
        self.assertIn("ALPHA=", self.read(".env.example"))

    def test_write_is_a_no_op_when_nothing_is_missing(self):
        self.write("app.py", 'os.environ["ALPHA"]\n')
        self.write(".env.example", "ALPHA=x\n")
        before = self.read(".env.example")
        out = self.run_cli("write")
        self.assertIn("to'liq", out.stdout)
        self.assertEqual(self.read(".env.example"), before)

    def test_write_then_check_is_clean(self):
        self.write("app.py", 'os.environ["ALPHA"]\nos.environ["BETA"]\n')
        self.run_cli("write")
        self.assertEqual(self.run_cli("check").returncode, 0)


class UnitTest(unittest.TestCase):
    def test_the_example_parser_reads_keys_and_ignores_comments(self):
        import tempfile as tf
        fd, path = tf.mkstemp()
        os.close(fd)
        try:
            with open(path, "w", encoding="utf-8") as f:
                f.write("# note\n\nALPHA=1\nBETA = two \nnot a pair\nlower=3\n")
            keys, lines = ed.parse_example(path)
            self.assertEqual(sorted(keys), ["ALPHA", "BETA"])
            self.assertEqual(keys["BETA"], "two")
            self.assertEqual(len(lines), 6)
        finally:
            os.remove(path)

    def test_compare_splits_the_two_directions(self):
        uses = [ed.Use("A", "a.py", 1), ed.Use("B", "a.py", 2)]
        used, missing, unused = ed.compare(uses, {"A": "", "C": ""})
        self.assertEqual(missing, ["B"])
        self.assertEqual(unused, ["C"])
        self.assertEqual(sorted(used), ["A", "B"])


if __name__ == "__main__":
    unittest.main()
