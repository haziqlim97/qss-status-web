import os
import logging
from concurrent.futures import ThreadPoolExecutor

import paramiko
from dotenv import load_dotenv
from flask import Flask, jsonify, render_template
from flask_httpauth import HTTPBasicAuth
from werkzeug.security import check_password_hash, generate_password_hash

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
log = logging.getLogger("qss-status")

app = Flask(__name__)
auth = HTTPBasicAuth()

WEB_USERNAME = os.getenv("WEB_USERNAME", "qss")
WEB_PASSWORD_HASH = generate_password_hash(os.getenv("WEB_PASSWORD", "change-me"))


def load_devices():
    devices = {}
    for i in (str(n) for n in range(1, 11)):
        host = os.getenv(f"DEV{i}_HOST")
        if not host:
            continue
        devices[i] = {
            "id": i,
            "name": os.getenv(f"DEV{i}_NAME", f"Device {i}"),
            "host": host,
            "user": os.getenv(f"DEV{i}_USER"),
            "password": os.getenv(f"DEV{i}_PASSWORD"),
        }
    return devices


DEVICES = load_devices()


@auth.verify_password
def verify_password(username, password):
    if username == WEB_USERNAME and check_password_hash(WEB_PASSWORD_HASH, password):
        log.info("auth ok user=%s", username)
        return username
    log.warning("auth fail user=%s", username)
    return None


def check_lte(device):
    name, host = device["name"], device["host"]
    result = {
        "id": device["id"],
        "name": name,
        "host": host,
        "running": False,
        "processes": [],
        "error": None,
    }
    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    try:
        ssh.connect(
            host,
            username=device["user"],
            password=device["password"],
            timeout=10,
            banner_timeout=10,
            auth_timeout=10,
        )
        _, stdout, _ = ssh.exec_command(
            'ps aux | grep "lte" | grep -v grep', timeout=20
        )
        lines = [ln.rstrip() for ln in stdout.readlines() if ln.strip()]
        result["processes"] = lines
        result["running"] = bool(lines)
    except Exception as e:
        result["error"] = str(e)
        log.warning("check fail %s (%s): %s", name, host, e)
    finally:
        try:
            ssh.close()
        except Exception:
            pass
    return result


@app.route("/")
@auth.login_required
def index():
    return render_template("index.html", devices=list(DEVICES.values()))


@app.route("/api/check/<device_id>")
@auth.login_required
def api_check(device_id):
    device = DEVICES.get(device_id)
    if not device:
        return jsonify({"error": "unknown device"}), 404
    return jsonify(check_lte(device))


@app.route("/api/check-all")
@auth.login_required
def api_check_all():
    with ThreadPoolExecutor(max_workers=max(1, len(DEVICES))) as pool:
        results = list(pool.map(check_lte, DEVICES.values()))
    return jsonify(results)


if __name__ == "__main__":
    from waitress import serve

    host = os.getenv("BIND_HOST", "0.0.0.0")
    port = int(os.getenv("BIND_PORT", "5000"))
    log.info("serving on http://%s:%s", host, port)
    serve(app, host=host, port=port, threads=8)
