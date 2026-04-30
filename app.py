from __future__ import annotations

import os
import signal
import subprocess
from pathlib import Path
from typing import Dict

from flask import Flask, jsonify, render_template, request

DEFAULTS: Dict[str, str] = {
    'TENANCY_OCID': '',
    'USER_OCID': '',
    'FINGERPRINT': '',
    'PRIVATE_KEY_PATH': '/data/oci/oci_api_key.pem',
    'REGION': 'ap-seoul-1',
    'COMPARTMENT_OCID': '',
    'AVAILABILITY_DOMAIN': '',
    'SHAPE': 'VM.Standard.A1.Flex',
    'OCPUS': '1',
    'MEMORY_IN_GBS': '6',
    'DISK_SIZE': '50',
    'SUBNET_OCID': '',
    'IMAGE_OCID': '',
    'SSH_PUBLIC_KEY': '',
    'CHECK_INTERVAL': '60',
    'BARK_KEY': '',
    'TELEGRAM_BOT_TOKEN': '',
    'TELEGRAM_CHAT_ID': '',
}

FIELD_META: Dict[str, Dict[str, str]] = {
    'TENANCY_OCID': {
        'label': '租户 OCID',
        'help': '甲骨文账号的 Tenancy 标识，控制台个人资料里可找到。',
        'placeholder': 'ocid1.tenancy.oc1..xxxx'
    },
    'USER_OCID': {
        'label': '用户 OCID',
        'help': '当前 API 用户的 OCID，用来签名请求。',
        'placeholder': 'ocid1.user.oc1..xxxx'
    },
    'FINGERPRINT': {
        'label': 'API 密钥指纹',
        'help': '上传 API Key 后显示的 fingerprint。',
        'placeholder': '12:34:56:78:90:ab:cd:ef'
    },
    'PRIVATE_KEY_PATH': {
        'label': '私钥文件路径',
        'help': 'OCI API 私钥在容器里的路径，默认不用改。',
        'placeholder': '/data/oci/oci_api_key.pem'
    },
    'REGION': {
        'label': '区域 Region',
        'help': '抢实例的区域代码，常见如 ap-seoul-1、us-ashburn-1。',
        'placeholder': 'ap-seoul-1'
    },
    'COMPARTMENT_OCID': {
        'label': 'Compartment OCID',
        'help': '要创建实例的 compartment。根租户也可以。',
        'placeholder': 'ocid1.compartment.oc1..xxxx'
    },
    'AVAILABILITY_DOMAIN': {
        'label': '可用域 AD',
        'help': '支持填多个完整 AD，逗号分隔，比如 VyDi:PHX-AD-1,VyDi:PHX-AD-2。',
        'placeholder': 'VyDi:PHX-AD-1,VyDi:PHX-AD-2'
    },
    'SHAPE': {
        'label': '实例规格 Shape',
        'help': 'Always Free ARM 一般填 VM.Standard.A1.Flex。',
        'placeholder': 'VM.Standard.A1.Flex'
    },
    'OCPUS': {
        'label': 'CPU 核数',
        'help': '建议先填 1，更容易抢到。',
        'placeholder': '1'
    },
    'MEMORY_IN_GBS': {
        'label': '内存 GB',
        'help': '建议先填 6，对应 1C/6G。',
        'placeholder': '6'
    },
    'DISK_SIZE': {
        'label': '启动盘大小 GB',
        'help': '系统盘大小，常用 50。',
        'placeholder': '50'
    },
    'SUBNET_OCID': {
        'label': '子网 Subnet OCID',
        'help': '实例网卡要挂到的子网。',
        'placeholder': 'ocid1.subnet.oc1..xxxx'
    },
    'IMAGE_OCID': {
        'label': '镜像 Image OCID',
        'help': '要安装的系统镜像 ID，比如 Ubuntu/Oracle Linux。',
        'placeholder': 'ocid1.image.oc1..xxxx'
    },
    'SSH_PUBLIC_KEY': {
        'label': 'SSH 公钥',
        'help': '填整行公钥，实例创建后用于 SSH 登录。',
        'placeholder': 'ssh-rsa AAAAB3NzaC1...'
    },
    'CHECK_INTERVAL': {
        'label': '检查间隔 秒',
        'help': '轮询频率，默认 60 秒。',
        'placeholder': '60'
    },
    'BARK_KEY': {
        'label': 'Bark 推送 Key',
        'help': '可选，抢到后推送到 iPhone Bark。不会用就留空。',
        'placeholder': ''
    },
    'TELEGRAM_BOT_TOKEN': {
        'label': 'Telegram Bot Token',
        'help': '可选，抢到后让机器人发消息。',
        'placeholder': '123456:ABCDEF'
    },
    'TELEGRAM_CHAT_ID': {
        'label': 'Telegram Chat ID',
        'help': '可选，机器人要发到哪个聊天。',
        'placeholder': '123456789'
    },
}


def read_env(env_path: Path) -> Dict[str, str]:
    data = DEFAULTS.copy()
    if not env_path.exists():
        return data
    for raw in env_path.read_text(encoding='utf-8').splitlines():
        line = raw.strip()
        if not line or line.startswith('#') or '=' not in line:
            continue
        key, value = line.split('=', 1)
        data[key.strip()] = value.strip()
    return data


def write_env(env_path: Path, data: Dict[str, str]) -> None:
    lines = [f'{key}={data.get(key, "")}' for key in DEFAULTS]
    env_path.write_text('\n'.join(lines) + '\n', encoding='utf-8')


class MonitorManager:
    def __init__(self, workdir: Path):
        self.workdir = workdir
        self.pid_path = workdir / 'monitor.pid'
        self.log_path = workdir / 'monitor.log'
        self.env_path = workdir / '.env'
        self.script_path = workdir / 'monitor.py'
        self.source_script_path = Path(__file__).resolve().parent / 'oracle-arm-monitor.py'

    def ensure_monitor_script(self) -> None:
        if self.source_script_path.exists():
            self.script_path.write_text(self.source_script_path.read_text(encoding='utf-8'), encoding='utf-8')

    def status(self) -> dict:
        pid = None
        running = False
        if self.pid_path.exists():
            try:
                pid = int(self.pid_path.read_text(encoding='utf-8').strip())
                os.kill(pid, 0)
                running = True
            except Exception:
                self.pid_path.unlink(missing_ok=True)
                pid = None
                running = False
        return {'running': running, 'pid': pid, 'log_path': str(self.log_path)}

    def start(self) -> dict:
        status = self.status()
        if status['running']:
            return status
        self.ensure_monitor_script()
        self.log_path.touch(exist_ok=True)
        logf = self.log_path.open('ab')
        child_env = os.environ.copy()
        child_env['APP_DATA_DIR'] = str(self.workdir)
        proc = subprocess.Popen(
            ['/usr/local/bin/python', str(self.script_path)],
            cwd=self.workdir,
            stdout=logf,
            stderr=subprocess.STDOUT,
            start_new_session=True,
            env=child_env,
        )
        logf.close()
        self.pid_path.write_text(str(proc.pid), encoding='utf-8')
        return self.status()

    def stop(self) -> dict:
        status = self.status()
        if not status['running']:
            self.pid_path.unlink(missing_ok=True)
            return self.status()
        os.kill(status['pid'], signal.SIGTERM)
        self.pid_path.unlink(missing_ok=True)
        return self.status()

    def logs(self, limit: int = 200) -> str:
        if not self.log_path.exists():
            return ''
        lines = self.log_path.read_text(encoding='utf-8', errors='ignore').splitlines()
        return '\n'.join(lines[-limit:])


def create_app(workdir: Path | None = None) -> Flask:
    base = Path(workdir or os.getenv('APP_DATA_DIR', '/data')).resolve()
    base.mkdir(parents=True, exist_ok=True)
    app = Flask(__name__, template_folder='templates', static_folder='static')
    manager = MonitorManager(base)

    @app.get('/')
    def index():
        fields = [
            {
                'key': key,
                'value': read_env(manager.env_path).get(key, ''),
                'label': FIELD_META[key]['label'],
                'help': FIELD_META[key]['help'],
                'placeholder': FIELD_META[key]['placeholder'],
            }
            for key in DEFAULTS
        ]
        return render_template('index.html', fields=fields)

    @app.get('/api/config')
    def get_config():
        return jsonify(read_env(manager.env_path))

    @app.post('/api/config')
    def save_config():
        payload = request.get_json(force=True) or {}
        data = read_env(manager.env_path)
        for key in DEFAULTS:
            if key in payload:
                data[key] = str(payload[key])
        write_env(manager.env_path, data)
        return jsonify({'ok': True})

    @app.get('/api/status')
    def status():
        return jsonify(manager.status())

    @app.post('/api/start')
    def start():
        return jsonify(manager.start())

    @app.post('/api/stop')
    def stop():
        return jsonify(manager.stop())

    @app.get('/api/logs')
    def logs():
        return jsonify({'text': manager.logs()})

    return app


app = create_app()


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8080)
