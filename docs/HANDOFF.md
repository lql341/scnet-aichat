# scnet-aichat handoff and new-machine runbook

This document is the operational contract for handing the project to a new laptop,
desktop, coding agent, or operator.

## What the project does

`scnet-aichat` is a local Bash client. It never runs EVA on the local computer.
It uploads prompts over SSH and runs the model on SCNet:

```text
local Bash client
  -> SSH login node
  -> Slurm job in kshdnormal
  -> llama.cpp HIP on Z100/gfx906
  -> EVA GGUF model
```

There are two modes:

- `job`: one Slurm job per question; resources are released after completion.
- `server`: one long-lived Slurm allocation with `llama-server`; later requests reuse
  the loaded model. Stop it explicitly or it consumes resources until walltime expires.

## New-machine prerequisites

### Local machine

Required:

- Bash 3.2 or newer;
- OpenSSH: `ssh`, `scp`;
- standard commands: `awk`, `mktemp`, `install`, `cp`;
- Git or GitHub CLI for a private-repository clone.

Not required locally:

- Python;
- PyTorch;
- ROCm/DTK;
- Docker;
- GPU;
- model files.

### GitHub access

The repository is private. Choose one:

- SSH: `git@github.com:lql341/scnet-aichat.git` and a GitHub SSH key;
- GitHub CLI: `gh auth login` with repository read access.

Do not put a GitHub token in the project config.

### SCNet SSH access

The local SSH profile must reach the SCNet login node. Example:

```sshconfig
Host kseshell
  HostName your-login-host
  User your-user
  Port your-port
  IdentityFile ~/.ssh/id_rsa_scnet
  IdentitiesOnly yes
  ServerAliveInterval 60
```

Verify before installing:

```bash
ssh kseshell 'hostname; printf "HOME=%s\n" "$HOME"; command -v sbatch'
```

### Remote model/runtime prerequisites

The remote account must already contain:

| Item | Default path |
|---|---|
| llama.cpp CLI | `$HOME/eva-k100/llama.cpp-b5046/build-gfx906/bin/llama-cli` |
| llama.cpp server | `$HOME/eva-k100/llama.cpp-b5046/build-gfx906/bin/llama-server` |
| EVA 14B | `$HOME/models/EVA-Qwen2.5-14B-v0.2-GGUF-Q4_0/EVA-Qwen2.5-14B-v0.2-Q4_0.gguf` |
| EVA 32B | `$HOME/models/EVA-Qwen2.5-32B-v0.2-GGUF/EVA-Qwen2.5-32B-v0.2-Q4_K_M.gguf` |

The compute node must provide the DTK modules and a Slurm `kshdnormal` queue.
The worker uses:

- 14B: `dcu:1`, 8 CPU, 27GB;
- 32B: `dcu:4`, 32 CPU, 110GB.

If paths or module names differ, set them in
`~/.config/scnet-aichat/config`.

## Agent one-liner installation

This is the recommended handoff command when the agent already has GitHub SSH access
and the SCNet SSH profile configured. It is idempotent for an existing checkout:

```bash
bash -lc 'set -eu; d="${SCNET_AICHAT_DIR:-$HOME/.local/src/scnet-aichat}"; if [ -d "$d/.git" ]; then git -C "$d" pull --ff-only; else mkdir -p "$(dirname "$d")"; git clone git@github.com:lql341/scnet-aichat.git "$d"; fi; "$d/install.sh" --check --remote-install'
```

If using GitHub CLI instead of an SSH Git remote:

```bash
bash -lc 'set -eu; d="${SCNET_AICHAT_DIR:-$HOME/.local/src/scnet-aichat}"; if [ -d "$d/.git" ]; then git -C "$d" pull --ff-only; else mkdir -p "$(dirname "$d")"; gh repo clone lql341/scnet-aichat "$d"; fi; "$d/install.sh" --check --remote-install'
```

The one-liner:

1. clones or fast-forwards the private repository;
2. installs the local command into `~/.local/bin`;
3. creates `~/.config/scnet-aichat/config` only if it does not exist;
4. uploads the worker and persistent-server Slurm script;
5. runs local tests and remote `doctor`.

It does not download models, overwrite an existing config, cancel jobs, or delete files.

## Manual installation

```bash
git clone git@github.com:lql341/scnet-aichat.git
cd scnet-aichat
./install.sh --check
mkdir -p ~/.config/scnet-aichat
cp config.example ~/.config/scnet-aichat/config
${EDITOR:-vi} ~/.config/scnet-aichat/config
./install.sh --remote-install --no-init-config
```

If `~/.local/bin` is not on `PATH`:

```bash
export PATH="$HOME/.local/bin:$PATH"
```

Then:

```bash
scnet-aichat doctor
scnet-aichat
```

## Daily operations

Occasional questions:

```bash
scnet-aichat ask "请解释张量并行。"
```

Persistent server:

```text
/mode server
/serve status
/serve stop
```

EVA roleplay preset:

```text
/preset eva-rp
/preset show
/preset default
```

Always stop a persistent server when finished:

```text
/serve stop
```

Exiting the local panel alone does not stop a remote job. Use `/cancel JOB_ID` for a
one-shot job or `/serve stop` for a persistent server.

## Upgrade and rollback

Upgrade:

```bash
git -C "$HOME/.local/src/scnet-aichat" pull --ff-only
"$HOME/.local/src/scnet-aichat/install.sh" --remote-install --no-init-config
```

The installer preserves the user config and remote models.

Rollback:

```bash
git -C "$HOME/.local/src/scnet-aichat" log --oneline -5
git -C "$HOME/.local/src/scnet-aichat" checkout <known-good-commit>
"$HOME/.local/src/scnet-aichat/install.sh" --remote-install --no-init-config
```

## Troubleshooting

- `Permission denied (publickey)`: fix the SSH profile/key before running the client.
- `worker=missing`: run `scnet-aichat install`.
- `llama_cli=missing`: set `SCNET_LLAMA_CLI` or build llama.cpp on the remote account.
- `model_14b`/`model_32b` missing: set model paths or stage the GGUF files.
- `PENDING`: inspect `scnet-aichat status JOB_ID`; this is Slurm queueing, not model failure.
- server remains `Waiting`: the persistent allocation has not reached `Running`; stop it
  if the wait is no longer useful.
- server mode and container mode are separate. Container API credentials/resources are
  not required for the Slurm client.

## Security and data boundaries

Local secrets belong in the SSH agent/keychain, not in Git. The repository intentionally
does not contain model files, SSH keys, access tokens, private API credentials, job logs,
or user-specific remote paths.
