# Oracle ARM Monitor

甲骨文云 ARM 实例自动抢建工具，支持 Web 面板配置。

## 功能特性

- 多 AD 轮询（AD-1/2/3 随机打乱）
- 自动分配 Fault Domain（让 Oracle 选择最优宿主机）
- 冲刺模式：命中容量满后 30 秒内 5 秒速抢
- Web 控制面板 + Telegram 通知
- 支持 OCI SDK / REST API 两种模式

## 快速开始

### 方式一：Docker 部署（推荐）

```bash
git clone https://github.com/dute8505/oracle-arm-monitor.git
cd oracle-arm-monitor

# 复制配置模板
cp .env.example data/.env

# 编辑配置
vim data/.env

# 启动
docker-compose up -d
```

访问 `http://localhost:8088`

### 方式二：直接运行

```bash
pip install -r requirements.txt
cp .env.example .env
# 编辑 .env 填入 Oracle Cloud 凭证
python oracle-arm-monitor.py
```

## 配置说明

| 字段 | 说明 |
|------|------|
| TENANCY_OCID | 租户 OCID |
| USER_OCID | 用户 OCID |
| FINGERPRINT | API 密钥指纹 |
| REGION | 区域，如 `us-phoenix-1` |
| AVAILABILITY_DOMAIN | 可用域，支持多 AD 逗号分隔 |
| OCPUS / MEMORY_IN_GBS | 实例规格（免费额度 4C/24G） |
| SUBNET_OCID | 子网 OCID |
| IMAGE_OCID | 镜像 OCID |
| SSH_PUBLIC_KEY | SSH 公钥 |
| TELEGRAM_BOT_TOKEN | Telegram 机器人 Token |
| TELEGRAM_CHAT_ID | Telegram 通知目标 ID |
| CHECK_INTERVAL | 轮询间隔（秒） |

## 获取 Oracle Cloud API 凭证

1. 登录 Oracle Cloud Console
2. 个人头像 → My Profile → API Keys
3. 添加 API Key，下载私钥
4. 复制 OCID 等信息填入配置

## License

MIT
