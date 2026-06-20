# Oracle ARM Monitor

（基于[dute8505/oracle-arm-monitor](https://github.com/dute8505/oracle-arm-monitor)的修改版本）

甲骨文云 ARM 实例自动抢建工具，支持 Web 面板配置。

## 功能特性

- 多 AD 轮询（AD-1/2/3 随机打乱）
- 自动分配 Fault Domain（让 Oracle 选择最优宿主机）
- Web 控制面板 + Telegram 通知
- 支持 OCI SDK / REST API 两种模式（推荐OCI SDK模式）
- (new)脚本支持通过命令行参数指定配置文件，实现在同一机器上多甲骨文帐号同时申请arm。

## 快速开始

### 方式一：直接运行（推荐）

1. `pip install -r requirements.txt`
2. `cp .env.example .env`
3. 编辑 .env 填入 Oracle Cloud 凭证
4. `python oracle-arm-monitor.py`

### 方式二：Docker 部署

```bash
git clone https://github.com/wkingnet/oracle-arm-monitor.git
cd oracle-arm-monitor

# 复制配置模板
cp .env.example data/.env

# 编辑配置
nano data/.env

# 启动
docker-compose up -d
```

访问`http://localhost:8088`开启监控，并可查看日志和修改配置。



## 配置说明

| 字段                    | 说明                 | 获取位置                                                                          |
|-----------------------|--------------------|-------------------------------------------------------------------------------|
| USER_OCID             | 用户 OCID            | https://cloud.oracle.com/identity/domains/my-profile 用户信息内的OCID               |
| TENANCY_OCID          | 租户 OCID            | https://cloud.oracle.com/tenancy 一般信息内的OCID                                   |
| COMPARTMENT_OCID      | 包房 OCID            | 值同租户 OCID                                                                     |
| FINGERPRINT           | API 密钥指纹           | https://cloud.oracle.com/identity/domains/my-profile/auth-tokens 添加或使用现有API密钥 |
| REGION                | 区域                 | 找到子网OCID后，子网OCID的值中的ocid1.subnet.oc1.**us-sanjose-1**就是区域                     |
| AVAILABILITY_DOMAIN   | 可用域，支持多 AD 逗号分隔    | 读取main.tf文件availability_domain字段的值                                            |
| OCPUS / MEMORY_IN_GBS | 实例规格               | 自定义，arm最大免费额度4C/24G内存，且所有免费实例共享200G硬盘额度                                       |
| SUBNET_OCID           | 子网 OCID            | 读取main.tf文件subnet_id字段的值                                                      |
| IMAGE_OCID            | 镜像 OCID            | 读取main.tf文件source_id字段的值                                                      |
| SSH_PUBLIC_KEY        | 登录arm实例所需的SSH 公钥   | 自定义                                                                           |
| TELEGRAM_BOT_TOKEN    | Telegram 机器人 Token | 自定义                                                                           |
| TELEGRAM_CHAT_ID      | Telegram 通知目标 ID   | 自定义                                                                           |
| CHECK_INTERVAL        | 轮询间隔（秒）            | 自定义，请求过于频繁会被警告/封号                                                             |

### 如何获取main.tf文件
1. 手动进行创建arm实例步骤，配置完arm规格后，到最后一步，不要点击“创建”按钮，点击旁边的“另存为堆栈”按钮。
2. 进入到创建堆栈过程，无需更改配置，一路“下一步”，最后点“创建”按钮。
3. 创建完成后来到堆栈详情界面，在“Terraform 配置”所在行后面，有一个“下载”按钮，点击并保存文件。
4. 解压缩文件，就得到了所需的main.tf。此文件中包含了创建arm实例所需的一些

## License

MIT
