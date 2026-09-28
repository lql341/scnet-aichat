# scnet-aichat

一个纯 Bash 的 SCNet/Slurm AI 问答面板。默认每个问题提交一个 Slurm 推理作业；
另外提供持久 `llama-server` 模式，用于连续问答。

项目不在登录节点运行模型，也不包含模型、SSH 私钥、访问令牌、作业日志或个人路径。

## 支持环境

- macOS 自带 Bash 3.2
- Ubuntu
- Debian
- 其他提供 Bash、OpenSSH、`awk`、`mktemp` 的 Unix-like 系统

远端目标环境是 Slurm + Hygon DCU/DTK + llama.cpp HIP，内置 14B 单卡和 32B 四卡资源模板。

## 一、安装和首次运行

新机器的完整交接说明见 [`docs/HANDOFF.md`](docs/HANDOFF.md)；架构说明见
[`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md)，容器 API 说明见
[`docs/CONTAINER_API.md`](docs/CONTAINER_API.md)。

### Agent 一句话安装

仓库是私有的，因此执行前需要本机已经配置 GitHub SSH key，或已经运行
`gh auth login`。Agent 可直接执行下面的一句话：

```bash
bash -lc 'set -eu; d="${SCNET_AICHAT_DIR:-$HOME/.local/src/scnet-aichat}"; if [ -d "$d/.git" ]; then git -C "$d" pull --ff-only; else mkdir -p "$(dirname "$d")"; git clone git@github.com:lql341/scnet-aichat.git "$d"; fi; "$d/install.sh" --check --remote-install'
```

该命令会安装本地客户端、初始化配置（只在配置不存在时创建）、上传远端 worker，
并运行本地和远端检查；不会下载模型、覆盖已有配置或删除远端数据。

如果使用 GitHub CLI：

```bash
bash -lc 'set -eu; d="${SCNET_AICHAT_DIR:-$HOME/.local/src/scnet-aichat}"; if [ -d "$d/.git" ]; then git -C "$d" pull --ff-only; else mkdir -p "$(dirname "$d")"; gh repo clone lql341/scnet-aichat "$d"; fi; "$d/install.sh" --check --remote-install'
```

### 1. 准备 SSH profile

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

### 2. 获取项目并创建配置

```bash
git clone git@github.com:lql341/scnet-aichat.git
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
cp -R worker server config.example ~/.local/share/scnet-aichat/
chmod 755 ~/.local/bin/scnet-aichat
```

然后把 `~/.local/bin` 加入 `PATH`，创建并编辑
`~/.config/scnet-aichat/config`，最后执行 `scnet-aichat install` 和
`scnet-aichat doctor`。

### 3. 安装远端 worker 并检查

```bash
./scnet-aichat install
./scnet-aichat doctor
```

`install` 只上传一个 Slurm worker 到远端 `~/.scnet-aichat/worker.slurm`；
不会上传 GGUF，也不会覆盖模型。

### 4. 打开面板

```bash
./scnet-aichat
```

直接输入问题即可提交作业。面板命令：

```text
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

如果未设置 `SCNET_REMOTE_HOME`，客户端会通过 SSH 自动读取远端 `$HOME`，再推导：

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
    --export=ALL,SCNET_SERVER_APP_DIR=$HOME/.scnet-aichat \
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
scp server/start-server.sh kseshell:~/dockerFileTemp/start-server.sh
scp Dockerfile kseshell:~/dockerFileTemp/Dockerfile
```

然后在 SCNet 容器服务中选择 Dockerfile 构建，并配置：

- 与 Hygon DCU/DTK 兼容的基础镜像；
- 启动命令 `/opt/scnet-aichat/start-server.sh`；
- 服务端口 `8080`；
- GGUF 通过持久存储挂载到 `/models`；
- `SCNET_MODEL_PATH` 指向挂载后的 GGUF；
- 需要鉴权时给 server 启动参数增加 `--api-key`。

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

测试覆盖 Bash 语法、Bash 3.2 兼容性、14B/32B 资源映射、非法参数拒绝，以及可选的
远端 worker、模型和分区检查。

## 安全

- 不要把 SSH 私钥、GitHub token 或集群凭据写入配置文件。
- `config`、`.env`、日志和结果目录默认不会被 Git 跟踪。
- 客户端会校验模型、资源数字、远端路径和作业号。
- `cancel` 只在用户显式执行时调用 `scancel`。
