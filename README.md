# scnet-aichat

一个 SCNet/Slurm AI 问答面板。支持 SSH 和 SCNet OpenAPI 两种 backend；
默认每个问题提交一个 Slurm 推理作业，SSH backend 另外提供持久
`llama-server` 模式。

项目不在登录节点运行模型，也不包含模型、SSH 私钥、访问令牌、作业日志或个人路径。

## 支持环境

- macOS 自带 Bash 3.2
- Ubuntu
- Debian
- 其他提供 Bash、OpenSSH、`awk`、`mktemp` 的 Unix-like 系统

SSH backend 不需要 Python；OpenAPI backend 和持久模式的 JSON 编码需要 Python 3
（持久模式也可使用 Perl）。

远端目标环境是 Slurm + Hygon DCU/DTK + llama.cpp HIP，内置 14B 单卡和 32B 四卡资源模板。

## 一、安装和首次运行

新机器的完整交接说明见 [`docs/HANDOFF.md`](docs/HANDOFF.md)；架构说明见
[`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md)，容器 API 说明见
[`docs/CONTAINER_API.md`](docs/CONTAINER_API.md)。

### Agent 一句话安装

```bash
bash -lc 'set -eu; d="${SCNET_AICHAT_DIR:-$HOME/.local/src/scnet-aichat}"; if [ -d "$d/.git" ]; then git -C "$d" pull --ff-only; else mkdir -p "$(dirname "$d")"; git clone https://github.com/lql341/scnet-aichat.git "$d"; fi; "$d/install.sh" --check'
```

该命令安装本地客户端、初始化非密钥配置并运行本地测试；不会连接 SCNet、下载模型、
覆盖已有配置或删除远端数据。

### 1. 推荐：配置 OpenAPI

```bash
scnet-aichat setup new
scnet-aichat --backend openapi doctor
scnet-aichat --backend openapi ask "请解释张量并行。"
```

配置面板要求输入 SCNet 平台用户名、AccessKey 和 SecretKey。SecretKey 不回显。
凭据存储规则与 `scnet-hpc` 兼容：

- macOS：保存在 Keychain，service 为 `scnet-hpc-openapi`；
- Linux：有 `secret-tool` 时保存在 Secret Service；
- 没有安全凭据库：不写明文文件，只接受
  `SCNET_OPENAPI_USER`、`SCNET_OPENAPI_ACCESS_KEY`、
  `SCNET_OPENAPI_SECRET_KEY` 环境变量。

每次调用都会用 AK/SK 获取临时区域 token；token 不落盘。区域、scheduler、区域用户名
和 HOME 自动发现，非密钥 metadata 以 `0600` 保存到
`~/.config/scnet-aichat/openapi.json`。

首次 setup 会列出账号已授权的区域，并默认选中昆山；用户只选择区域名称，不输入或
管理 Region ID。选择结果保存在本地私有 metadata 中。未来启用华中一区等其他区域时，
运行 `scnet-aichat setup modify` 重新选择即可。

配置生命周期：

```bash
scnet-aichat setup status
scnet-aichat setup modify
scnet-aichat setup reset               # 只删除本项目 metadata
scnet-aichat setup reset-credentials   # 显式删除共享 AK/SK
```

OpenAPI 当前支持单次作业模式。持久 `llama-server` 依赖 allocation 内的 `srun`，
暂时只支持 SSH backend。

### 2. 可选：配置 SSH profile

客户端只调用 SSH profile，不保存私钥。`~/.ssh/config` 的最小示例：

```sshconfig
Host kseshell
  HostName your-login-host
  User your-username
  Port your-ssh-port
  IdentityFile ~/.ssh/id_rsa_scnet
  IdentitiesOnly yes
  ServerAliveInterval 60
```

先确认 SSH：

```bash
ssh kseshell 'hostname; echo "$HOME"'
```

### 3. 手工获取项目和配置

```bash
git clone https://github.com/lql341/scnet-aichat.git
cd scnet-aichat

mkdir -p ~/.config/scnet-aichat
cp config.example ~/.config/scnet-aichat/config
${EDITOR:-vi} ~/.config/scnet-aichat/config
```

如果 SSH 别名不是 `kseshell`，修改 `SCNET_PROFILE`。如果远端目录不是默认布局，
设置 `SCNET_REMOTE_HOME`、`SCNET_LLAMA_CLI`、`SCNET_MODEL_14B_PATH` 和
`SCNET_MODEL_32B_PATH`。

本机不需要安装 PyTorch、vLLM、ROCm 或 llama.cpp；这些都在远端运行。

如果不想使用安装器，也可以人工执行：

```bash
./tests/test.sh
mkdir -p ~/.local/bin ~/.local/share/scnet-aichat
cp scnet-aichat ~/.local/bin/scnet-aichat
cp -R worker server scripts config.example ~/.local/share/scnet-aichat/
chmod 755 ~/.local/bin/scnet-aichat
```

然后把 `~/.local/bin` 加入 `PATH`，创建并编辑
`~/.config/scnet-aichat/config`。选择 OpenAPI 时先运行
`scnet-aichat setup new`；选择 SSH 时确保 SSH profile 已配置。

### 4. 安装远端 worker 并检查

```bash
./scnet-aichat install
./scnet-aichat doctor
```

`install` 通过当前 backend 上传 Slurm worker；不会上传 GGUF，也不会覆盖模型。

### 5. 打开面板

```bash
./scnet-aichat
```

直接输入问题即可提交作业。面板命令：

```text
/backend ssh
/backend openapi
/model 14b
/model 32b
/mode job
/mode server
/preset eva-rp
/preset default
/preset show
/serve start
/serve status
/serve stop
/tokens 1024
/system You are a concise assistant.
/file prompt.txt
/status JOB_ID
/result JOB_ID
/cancel JOB_ID
/history
/doctor
/install
/quit
```

非交互调用：

```bash
./scnet-aichat ask "请解释张量并行。"
./scnet-aichat --backend openapi ask "请解释张量并行。"
./scnet-aichat --model 32b --max-tokens 256 ask "写一个简短示例。"
./scnet-aichat --mode server --model 14b ask "连续问答的第一问。"
./scnet-aichat --mode server --model 14b --preset eva-rp ask "开始角色扮演。"
./scnet-aichat --no-wait ask "生成报告。"
./scnet-aichat result JOB_ID
```

每次提交都会返回 `JOB_ID`。本地历史保存在 `~/.scnet-aichat/jobs.tsv`。

### EVA 角色扮演预设

在交互面板中启用：

```text
/preset eva-rp
```

查看当前预设：

```text
/preset show
```

恢复普通助手：

```text
/preset default
```

`eva-rp` 会自动设置专用 system prompt，要求模型：

- 遵守角色卡和世界设定；
- 保持人物性格、关系、记忆和场景连续性；
- 不跳出角色、不总结剧情；
- 不替用户决定或描述用户角色的行动；
- 成人向虚构情节中所有参与者必须明确为成年人且自愿；
- 禁止未成年人或年龄含糊的相关情节。

使用示例：

```bash
./scnet-aichat --mode server --model 14b --preset eva-rp ask \
  "角色卡：林岚，32岁，冷静克制的私人秘书。场景：深夜办公室。请以角色身份开始。"
```

### 在面板里使用持久模式

不需要手工执行 `sbatch`。直接启动：

```bash
./scnet-aichat
```

然后输入：

```text
/mode server
```

下一条普通问题会自动：

1. 提交持久 `llama-server` 作业；
2. 等待模型加载完成和 `/health` 就绪；
3. 通过 `srun --jobid ... --overlap` 发送问答；
4. 返回回答内容。

之后连续输入的问题都复用同一个服务。管理命令：

```text
/serve status
/serve stop
```

也可以直接从命令行完成第一次问答：

```bash
./scnet-aichat --mode server --model 14b ask "第一问"
```

切换模型前先停止旧服务：

```text
/serve stop
/model 32b
/mode server
```

如果 14B 服务正在运行，面板会拒绝直接切换到 32B，避免错误复用显存和模型。

## 二、配置

默认配置文件：

```text
~/.config/scnet-aichat/config
```

也可以通过 `SCNET_AICHAT_CONFIG` 指定其他文件。所有选项见
[`config.example`](config.example)。

配置文件使用受限的 `SCNET_*=value` 解析器，不会作为 Shell 脚本执行；包含
`ACCESS_KEY`、`SECRET_KEY`、`API_KEY`、`TOKEN` 或 `PASSWORD` 的键会被拒绝。

如果未设置 `SCNET_REMOTE_HOME`，SSH backend 会通过 SSH 读取远端 `$HOME`；
OpenAPI backend 会从区域中心信息发现 HOME。随后推导：

- 远端应用目录：`$HOME/.scnet-aichat`
- llama.cpp：`$HOME/eva-k100/llama.cpp-b5046/build-gfx906/bin/llama-cli`
- 模型目录：`$HOME/models/...`

默认资源必须保持 CPU/DCU 匹配：

| 模型 | DCU | CPU | 内存 | 默认格式 |
|---|---:|---:|---:|---|
| 14B | 1 | 8 | 27GB | Q4_0 |
| 32B | 4 | 32 | 110GB | Q4_K_M |

默认分区为 `kshdnormal`，项目不会自动切换到 `kshdAI`。

## 三、单次作业模式的实际耗时

默认模式是一问一作业。端到端时间包括 Slurm 排队、进程启动、模型加载、prompt
处理和生成；不是只有生成速度。

在已验证的昆山 Z100/gfx906 环境中：

- 14B Q4_0：模型加载约 **44–50 秒**，生成约 **26–28 tok/s**；
- 32B Q4_K_M：模型加载约 **98 秒**，生成约 **13.7–13.8 tok/s**。

因此频繁问答时，每个问题都会重复付出模型加载时间，连续对话体验会很差。

## 四、频繁问答：持久 llama-server

频繁问答推荐保持一个 Slurm 作业运行，让 `llama-server` 只加载一次模型。脚本位于
[`server/llama-server.slurm`](server/llama-server.slurm)。

持久模式当前要求 `--backend ssh`。服务默认只监听计算节点的
`127.0.0.1`，客户端通过 allocation 内的 `srun` 调用。

### 1. 编译 server

如果共享存储中已有本项目验证过的 llama.cpp 源码：

```bash
scp server/build-server.sh kseshell:~/.scnet-aichat/server/
ssh kseshell 'bash ~/.scnet-aichat/server/build-server.sh'
```

也可以直接在已有源码目录执行：

```bash
ssh kseshell '
  cd ~/eva-k100/llama.cpp-b5046 &&
  cmake -S . -B build-gfx906 \
    -DGGML_HIP=ON -DAMDGPU_TARGETS=gfx906 \
    -DLLAMA_BUILD_SERVER=ON -DLLAMA_BUILD_TESTS=OFF &&
  cmake --build build-gfx906 --target llama-server -j8
'
```

计算节点离线不影响这一步：源码和 DTK module 已在共享存储，编译不需要下载。

### 2. 提交常驻服务

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

脚本默认申请 1 DCU、8 CPU、27GB，运行 14B，最长 8 小时。32B 需要改成 4 DCU、
32 CPU、110GB，并设置 32B 模型路径。

### 3. 健康检查和问答

```bash
JOB_ID="$(ssh kseshell 'cat ~/.scnet-aichat/server/job_id')"

ssh kseshell \
  "srun --jobid=$JOB_ID --overlap curl -fsS http://127.0.0.1:18080/health"

ssh kseshell "
  srun --jobid=$JOB_ID --overlap \
    curl -sS http://127.0.0.1:18080/v1/chat/completions \
      -H 'Content-Type: application/json' \
      -d '{\"messages\":[{\"role\":\"user\",\"content\":\"请解释张量并行。\"}],\"max_tokens\":128}'
"
```

`srun --jobid ... --overlap` 复用已有 allocation，不会每个问题重新申请 DCU。
验证中 14B 服务首次加载约 50 秒，之后生成约 27.7 tok/s。

默认服务只监听计算节点；用 `srun` 访问最稳妥。如果站点允许登录节点转发到计算节点，
也可以使用 SSH 隧道。服务结束后取消：

```bash
ssh kseshell "scancel $(ssh kseshell 'cat ~/.scnet-aichat/server/job_id')"
```

持久模式的代价是：即使没有请求，也会持续占用 Slurm 资源直到取消或 walltime 到期。

## 五、容器镜像部署

仓库提供 [`Dockerfile`](Dockerfile)、[`server/start-server.sh`](server/start-server.sh)
和 [`server/README.md`](server/README.md) 作为 SCNet 容器实例材料。

SCNet Dockerfile 构建要求 `COPY`/`ADD` 的文件放到用户家目录 `dockerFileTemp`。先准备：

```bash
mkdir -p ~/dockerFileTemp
scp /path/to/llama-server kseshell:~/dockerFileTemp/llama-server
ssh kseshell 'mkdir -p ~/dockerFileTemp/server'
scp server/start-server.sh kseshell:~/dockerFileTemp/server/start-server.sh
scp Dockerfile kseshell:~/dockerFileTemp/Dockerfile
```

然后在 SCNet 容器服务中选择 Dockerfile 构建，并配置：

- 与 Hygon DCU/DTK 兼容的基础镜像；
- 启动命令 `/opt/scnet-aichat/start-server.sh`；
- 服务端口 `8080`；
- GGUF 通过持久存储挂载到 `/models`；
- `SCNET_MODEL_PATH` 指向挂载后的 GGUF；
- 必须通过安全环境注入设置 `SCNET_SERVER_API_KEY`。

不要把 GGUF 权重提交到 Git 或 Docker build context。计算节点不能联网时，应在 SCNet
镜像构建服务或可联网的构建环境完成构建；容器运行时只使用已打包依赖、挂载模型和
宿主机提供的 DTK/HYHAL 设备运行时。

当前仓库不包含 40MB 左右的 `llama-server` 二进制或几十 GB 模型，因此没有生成
Docker save 大镜像包；SCNet Dockerfile 构建材料已经准备好。当前环境本机和登录节点
没有 Docker/Podman/Buildah，无法在本地直接执行 `docker save`。

## 六、两种模式如何选择

| 场景 | 推荐模式 | 原因 |
|---|---|---|
| 偶尔问一个问题 | `scnet-aichat ask` | 任务隔离，回答后释放资源 |
| 连续对话、几十个问题 | 持久 `llama-server` | 模型只加载一次，避免重复等待 44–98 秒 |
| 多用户或网页服务 | 容器实例 + `llama-server` | 统一端口、鉴权、监控和生命周期 |
| 计算节点无外网 | Slurm 持久服务或 SCNet 镜像 | 推理不依赖运行时下载 |

## 七、测试

```bash
make test
SCNET_AICHAT_REMOTE_TESTS=1 ./tests/test.sh
```

测试覆盖 Bash/Python 语法、OpenAPI 签名和发现、凭据与路径脱敏、安装布局、
Bash 3.2 兼容性、14B/32B 资源映射、非法参数拒绝，以及可选的远端检查。

2026-09-28 已在昆山区域完成 OpenAPI 端到端 smoke：请求文件上传、14B Slurm
提交、状态轮询、模型推理、回答及性能日志下载均成功。

## 安全

- AK/SK 只进入 Keychain、Secret Service 或当前进程环境，不写普通配置文件。
- OpenAPI 区域 token 每次运行重新获取，不持久化。
- 个人 HOME 和模型绝对路径不会出现在 `--dry-run` 或历史列表中。
- `config`、`.env`、日志和结果目录默认不会被 Git 跟踪。
- worker 默认在作业结束时删除 prompt、system prompt 和运行路径输入文件；回答及
  Slurm 日志仍保留在远端请求目录，用户应按所在站点的数据保留策略清理。
- Slurm 持久服务只监听回环地址；容器服务强制要求 API key。
- 客户端会校验模型、资源数字、远端路径和作业号。
- `cancel` 只在用户显式执行时调用 `scancel`。
