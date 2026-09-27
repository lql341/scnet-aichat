# scnet-aichat

一个纯 Bash 的 SCNet/Slurm AI 问答面板。每次提问都会：

1. 通过 SSH 上传提示词；
2. 向指定 Slurm 分区提交推理作业；
3. 轮询作业状态；
4. 返回模型回答和 llama.cpp 性能数据。

项目不在登录节点运行模型，也不包含模型、SSH 密钥、访问令牌、作业日志或个人路径。

## 支持环境

- macOS 自带 Bash 3.2
- Ubuntu
- Debian
- 其他提供 Bash、OpenSSH、awk、mktemp 的 Unix-like 系统

远端目前面向 Slurm + Hygon DCU/DTK + llama.cpp HIP 环境，内置 14B 单卡与
32B 四卡资源模板。

## 快速开始

```bash
git clone git@github.com:lql341/scnet-aichat.git
cd scnet-aichat

mkdir -p ~/.config/scnet-aichat
cp config.example ~/.config/scnet-aichat/config

./scnet-aichat install
./scnet-aichat doctor
./scnet-aichat
```

面板命令：

```text
/model 14b
/model 32b
/tokens 1024
/system You are a concise assistant.
/file prompt.txt
/status JOB_ID
/result JOB_ID
/cancel JOB_ID
/history
/quit
```

非交互调用：

```bash
./scnet-aichat ask "请解释张量并行。"
./scnet-aichat --model 32b --max-tokens 256 ask "写一个简短示例。"
./scnet-aichat --no-wait ask "生成报告。"
./scnet-aichat result JOB_ID
```

## 配置

默认读取：

```text
~/.config/scnet-aichat/config
```

也可以通过 `SCNET_AICHAT_CONFIG` 指定其他文件。完整选项见
[`config.example`](config.example)。

如果未设置 `SCNET_REMOTE_HOME`，客户端会通过 SSH 自动读取远端 `$HOME`，再据此推导：

- 远端应用目录：`$HOME/.scnet-aichat`
- llama.cpp：`$HOME/eva-k100/llama.cpp-b5046/build-gfx906/bin/llama-cli`
- 模型目录：`$HOME/models/...`

路径均可在配置文件中覆盖。

默认资源：

| 模型 | DCU | CPU | 内存 | 默认格式 |
|---|---:|---:|---:|---|
| 14B | 1 | 8 | 27GB | Q4_0 |
| 32B | 4 | 32 | 110GB | Q4_K_M |

默认分区为 `kshdnormal`。项目不会自动切换分区。

## 测试

```bash
make test
```

加入真实远端 `doctor`：

```bash
SCNET_AICHAT_REMOTE_TESTS=1 ./tests/test.sh
```

测试覆盖：

- Bash 语法；
- Bash 3.2 兼容性扫描；
- 14B/32B 资源映射；
- 非法模型和 token 参数拒绝；
- 可选远端运行时、模型和分区检查。

## 延迟说明

这是“一问一作业”模式，端到端时间包含 Slurm 排队和模型加载。已验证环境中的典型值：

- 14B Q4_0：生成约 27–28 tok/s，加载约 44–47 秒；
- 32B Q4_K_M：生成约 13.7–13.8 tok/s，加载约 98 秒。

## 安全

- 不要把 SSH 私钥、GitHub token 或集群凭据写入配置文件。
- `config`、`.env`、日志和结果目录默认不会被 Git 跟踪。
- 客户端会校验模型、资源数字、远端路径和作业号。
- `cancel` 只在用户显式执行时调用 `scancel`。
