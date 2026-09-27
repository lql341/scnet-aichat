# SCNet image-management Dockerfile template.
#
# Before building in the SCNet console, put these files in:
#   $HOME/dockerFileTemp/
#   - llama-server
#   - start-server.sh
#
# Choose an SCNet/DTK-compatible heterogeneous base image in the console.
# The exact base image is site/region-specific; do not use a CUDA-only image.

ARG BASE_IMAGE=ubuntu:22.04
FROM ${BASE_IMAGE}

ARG DEBIAN_FRONTEND=noninteractive
ENV TZ=Asia/Shanghai
SHELL ["/bin/bash", "-c"]

RUN apt-get update && \
    apt-get install -y --no-install-recommends ca-certificates openssh-server sudo curl && \
    rm -rf /var/lib/apt/lists/*

RUN mkdir -p /opt/scnet-aichat/bin /var/run/sshd /root/.ssh
COPY llama-server /opt/scnet-aichat/bin/llama-server
COPY start-server.sh /opt/scnet-aichat/start-server.sh
RUN chmod 755 /opt/scnet-aichat/bin/llama-server /opt/scnet-aichat/start-server.sh && \
    ssh-keygen -A

ENV SCNET_LLAMA_SERVER=/opt/scnet-aichat/bin/llama-server
ENV SCNET_MODEL_PATH=/models/EVA-Qwen2.5-14B-v0.2-Q4_0.gguf
ENV SCNET_PORT=8080

EXPOSE 8080
CMD ["/opt/scnet-aichat/start-server.sh"]
