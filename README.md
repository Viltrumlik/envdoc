<h1 align="center">envdoc</h1>

<p align="center">
  <b>Keep <code>.env.example</code> honest.</b>
</p>

<p align="center">
  <a href="https://github.com/Viltrumlik/envdoc/actions/workflows/ci.yml"><img src="https://github.com/Viltrumlik/envdoc/actions/workflows/ci.yml/badge.svg" alt="CI"></a>
  <img src="https://img.shields.io/badge/dependencies-0-brightgreen" alt="Zero dependencies">
  <a href="LICENSE"><img src="https://img.shields.io/badge/license-MIT-blue" alt="MIT"></a>
</p>

Someone adds `os.environ["STRIPE_KEY"]` on a Friday. The next person clones the repo, copies `.env.example`, and the app dies on boot with a `KeyError` that explains nothing. Nobody updated the example file, because nothing made them.

```bash
envdoc check
```

```
USED IN CODE, NOT DOCUMENTED:
  STRIPE_KEY                     billing/charge.py:14
  SENTRY_DSN                     app/settings.py:91

DOCUMENTED, NOT USED:
  OLD_REDIS_URL
  (stale, or set outside this codebase)

2 missing, 1 extra
`envdoc write` adds them
```

## Commands

| Command | What it does |
|---|---|
| `envdoc list` | Every variable the code reads, and where |
| `envdoc check` | Exit `3` if the example file is out of date — for CI |
| `envdoc write` | Add what's missing, keeping existing values and comments |

`check` is the default, so bare `envdoc` works. Every command takes `--json`.

Exit codes: `0` in sync · `1` error · `2` usage · `3` out of sync.

## What it reads

| Language | Patterns |
|---|---|
| Python | `os.environ.get`, `os.environ[…]`, `os.getenv` |
| JavaScript / TypeScript | `process.env.X`, `process.env["X"]`, `import.meta.env.X` |
| Go | `os.Getenv`, `os.LookupEnv` |
| Ruby | `ENV["X"]`, `ENV.fetch` |
| PHP | `getenv`, `$_ENV[…]`, Laravel's `env()` |
| docker-compose, shell | `${X}` and `${X:-default}` |

It recognises `.env.example`, `.env.sample` and `.env.template`.

## Two deliberate decisions

**Only `SCREAMING_SNAKE_CASE` names count.** This is a convention, not a rule, but without it `process.env.nodeEnv` and every other camelCase property lands in the results and the output turns to noise.

**System variables are hidden.** `HOME`, `PATH`, `USER`, `CI` and the rest are read by code all the time and belong in nobody's `.env.example` — no one configures them. Use `--all` when you want to see them.

## In CI

```yaml
- run: pipx install git+https://github.com/Viltrumlik/envdoc
- run: envdoc check
```

Now a pull request that adds a variable and forgets the example file turns red instead of turning into tomorrow's support question.

## Install

```bash
pipx install git+https://github.com/Viltrumlik/envdoc
```

Or take the file — one script, no dependencies:

```bash
curl -O https://raw.githubusercontent.com/Viltrumlik/envdoc/main/envdoc.py
python3 envdoc.py check
```

## Development

```bash
python3 -m unittest discover -s tests -v
```

CI runs on Ubuntu, macOS and Windows with Python 3.9 through 3.13.

## License

[MIT](LICENSE) © Alisher Muhammadaliyev ([@Viltrumlik](https://github.com/Viltrumlik))
