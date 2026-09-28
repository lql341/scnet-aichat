# Contributing

Run the local checks before opening a pull request:

```bash
make test
git diff --check
```

Changes must remain compatible with macOS Bash 3.2 unless the affected component is
explicitly Python-only. OpenAPI code must use the standard library unless a new dependency
is justified and documented.

Never commit AK/SK values, tokens, SSH keys, personal HOME paths, job IDs, prompts,
answers, model weights, or compiled `llama-server` binaries. Tests must use example
accounts such as `alice` and non-routable hosts such as `example.test`.

Mutating OpenAPI and Slurm operations must not be retried automatically after an ambiguous
timeout. Query state first to avoid duplicate jobs.
