# Persistent llama-server mode

The normal client is deliberately one-question/one-Slurm-job. This directory contains
an alternative persistent service for repeated questions.

## Start a service allocation

```bash
mkdir -p ~/.scnet-aichat/server
scp server/llama-server.slurm kseshell:~/.scnet-aichat/server/

ssh kseshell '
  sbatch \
    --output=$HOME/.scnet-aichat/server/slurm-%j.out \
    --error=$HOME/.scnet-aichat/server/slurm-%j.err \
    --export=SCNET_SERVER_APP_DIR=$HOME/.scnet-aichat \
    $HOME/.scnet-aichat/server/llama-server.slurm
'
```

The service reserves 1 DCU, 8 CPU cores and 27GB for up to 8 hours. It loads the 14B
model once, then serves multiple requests from the same process. Use 4 DCUs, 32 cores
and the 32B model only after changing the `#SBATCH` resources and model path.

## Check and query from the allocation

The most portable first test is to run curl inside the existing allocation:

```bash
JOB_ID="$(ssh kseshell 'cat ~/.scnet-aichat/server/job_id')"

ssh kseshell "
  srun --jobid=$JOB_ID --overlap \
    curl -sS http://127.0.0.1:18080/health
"

ssh kseshell "
  srun --jobid=$JOB_ID --overlap \
    curl -sS http://127.0.0.1:18080/v1/chat/completions \
      -H 'Content-Type: application/json' \
      -d '{\"messages\":[{\"role\":\"user\",\"content\":\"请回答：服务已启动。\"}],\"max_tokens\":32}'
"
```

This avoids opening a compute-node port to the login network. A production client can
wrap these `srun --jobid ... --overlap curl` calls, or use an SSH tunnel if the site
permits direct access to the allocated node.

The Slurm server binds to `127.0.0.1`; it is not exposed on the compute-node network.
Container mode is separate and requires `SCNET_SERVER_API_KEY`.

## Trade-off

Persistent mode pays the model load once and is preferable for many questions in one
session. It consumes the requested DCU/CPU allocation continuously until cancelled or
until the walltime expires:

```bash
JOB_ID="$(ssh kseshell 'cat ~/.scnet-aichat/server/job_id')"
ssh kseshell "scancel '$JOB_ID'"
```

The existing `scnet-aichat` command remains the safer default for occasional questions:
each request is isolated and releases resources after completion.
