#!/usr/bin/env python3
"""
甲骨文云 ARM 实例配额监控 + 自动创建脚本
跑在 NAS (192.168.5.20) 上，检测到配额立即开实例
"""

import json
import hashlib
import base64
import datetime
import time
import requests
import os
import sys

# ========== 配置区域 ==========
# 优先从 APP_DATA_DIR/.env、/data/.env、~/oracle-arm/.env 读取，再回退到环境变量/默认值
CONFIG = {}


def env(name, default=""):
    return CONFIG.get(name, os.getenv(name, default))


def load_env_file():
    env_candidates = []
    app_data_dir = os.getenv("APP_DATA_DIR", "/data")
    if app_data_dir:
        env_candidates.append(os.path.join(app_data_dir, ".env"))
    env_candidates.append("/data/.env")
    env_candidates.append(os.path.expanduser("~/oracle-arm/.env"))

    data = {}
    env_path = next((p for p in env_candidates if p and os.path.exists(p)), None)
    if not env_path:
        return data
    with open(env_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            data[key.strip()] = value.strip()
    return data


def resolve_private_key_path(path: str) -> str:
    app_data_dir = os.getenv("APP_DATA_DIR", "/data")
    if path and os.path.exists(path):
        return path
    if path.startswith("/data/") and app_data_dir and app_data_dir != "/data":
        mapped = os.path.join(app_data_dir, path.removeprefix("/data/").lstrip("/"))
        if os.path.exists(mapped):
            return mapped
    return path


CONFIG = load_env_file()
TENANCY_OCID = env("TENANCY_OCID")
USER_OCID = env("USER_OCID")
FINGERPRINT = env("FINGERPRINT")
PRIVATE_KEY_PATH = resolve_private_key_path(env("PRIVATE_KEY_PATH", "/data/oci/oci_api_key.pem"))
REGION = env("REGION", "ap-seoul-1")
COMPARTMENT_OCID = env("COMPARTMENT_OCID")

# 实例配置
AVAILABILITY_DOMAIN = env("AVAILABILITY_DOMAIN")
# 每个 AD 内部有几个 Fault Domain，尝试时随机打乱顺序
# 不手动指定 fault_domain，让 Oracle 自动分配最优宿主机
FAULT_DOMAINS = [d.strip() for d in env("FAULT_DOMAINS", "").split(",") if d.strip()]


def get_availability_domains():
    return [item.strip() for item in AVAILABILITY_DOMAIN.split(",") if item.strip()]


def shuffled_ad_iterator():
    """每次迭代随机打乱 AD 顺序，避免总在同一宿主机上撞墙"""
    import random
    ads = get_availability_domains()
    while True:
        random.shuffle(ads)
        yield from ads

SHAPE = env("SHAPE", "VM.Standard.A1.Flex")
OCPUS = int(env("OCPUS", "1"))
MEMORY_IN_GBS = int(env("MEMORY_IN_GBS", "6"))
DISK_SIZE = int(env("DISK_SIZE", "50"))
SUBNET_OCID = env("SUBNET_OCID")
IMAGE_OCID = env("IMAGE_OCID")
SSH_PUBLIC_KEY = env("SSH_PUBLIC_KEY")

# 通知配置 (可选)
BARK_KEY = env("BARK_KEY")
TELEGRAM_BOT_TOKEN = env("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = env("TELEGRAM_CHAT_ID")

# 轮询间隔
CHECK_INTERVAL = int(env("CHECK_INTERVAL", "60"))

# 冲刺模式：容量满时临时切换到短间隔重试
burst_until = 0.0
burst_interval = 5  # 冲刺时每 5 秒试一次
burst_duration = 30  # 冲刺窗口持续 30 秒
# =============================


def validate_config():
    required = {
        "TENANCY_OCID": TENANCY_OCID,
        "USER_OCID": USER_OCID,
        "FINGERPRINT": FINGERPRINT,
        "COMPARTMENT_OCID": COMPARTMENT_OCID,
        "SUBNET_OCID": SUBNET_OCID,
        "IMAGE_OCID": IMAGE_OCID,
        "SSH_PUBLIC_KEY": SSH_PUBLIC_KEY,
        "AVAILABILITY_DOMAIN": AVAILABILITY_DOMAIN,
    }
    missing = [k for k, v in required.items() if not v]
    if missing:
        print(f"[{now()}] 缺少配置: {', '.join(missing)}")
        print(f"[{now()}] 请编辑 ~/oracle-arm/.env")
        return False
    if not os.path.exists(PRIVATE_KEY_PATH):
        print(f"[{now()}] 私钥不存在: {PRIVATE_KEY_PATH}")
        return False
    return True


def load_private_key():
    with open(PRIVATE_KEY_PATH, 'r') as f:
        return f.read()


def sign_request_correct(method, uri, body=""):
    """OCI 标准签名 (使用 RSA-SHA256)"""
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import padding

    date_header = datetime.datetime.now(datetime.UTC).strftime('%a, %d %b %Y %H:%M:%S GMT')
    body_bytes = body.encode("utf-8")
    body_sha256_b64 = base64.b64encode(hashlib.sha256(body_bytes).digest()).decode()

    signing_lines = [
        f"(request-target): {method.lower()} {uri}",
        f"host: iaas.{REGION}.oraclecloud.com",
        f"date: {date_header}",
    ]
    header_names = ["(request-target)", "host", "date"]

    if method.upper() in {"POST", "PUT", "PATCH"}:
        signing_lines.extend([
            f"x-content-sha256: {body_sha256_b64}",
            "content-type: application/json",
            f"content-length: {len(body_bytes)}",
        ])
        header_names.extend(["x-content-sha256", "content-type", "content-length"])

    signing_string = "\n".join(signing_lines)

    with open(PRIVATE_KEY_PATH, 'rb') as f:
        private_key = serialization.load_pem_private_key(f.read(), password=None)

    signature = base64.b64encode(
        private_key.sign(signing_string.encode(), padding.PKCS1v15(), hashes.SHA256())
    ).decode()

    headers = {
        "host": f"iaas.{REGION}.oraclecloud.com",
        "date": date_header,
        "Authorization": (
            f'Signature version="1",'
            f'keyId="{TENANCY_OCID}/{USER_OCID}/{FINGERPRINT}",'
            f'algorithm="rsa-sha256",'
            f'headers="{" ".join(header_names)}",'
            f'signature="{signature}"'
        )
    }

    if method.upper() in {"POST", "PUT", "PATCH"}:
        headers.update({
            "x-content-sha256": body_sha256_b64,
            "content-type": "application/json",
            "content-length": str(len(body_bytes)),
        })

    return headers


def get_compute_client():
    """使用 oci sdk (推荐)"""
    try:
        import oci
        config = {
            "user": USER_OCID,
            "fingerprint": FINGERPRINT,
            "key_file": PRIVATE_KEY_PATH,
            "tenancy": TENANCY_OCID,
            "region": REGION,
        }
        return oci.core.ComputeClient(config), oci.core.VirtualNetworkClient(config)
    except Exception:
        return None, None


def check_arm_quota_sdk(compute_client):
    """SDK 方式检查 A1 配额"""
    try:
        shapes = compute_client.list_shapes(
            compartment_id=COMPARTMENT_OCID
        )
        for shape in shapes.data:
            if shape.shape == SHAPE:
                print(f"[{now()}] 发现 {SHAPE} 可用! 尝试创建实例...")
                return True
        return False
    except Exception as e:
        print(f"[{now()}] 检查配额失败: {e}")
        return False


def try_create_instance_sdk(compute_client, network_client):
    """SDK 方式创建实例，不指定 fault_domain（让 Oracle 自动分配），AD 随机轮询"""
    import oci

    ad_gen = shuffled_ad_iterator()
    for availability_domain in ad_gen:
        # 不传 fault_domain，由 Oracle 选择最优宿主机
        launch_details = oci.core.models.LaunchInstanceDetails(
            compartment_id=COMPARTMENT_OCID,
            display_name="free-arm-a1",
            availability_domain=availability_domain,
            shape=SHAPE,
            shape_config=oci.core.models.LaunchInstanceShapeConfigDetails(
                ocpus=OCPUS,
                memory_in_gbs=MEMORY_IN_GBS
            ),
            source_details=oci.core.models.InstanceSourceViaImageDetails(
                image_id=IMAGE_OCID,
                boot_volume_size_in_gbs=DISK_SIZE
            ),
            create_vnic_details=oci.core.models.CreateVnicDetails(
                subnet_id=SUBNET_OCID,
                assign_public_ip=True
            ),
            metadata={
                "ssh_authorized_keys": SSH_PUBLIC_KEY
            }
        )

        try:
            print(f"[{now()}] 尝试 AD: {availability_domain}（fault_domain=自动）")
            response = compute_client.launch_instance(launch_details)
            instance = response.data
            print(f"[{now()}] 实例创建成功! OCID: {instance.id}")
            send_notification(f"甲骨文 ARM 实例创建成功!\nID: {instance.id}\n区域: {REGION}\nAD: {availability_domain}")
            return True
        except oci.exceptions.ServiceError as e:
            if e.status == 500 or "Out of host capacity" in str(e.message):
                print(f"[{now()}] {availability_domain} 配额已满: {e.message}")
                trigger_burst()
                continue
            print(f"[{now()}] {availability_domain} 创建失败: {e.message}")
        except Exception as e:
            print(f"[{now()}] {availability_domain} 异常: {e}")
    return False


def check_and_create_api():
    """纯 API 方式 (无 oci sdk)"""
    base_url = f"https://iaas.{REGION}.oraclecloud.com"
    
    # 1. 检查 shape 可用性 (list shapes)
    uri = f"/20160918/shapes?compartmentId={COMPARTMENT_OCID}"
    headers = sign_request_correct("GET", uri)
    
    try:
        resp = requests.get(base_url + uri, headers=headers, timeout=10)
        if resp.status_code == 200:
            shapes = resp.json()
            arm_available = any(s.get("shape") == SHAPE for s in shapes)
            if arm_available:
                print(f"[{now()}] {SHAPE} 出现在 shape 列表中，尝试创建...")
                return try_create_instance_api(base_url)
            else:
                print(f"[{now()}] {SHAPE} 不在可用列表中")
        else:
            print(f"[{now()}] API 错误: {resp.status_code} {resp.text[:200]}")
    except Exception as e:
        print(f"[{now()}] 请求异常: {e}")
    return False


def try_create_instance_api(base_url):
    """API 方式创建实例，不指定 fault_domain（让 Oracle 自动分配），AD 随机轮询"""
    uri = "/20160918/instances"

    ad_gen = shuffled_ad_iterator()
    for availability_domain in ad_gen:
        # 不传 fault_domain 字段，由 Oracle 自动分配最优宿主机
        payload = json.dumps({
            "compartmentId": COMPARTMENT_OCID,
            "displayName": "free-arm-a1",
            "availabilityDomain": availability_domain,
            "shape": SHAPE,
            "shapeConfig": {
                "ocpus": OCPUS,
                "memoryInGBs": MEMORY_IN_GBS
            },
            "sourceDetails": {
                "sourceType": "image",
                "imageId": IMAGE_OCID,
                "bootVolumeSizeInGBs": DISK_SIZE
            },
            "createVnicDetails": {
                "subnetId": SUBNET_OCID,
                "assignPublicIp": True
            },
            "metadata": {
                "ssh_authorized_keys": SSH_PUBLIC_KEY
            }
        })

        headers = sign_request_correct("POST", uri, payload)

        try:
            print(f"[{now()}] 尝试 AD: {availability_domain}（fault_domain=自动）")
            resp = requests.post(base_url + uri, headers=headers, data=payload, timeout=15)
            if resp.status_code == 200:
                data = resp.json()
                print(f"[{now()}] 实例创建成功! ID: {data.get('id')}")
                send_notification(f"甲骨文 ARM 抢到了！\nID: {data.get('id')}\n区域: {REGION}\nAD: {availability_domain}")
                return True
            if resp.status_code == 500 or "OutOfHostCapacity" in resp.text or "Out of host capacity" in resp.text:
                print(f"[{now()}] {availability_domain} 主机容量不足，继续监控...")
                trigger_burst()
                continue
            print(f"[{now()}] {availability_domain} 创建失败: {resp.status_code} {resp.text[:300]}")
        except Exception as e:
            print(f"[{now()}] {availability_domain} 创建异常: {e}")
    return False


def trigger_burst():
    """命中容量满时触发冲刺模式：30秒内每5秒快速重试"""
    global burst_until
    import time
    burst_until = time.time() + burst_duration
    print(f"[{now()}] 触发冲刺模式（{burst_duration}秒窗口）")


def send_notification(msg):
    """发送通知"""
    if BARK_KEY:
        try:
            requests.get(f"https://api.day.app/{BARK_KEY}/甲骨文ARM/{msg}", timeout=5)
        except:
            pass
    if TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID:
        try:
            requests.post(
                f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage",
                json={"chat_id": TELEGRAM_CHAT_ID, "text": msg},
                timeout=5
            )
        except:
            pass


def now():
    return datetime.datetime.now().strftime("%m-%d %H:%M:%S")


def main():
    if "--check" in sys.argv:
        ok = validate_config()
        print("CONFIG_OK" if ok else "CONFIG_MISSING")
        sys.exit(0 if ok else 1)

    print(f"甲骨文 ARM 监控启动 | 区域: {REGION} | 间隔: {CHECK_INTERVAL}s")
    print(f"目标: {SHAPE} ({OCPUS}C/{MEMORY_IN_GBS}G)")
    print(f"AD 列表: {', '.join(get_availability_domains())}")
    print("=" * 50)

    if not validate_config():
        sys.exit(1)
    compute_client, network_client = get_compute_client()
    use_sdk = compute_client is not None
    
    if use_sdk:
        print("使用 OCI SDK 模式")
    else:
        print("OCI SDK 未安装，使用 REST API 模式")
        print("安装 SDK: pip3 install oci")
    
    attempt = 0
    print(f"故障域: 自动分配（让 Oracle 选最优宿主机）")
    print("=" * 50)
    while True:
        attempt += 1
        try:
            # 冲刺模式窗口内用短间隔
            now_ts = time.time()
            if now_ts < burst_until:
                sleep_time = burst_interval
            else:
                sleep_time = CHECK_INTERVAL
                burst_until = 0.0

            if use_sdk:
                if check_arm_quota_sdk(compute_client):
                    if try_create_instance_sdk(compute_client, network_client):
                        print("抢到了！脚本退出。")
                        break
            else:
                if check_and_create_api():
                    print("抢到了！脚本退出。")
                    break

            if attempt % 10 == 0:
                print(f"[{now()}] 已尝试 {attempt} 次，继续监控...")

        except KeyboardInterrupt:
            print("\n手动退出")
            break
        except Exception as e:
            print(f"[{now()}] 循环异常: {e}")

        time.sleep(sleep_time)


if __name__ == "__main__":
    main()
