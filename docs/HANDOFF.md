# scnet-aichat handoff and new-machine runbook

This document is the operational contract for handing the project to a new laptop,
desktop, coding agent, or operator.

## What the project does

`scnet-aichat` is a local client. It never runs EVA on the local computer.
It uploads prompts through SSH or SCNet OpenAPI and runs the model on SCNet:

```text
local client
  -> SSH or OpenAPI
  -> Slurm job in kshdnormal
  -> llama.cpp HIP on Z100/gfx906
  -> EVA GGUF model
```

There are two modes:

- `job`: one Slurm job per question; resources are released after completion.
- `server`: one long-lived Slurm allocation with `llama-server`; later requests reuse
  the loaded model. This mode currently requires SSH. Stop it explicitly or it consumes
  resources until walltime expires.

## New-machine prerequisites

### Local machine

Required:

- Bash 3.2 or newer;
- standard commands: `awk`, `mktemp`, `install`, `cp`;
- Git;
- Python 3 for OpenAPI.

SSH backend additionally requires OpenSSH: `ssh`, `scp`.

Not required locally:

- PyTorch;
- ROCm/DTK;
- Docker;
- GPU;
- model files.

### OpenAPI access

Run `scnet-aichat setup new` and enter the SCNet platform username, AccessKey and
SecretKey. Credentials are stored in macOS Keychain or Linux Secret Service using the
`scnet-hpc-openapi` service. Without a supported credential store, inject
`SCNET_OPENAPI_USER`, `SCNET_OPENAPI_ACCESS_KEY`, and
`SCNET_OPENAPI_SECRET_KEY` through the environment.

Do not put AK, SK, token, SSH private keys, or user-specific paths in the repository
configuration.

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

## Agent installation instruction

Give your coding agent this natural-language instruction:

> Please install or update the public GitHub repository `lql341/scnet-aichat` at
> `~/.local/src/scnet-aichat`. If the directory already exists, fast-forward it; otherwise
> clone it over HTTPS. Then run `install.sh --check` to install the local client and execute
> the tests. Do not connect to SCNet, submit jobs, download models, overwrite existing
> configuration, or delete remote data. Report the installation path and test result.

The instruction:

1. clones or fast-forwards the public repository;
2. installs the local command into `~/.local/bin`;
3. creates `~/.config/scnet-aichat/config` only if it does not exist;
4. installs the OpenAPI helper;
5. runs local tests.

It does not connect to SCNet, download models, overwrite an existing config, cancel jobs,
or delete remote files.

## Manual installation

```bash
git clone https://github.com/lql341/scnet-aichat.git
cd scnet-aichat
./install.sh --check
mkdir -p ~/.config/scnet-aichat
cp config.example ~/.config/scnet-aichat/config
${EDITOR:-vi} ~/.config/scnet-aichat/config
./install.sh --no-init-config
```

If `~/.local/bin` is not on `PATH`:

```bash
export PATH="$HOME/.local/bin:$PATH"
```

Then:

```bash
scnet-aichat setup new
scnet-aichat --backend openapi doctor
scnet-aichat
```

## Daily operations

Occasional questions:

```bash
scnet-aichat ask "请解释张量并行。"
scnet-aichat --backend openapi ask "请解释张量并行。"
```

Persistent server:

```text
/mode server
/serve status
/serve stop
```

Persistent mode is SSH-only. OpenAPI supports one-shot jobs, status, results, and
cancellation.

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
- `OpenAPI credentials are not configured`: run `scnet-aichat setup new` or inject the
  three `SCNET_OPENAPI_*` credential variables.
- `worker=missing`: run `scnet-aichat install`.
- `llama_cli=missing`: set `SCNET_LLAMA_CLI` or build llama.cpp on the remote account.
- `model_14b`/`model_32b` missing: set model paths or stage the GGUF files.
- `PENDING`: inspect `scnet-aichat status JOB_ID`; this is Slurm queueing, not model failure.
- server remains `Waiting`: the persistent allocation has not reached `Running`; stop it
  if the wait is no longer useful.
- server mode and container mode are separate. Container API credentials/resources are
  not required for the Slurm client.

## Security and data boundaries

Local secrets belong in the SSH agent, Keychain, or Secret Service, not in Git. OpenAPI
tokens are ephemeral. User-specific HOME/model paths are discovered locally and redacted
from dry-run/history output. The worker removes prompt/system/runtime input files after
the job; answers and Slurm logs remain in the private remote request directory until the
user removes them.
