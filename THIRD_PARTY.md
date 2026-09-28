# Third-party components

This repository contains orchestration code and does not distribute model weights or a
compiled inference runtime.

| Component | Use | License handling |
|---|---|---|
| llama.cpp | Remote `llama-cli` and `llama-server` runtime | Upstream MIT license; include its license when redistributing a binary or container image |
| EVA-Qwen2.5 14B/32B | User-supplied GGUF model | Verify the exact model and quantization source before redistribution |
| SCNet OpenAPI | Authentication, files, and Slurm job control | Platform API; users supply their own account credentials |

The top-level MIT license applies only to code and documentation in this repository.
