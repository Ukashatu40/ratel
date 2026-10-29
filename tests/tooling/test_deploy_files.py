"""deploy/core-cp/ stays in step with the code and stays free of secrets and addresses."""

from __future__ import annotations

import json
import os
import re
import stat
from pathlib import Path

from ratel_link.config import Settings

ROOT = Path(__file__).resolve().parents[2]
DEPLOY = ROOT / "deploy/core-cp"
ENV_EXAMPLE = DEPLOY / "ratel-link.env.example"
UNIT = DEPLOY / "ratel-link.service"


def _files() -> list[Path]:
    return [p for p in DEPLOY.rglob("*") if p.is_file()]


def test_every_setting_is_in_the_deployment_env_template() -> None:
    text = ENV_EXAMPLE.read_text()
    missing = [
        name.upper()
        for name in Settings.model_fields
        if not re.search(rf"^#?\s*{name.upper()}=", text, re.MULTILINE)
    ]
    assert missing == [], f"add these to {ENV_EXAMPLE.name}: {missing}"


def test_the_env_template_has_no_real_password() -> None:
    uri = re.search(r"^MONGO_URI=(.*)$", ENV_EXAMPLE.read_text(), re.MULTILINE)
    assert uri is not None and "<password>" in uri.group(1)


def test_the_unit_runs_the_service_the_way_the_docs_say() -> None:
    unit = UNIT.read_text()
    exec_start = next(line for line in unit.splitlines() if line.startswith("ExecStart="))
    assert "--factory ratel_link.main:create_app" in exec_start
    assert "--host 127.0.0.1" in exec_start  # other hosts go through the proxy
    assert "--no-access-log" in exec_start  # the access log would print IMSIs
    assert "User=ratellink" in unit and "EnvironmentFile=/etc/ratel-link/ratel-link.env" in unit


def test_the_unit_keeps_its_hardening() -> None:
    unit = UNIT.read_text()
    for setting in (
        "NoNewPrivileges=yes",
        "ProtectSystem=strict",
        "ProtectHome=yes",
        "PrivateTmp=yes",
        "CapabilityBoundingSet=",
        "RestrictAddressFamilies=AF_INET AF_INET6 AF_UNIX",
        "ReadOnlyPaths=/opt/ratel-link /etc/ratel-link",
    ):
        assert setting in unit, setting


def test_restart_limits_are_in_the_unit_section() -> None:
    # systemd silently ignores them anywhere else (found by systemd-analyze verify).
    unit = UNIT.read_text()
    unit_section = unit.split("[Service]")[0]
    assert "StartLimitIntervalSec=" in unit_section and "StartLimitBurst=" in unit_section


EXPIRY_UNIT = DEPLOY / "ratel-link-check-expiry.service"
EXPIRY_TIMER = DEPLOY / "ratel-link-check-expiry.timer"
# The unit settings that confine a process. The expiry job must have every one the service has.
CONFINEMENT_PREFIXES = (
    "NoNewPrivileges=",
    "Private",
    "Protect",
    "Restrict",
    "LockPersonality=",
    "CapabilityBoundingSet=",
    "AmbientCapabilities=",
    "SystemCall",
    "ReadOnlyPaths=",
)


def _settings(unit: str, prefixes: tuple[str, ...]) -> set[str]:
    return {ln for ln in unit.splitlines() if ln.startswith(prefixes)}


def test_the_expiry_job_runs_the_admin_command_as_the_service_user() -> None:
    unit = EXPIRY_UNIT.read_text()
    exec_start = next(ln for ln in unit.splitlines() if ln.startswith("ExecStart="))
    assert exec_start.endswith("-m ratel_link.admin_cli api-key check-expiry")
    assert "/opt/ratel-link/current/venv/bin/python" in exec_start
    assert "User=ratellink" in unit and "EnvironmentFile=/etc/ratel-link/ratel-link.env" in unit
    assert "Environment=PYTHONPATH=/opt/ratel-link/current/services" in unit
    assert "Type=oneshot" in unit
    assert "Restart=" not in unit  # a failed run is seen in the journal, not retried in a loop


def test_the_expiry_job_is_confined_at_least_as_tightly_as_the_service() -> None:
    service, job = UNIT.read_text(), EXPIRY_UNIT.read_text()
    missing = _settings(service, CONFINEMENT_PREFIXES) - _settings(job, CONFINEMENT_PREFIXES)
    assert missing == set(), f"add to {EXPIRY_UNIT.name}: {sorted(missing)}"


def test_the_timer_runs_the_expiry_job_daily_and_catches_up_after_downtime() -> None:
    timer = EXPIRY_TIMER.read_text()
    assert "OnCalendar=daily" in timer
    assert "Persistent=true" in timer
    assert "Unit=ratel-link-check-expiry.service" in timer
    assert "WantedBy=timers.target" in timer
    assert EXPIRY_UNIT.exists()


def test_the_scripts_are_executable_where_they_are_run_directly() -> None:
    mode = os.stat(DEPLOY / "install-release.sh").st_mode
    assert mode & stat.S_IXUSR


def test_the_roles_file_is_valid_json_with_the_placeholders_the_script_fills() -> None:
    text = (DEPLOY / "mongo/ratel-link-roles.json").read_text()
    assert {"RATEL_DB", "CORE_DB", "SUFFIX"} <= set(re.findall(r"\{\{(\w+)\}\}", text))
    filled = text.replace("{{RATEL_DB}}", "a").replace("{{CORE_DB}}", "b").replace("{{SUFFIX}}", "")
    assert json.loads(filled)["roles"]


def test_the_user_script_reads_the_password_from_the_environment_only() -> None:
    script = (DEPLOY / "mongo/create-ratel-link-user.js").read_text()
    assert "process.env.RATEL_LINK_DB_PASSWORD" in script
    assert not re.search(r"pwd:\s*['\"]", script)  # no literal password


def test_no_file_holds_a_secret_or_a_real_address() -> None:
    forbidden = [
        r"102\.214\.",  # the lab's public range (kept out of this public repository)
        r"BEGIN [A-Z ]*PRIVATE KEY",
        r"rlk_[a-z0-9-]+\.[A-Za-z0-9_-]{20,}",  # an API key
        r"mongodb://[^<\s]+:[^<\s@]{6,}@",  # a connection string with a real-looking password
    ]
    for path in _files():
        text = path.read_text()
        for pattern in forbidden:
            assert not re.search(pattern, text), f"{path.relative_to(ROOT)} matches {pattern}"


def test_the_proxy_template_never_logs_the_request_path() -> None:
    conf = (DEPLOY / "nginx/ratel-link.conf.example").read_text()
    log_format = next(line for line in conf.splitlines() if line.startswith("log_format"))
    for variable in ("$request ", "$request_uri", "$uri", "$http_authorization"):
        assert variable not in log_format + " ", variable
    assert "deny  all;" in conf and "client_max_body_size" in conf and "limit_req " in conf


def test_the_core_cp_readme_runs_the_admin_cli_through_a_function_not_a_variable() -> None:
    # `RUN="... bash -c '...' _"` then `$RUN cmd` is split into words and fails in bash.
    text = (ROOT / "deploy/core-cp/README.md").read_text()
    assert "$RUN" not in text and "RUN=" not in text
    assert "admin_cli() {" in text and "admin_cli key generate" in text


CERT_SCRIPT = ROOT / "deploy/core-cp/nginx/make-self-signed-cert.sh"


def test_the_certificate_script_refuses_what_is_not_an_address_and_never_overwrites(
    tmp_path: Path,
) -> None:
    import os
    import shutil
    import subprocess

    bash = shutil.which("bash")
    assert bash is not None
    assert os.access(CERT_SCRIPT, os.X_OK)
    for bad in ("", "999.1.1.1", "1.2.3", "localhost", "a;b.c", "-x.com", "a b.c"):
        out = tmp_path / "out"
        args = [bash, str(CERT_SCRIPT), *([bad] if bad else []), str(out)]
        done = subprocess.run(args, capture_output=True, text=True, check=False)  # noqa: S603
        assert done.returncode == 2, (bad, done.stderr)
        assert not out.exists()  # refused before anything was made
    taken = tmp_path / "taken"
    taken.mkdir()
    (taken / "fullchain.pem").write_text("old")
    done = subprocess.run(  # noqa: S603
        [bash, str(CERT_SCRIPT), "192.0.2.1", str(taken)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert done.returncode == 1  # an existing pair is never overwritten
    assert (taken / "fullchain.pem").read_text() == "old"


def test_the_certificate_script_and_proxy_template_hold_no_real_address() -> None:
    import re

    for path in (CERT_SCRIPT, ROOT / "deploy/core-cp/nginx/ratel-link.conf.example"):
        for address in re.findall(r"\b\d{1,3}(?:\.\d{1,3}){3}\b", path.read_text()):
            assert address.startswith(("192.0.2.", "198.51.100.", "203.0.113.", "127.", "0.")), (
                path.name,
                address,
            )


def test_callers_are_told_which_certificates_to_trust_and_core_cp_lets_them_in() -> None:
    assert "SSL_CERT_FILE=" in (ROOT / "deploy/core-up/ratel-meter.env.example").read_text()
    app_env = (ROOT / "deploy/bss-app/ratel-app.env.example").read_text()
    assert "SSL_CERT_FILE=" in app_env
    assert "ca-certificates.crt" in app_env  # a bundle, never the one certificate alone
    rules = (ROOT / "deploy/firewall/core-cp.nft").read_text()
    assert "ip saddr { $core_up, $bss_app } tcp dport 443 accept" in rules


def test_the_paystack_sandbox_check_refuses_anything_but_a_test_key_before_any_network_call() -> (
    None
):
    import os
    import shutil
    import subprocess
    import sys

    script = ROOT / "scripts/paystack_sandbox_check.py"
    assert shutil.which("env") is not None
    for key in ("", "sk_live_aaaaaaaaaaaaaaaaaaaa", "pk_test_aaaaaaaaaaaaaaaa", "CHANGE_ME"):
        env = {**os.environ, "PAYSTACK_SECRET_KEY": key, "PYTHONPATH": str(ROOT / "services")}
        done = subprocess.run(  # noqa: S603
            [sys.executable, str(script)],
            env=env,
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
        assert done.returncode == 2, (key, done.stderr)
        assert key == "" or key not in done.stdout + done.stderr  # the key is never echoed
