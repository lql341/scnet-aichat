# Architecture and lifecycle

## One-shot mode

```text
scnet-aichat
  ├─ SSH backend: scp + sbatch
  ├─ OpenAPI backend: efile upload + structured job submit
  ├─ worker loads one GGUF into GPU memory
  ├─ llama-cli generates one answer
  └─ worker exits and releases the allocation
```

This mode is the default and is appropriate for occasional requests.

OpenAPI credentials are loaded from environment variables, macOS Keychain, or Linux
Secret Service. AK/SK are exchanged for a fresh region token on each invocation; tokens
are not persisted. Region username, scheduler, and HOME are discovered from the selected
region and cached only in a mode-0600 local metadata file. First-use setup presents
authorized region names and highlights Kunshan by default; users never enter or manage
Region IDs. `setup modify` can select future regions without changing the job backend.

## Persistent server mode

```text
scnet-aichat
  ├─ sbatch one server allocation
  ├─ llama-server loads EVA once
  ├─ wait for /health
  └─ each request:
       SSH to login node
       srun --jobid=<server-job> --overlap curl ...
       llama-server on the allocated compute node
```

The compute node is held by Slurm for the server walltime. Exiting the local panel does
not stop it; `/serve stop` is required.

Persistent mode currently requires the SSH backend because requests use `srun --overlap`
inside an existing allocation. The server binds to `127.0.0.1`, not the compute-node
network interface.

The current persistent mode keeps the model process alive, but the Bash client does not
automatically accumulate chat history. For multi-turn context, send previous messages in
the request or use a future local conversation-history layer.

## Resource mapping

| Model | Format | GPUs | CPUs | Memory | Tested decode |
|---|---|---:|---:|---:|---:|
| EVA 14B | Q4_0 | 1 | 8 | 27GB | 26–28 tok/s |
| EVA 32B | Q4_K_M | 4 | 32 | 110GB | 13.7–13.8 tok/s |

Do not change GPU count without changing CPU and memory together. The target queue is
`kshdnormal`; do not use `kshdAI`.

## Container mode boundary

The repository includes Dockerfile/server materials, while the client currently uses
Slurm through SSH or the HPC OpenAPI. SCNet container lifecycle APIs are a separate
integration:

```text
POST /ai/openapi/v2/instance-service/task
POST /ai/openapi/v2/instance-service/task/actions/restart
POST /ai/openapi/v2/instance-service/task/actions/stop
DELETE /ai/openapi/v2/instance-service/task
GET  /ai/openapi/v2/instance-service/task/list
GET  /ai/openapi/v2/instance-service/{id}/detail
GET  /ai/openapi/v2/instance-service/{id}/url
```

Container credentials and account-specific validation results are intentionally not
stored in this repository. The container image requires `SCNET_SERVER_API_KEY` at
runtime and does not expose an unauthenticated inference endpoint.
