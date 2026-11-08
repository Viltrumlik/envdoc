#!/usr/bin/env python3
"""envdoc - keep .env.example honest.

Someone adds os.environ["STRIPE_KEY"] on a Friday. The next person clones
the repo, copies .env.example, and the app dies on boot with a KeyError
that explains nothing. Nobody updated the example file, because nothing
made them.

envdoc reads the code, finds the variables it actually uses, and compares
them with what .env.example documents.

    envdoc              # what the code uses, and how the example compares
    envdoc check        # exit 3 if the example is out of date -- for CI
    envdoc write        # update the example, keeping comments and values

Exit codes: 0 in sync, 1 error, 2 usage, 3 out of sync.

Zero dependencies. Python 3.9+.
"""

import argparse
import json
import os
import re
import sys

VERSION = "0.1.0"
EXIT_OK, EXIT_ERROR, EXIT_USAGE, EXIT_DRIFT = 0, 1, 2, 3

EXAMPLE_NAMES = (".env.example", ".env.sample", ".env.template")

SKIP_DIRS = {
    ".git", ".hg", ".svn", "node_modules", ".venv", "venv", "__pycache__",
    "dist", "build", "target", "vendor", ".next", ".nuxt", ".tox",
    ".pytest_cache", ".mypy_cache", "coverage", ".idea", ".vscode",
}
CODE_SUFFIXES = {
    ".py", ".js", ".jsx", ".ts", ".tsx", ".mjs", ".cjs", ".go", ".rb",
    ".php", ".sh", ".bash", ".yml", ".yaml",
}
MAX_BYTES = 2 * 1024 * 1024   # bundle va minified fayllarni o'qimaymiz

# Nom qoidasi: SCREAMING_SNAKE_CASE. Bu shartli, lekin env o'zgaruvchilari
# deyarli har doim shunday yoziladi; busiz process.env.nodeEnv kabi
# narsalar ham tushib, natija shovqinga aylanadi.
NAME = r"[A-Z][A-Z0-9_]{1,63}"

PATTERNS = [
    # Python
    re.compile(r"""os\.environ\.get\(\s*['"](%s)['"]""" % NAME),
    re.compile(r"""os\.environ\[\s*['"](%s)['"]\s*\]""" % NAME),
    re.compile(r"""os\.getenv\(\s*['"](%s)['"]""" % NAME),
    re.compile(r"""environ\.get\(\s*['"](%s)['"]""" % NAME),
    # JavaScript / TypeScript
    re.compile(r"""process\.env\.(%s)\b""" % NAME),
    re.compile(r"""process\.env\[\s*['"](%s)['"]\s*\]""" % NAME),
    re.compile(r"""import\.meta\.env\.(%s)\b""" % NAME),
    # Go
    re.compile(r"""os\.Getenv\(\s*"(%s)""" % NAME),
    re.compile(r"""os\.LookupEnv\(\s*"(%s)""" % NAME),
    # Ruby
    re.compile(r"""ENV\[\s*['"](%s)['"]\s*\]""" % NAME),
    re.compile(r"""ENV\.fetch\(\s*['"](%s)['"]""" % NAME),
    # PHP (Laravel's env() included)
    re.compile(r"""getenv\(\s*['"](%s)['"]""" % NAME),
    re.compile(r"""\$_ENV\[\s*['"](%s)['"]\s*\]""" % NAME),
    re.compile(r"""\benv\(\s*['"](%s)['"]""" % NAME),
    # docker-compose and shell interpolation
    re.compile(r"""\$\{(%s)[:}]""" % NAME),
]


# Tizim bergan o'zgaruvchilar. Kod ularni o'qishi mumkin, lekin ular
# .env.example ga yozilmaydi -- ularni hech kim sozlamaydi.
SYSTEM_VARS = {
    "HOME", "PATH", "USER", "USERNAME", "LOGNAME", "SHELL", "TERM", "LANG",
    "LC_ALL", "PWD", "OLDPWD", "TMPDIR", "TEMP", "TMP", "EDITOR", "VISUAL",
    "HOSTNAME", "DISPLAY", "SHLVL", "CI", "GITHUB_ACTIONS", "RUNNER_OS",
    "COMSPEC", "SYSTEMROOT", "APPDATA", "LOCALAPPDATA", "PROGRAMFILES",
    "PYTHONPATH", "VIRTUAL_ENV", "NODE_ENV",
}


class Use:
    def __init__(self, name, path, line):
        self.name, self.path, self.line = name, path, line


# ---------------------------------------------------------------- scanning


def walk(root):
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS and not d.startswith(".")
                       or d in (".github",)]
        for filename in filenames:
            if os.path.splitext(filename)[1] in CODE_SUFFIXES:
                yield os.path.join(dirpath, filename)


def scan_text(text, path, root):
    uses = []
    rel = os.path.relpath(path, root)
    for number, line in enumerate(text.splitlines(), 1):
        if len(line) > 2000:          # minified; nom izlashdan foyda yo'q
            continue
        for pattern in PATTERNS:
            for name in pattern.findall(line):
                uses.append(Use(name, rel, number))
    return uses


def scan(root, include_system=False):
    uses = []
    for path in walk(root):
        try:
            if os.path.getsize(path) > MAX_BYTES:
                continue
            with open(path, encoding="utf-8", errors="replace") as f:
                text = f.read()
        except OSError:
            continue      # o'qilmasa o'tkazib yuboramiz; bu lint emas
        uses.extend(scan_text(text, path, root))
    if not include_system:
        uses = [u for u in uses if u.name not in SYSTEM_VARS]
    return uses


# ---------------------------------------------------------------- example file


def find_example(root):
    for name in EXAMPLE_NAMES:
        path = os.path.join(root, name)
        if os.path.isfile(path):
            return path
    return None


def parse_example(path):
    """Tartibni saqlab o'qiydi: (kalit -> qiymat) va xom qatorlar."""
    keys, lines = {}, []
    if not path or not os.path.isfile(path):
        return keys, lines
    with open(path, encoding="utf-8") as f:
        for raw in f.read().splitlines():
            lines.append(raw)
            stripped = raw.strip()
            if not stripped or stripped.startswith("#") or "=" not in stripped:
                continue
            key, _, value = stripped.partition("=")
            key = key.strip()
            if re.fullmatch(NAME, key):
                keys[key] = value.strip()
    return keys, lines


def compare(uses, documented):
    used = {}
    for use in uses:
        used.setdefault(use.name, []).append(use)
    missing = sorted(set(used) - set(documented))
    unused = sorted(set(documented) - set(used))
    return used, missing, unused


# ---------------------------------------------------------------- commands


def cmd_list(root, args):
    uses = scan(root, args.all)
    used, _, _ = compare(uses, {})
    if args.json:
        print(json.dumps({"ok": True, "variables": {
            name: [{"file": u.path, "line": u.line} for u in group]
            for name, group in sorted(used.items())}}, indent=2, sort_keys=True))
    elif not used:
        print("no environment variables found in the code")
    else:
        for name in sorted(used):
            first = used[name][0]
            extra = "  (+%d more)" % (len(used[name]) - 1) if len(used[name]) > 1 else ""
            print("%-32s %s:%d%s" % (name, first.path, first.line, extra))
        print("\n%d variables" % len(used))
    return EXIT_OK


def cmd_check(root, args):
    example = find_example(root)
    documented, _ = parse_example(example)
    used, missing, unused = compare(scan(root, args.all), documented)
    rel = os.path.relpath(example, root) if example else EXAMPLE_NAMES[0]

    if args.json:
        print(json.dumps({"ok": not missing and not (unused and args.strict),
                          "example": rel, "missing": missing, "unused": unused,
                          "used": sorted(used)}, indent=2, sort_keys=True))
    else:
        if example is None:
            print("%s does not exist" % rel)
        if missing:
            print("USED IN CODE, NOT DOCUMENTED:")
            for name in missing:
                first = used[name][0]
                print("  %-30s %s:%d" % (name, first.path, first.line))
        if unused:
            print("DOCUMENTED, NOT USED:")
            for name in unused:
                print("  %s" % name)
            print("  (stale, or set outside this codebase)")
        if not missing and not unused:
            print("in sync: %d variables, matching %s" % (len(used), rel))
        elif not missing:
            print("\nnothing missing; %d extra entries" % len(unused))
        else:
            print("\n%d missing, %d extra" % (len(missing), len(unused)))
            print("`envdoc write` adds them")
    if missing:
        return EXIT_DRIFT
    return EXIT_DRIFT if (unused and args.strict) else EXIT_OK


def cmd_write(root, args):
    example = find_example(root) or os.path.join(root, EXAMPLE_NAMES[0])
    documented, lines = parse_example(example if os.path.isfile(example) else None)
    used, missing, _ = compare(scan(root, args.all), documented)
    rel = os.path.relpath(example, root)

    if not missing:
        print("%s is already complete" % rel)
        return EXIT_OK

    out = list(lines)
    if out and out[-1].strip():
        out.append("")
    out.append("# added by envdoc -- fill in the value and a comment")
    for name in missing:
        first = used[name][0]
        out.append("# %s:%d" % (first.path, first.line))
        out.append("%s=" % name)
    with open(example, "w", encoding="utf-8") as f:
        f.write("\n".join(out).rstrip("\n") + "\n")
    print("added %d variables to %s:" % (len(missing), rel))
    for name in missing:
        print("  %s" % name)
    return EXIT_OK


# ---------------------------------------------------------------- cli


def main(argv=None):
    p = argparse.ArgumentParser(
        prog="envdoc",
        description="Compare .env.example with what the code actually uses.")
    p.add_argument("--version", action="version", version="envdoc " + VERSION)
    p.add_argument("-C", dest="root", default=".", metavar="PATH",
                   help="which folder to work in (default: current)")
    sub = p.add_subparsers(dest="command")

    def add(name, help_text, func):
        sp = sub.add_parser(name, help=help_text, description=help_text)
        sp.add_argument("--json", action="store_true")
        sp.add_argument("--all", action="store_true",
                        help="include system variables such as HOME and PATH")
        sp.set_defaults(func=func)
        return sp

    add("list", "variables the code reads", cmd_list)
    sp = add("check", "is the example file up to date (for CI)", cmd_check)
    sp.add_argument("--strict", action="store_true",
                    help="treat extra entries as failures too")
    add("write", "add what is missing to the example file", cmd_write)

    args = p.parse_args(argv)
    root = os.path.abspath(args.root)
    if not os.path.isdir(root):
        print("error: not a folder: %s" % args.root, file=sys.stderr)
        return EXIT_USAGE
    func = getattr(args, "func", None)
    if func is None:                    # buyruqsiz chaqirilsa -- check
        args.json = args.strict = args.all = False
        func = cmd_check
    try:
        return func(root, args)
    except OSError as e:
        print("error: %s" % e, file=sys.stderr)
        return EXIT_ERROR


if __name__ == "__main__":
    sys.exit(main())
