# Architecture and lifecycle

## One-shot mode

```text
scnet-aichat
  ├─ SSH upload prompt files
  ├─ sbatch to kshdnormal
  ├─ worker loads one GGUF into GPU memory
  ├─ llama-cli generates one answer
  └─ worker exits and releases the allocation
```

This mode is the default and is appropriate for occasional requests.

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

The repository includes Dockerfile/server materials, but the Bash client currently uses
Slurm/SSH as its production backend. SCNet container lifecycle APIs are a separate
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

The current account was able to authenticate and query images, resource groups, mount
directories, and instances. A reused terminated test instance accepted restart but
remained `Waiting` for roughly 270 seconds before being stopped. This indicates that
container API authorization works, while container DCU capacity/scheduling still needs
confirmation. No new persistent container was left running.
