"""deploy/bss-app/ stays in step with the code and stays free of secrets and addresses."""

from __future__ import annotations

import re
from pathlib import Path

from services.app.config import Settings

ROOT = Path(__file__).resolve().parents[2]
DEPLOY = ROOT / "deploy/bss-app"
ENV_EXAMPLE = DEPLOY / "ratel-app.env.example"
UNIT = DEPLOY / "ratel-app.service"
INSTALL = DEPLOY / "install-release.sh"
ROLES = DEPLOY / "postgres-roles.sql"
NGINX = DEPLOY / "nginx/ratel-app.conf.example"


def _env_names(path: Path) -> set[str]:
    return {
        line.split("=", 1)[0]
        for line in path.read_text().splitlines()
        if line and not line.startswith("#") and "=" in line
    }


def _code(path: Path) -> str:
    return "\n".join(
        line for line in path.read_text().splitlines() if not line.lstrip().startswith("#")
    )


def _sql(path: Path) -> str:
    return "\n".join(
        line for line in path.read_text().splitlines() if not line.lstrip().startswith("--")
    )


# Variables the app's Python reads that are not its own settings: where to find the certificates it
# trusts, for RatelLink's self-signed proxy (deploy/core-cp/README.md).
NOT_SETTINGS = {"SSL_CERT_FILE"}


def test_every_setting_is_in_the_env_template() -> None:
    wanted = {name.upper() for name in Settings.model_fields}
    assert wanted | NOT_SETTINGS == _env_names(ENV_EXAMPLE)


def test_the_env_template_holds_placeholders_only() -> None:
    for line in ENV_EXAMPLE.read_text().splitlines():
        if line.startswith("#") or "=" not in line:
            continue
        name, value = line.split("=", 1)
        if name in ("DATABASE_URL", "RATEL_LINK_BASE_URL"):
            assert "<" in value, line  # a placeholder in angle brackets
        if name.endswith("_KEY"):
            assert value == "CHANGE_ME", line


def test_the_unit_runs_the_installed_layout_as_an_unprivileged_user() -> None:
    unit = UNIT.read_text()
    install = INSTALL.read_text()
    assert "\nUser=ratelbss\n" in unit and "\nGroup=ratelbss\n" in unit
    assert 'BASE="${RATEL_APP_BASE:-/opt/ratel-app}"' in install
    assert 'SERVICE_USER="${RATEL_APP_USER:-ratelbss}"' in install
    assert "EnvironmentFile=/etc/ratel-app/ratel-app.env" in unit
    assert "/opt/ratel-app/current/venv/bin/python -m uvicorn --factory app.main:create_app" in unit
    assert "--host 127.0.0.1" in unit  # only the proxy is allowed to reach it
    assert "--no-access-log" in unit  # access logs print paths, and paths hold IMSIs
    assert "\nCapabilityBoundingSet=\n" in unit and "\nAmbientCapabilities=\n" in unit
    assert "ReadOnlyPaths=/opt/ratel-app /etc/ratel-app" in unit


def test_the_unit_keeps_its_hardening() -> None:
    unit = UNIT.read_text()
    for directive in (
        "NoNewPrivileges=yes",
        "ProtectSystem=strict",
        "ProtectHome=yes",
        "PrivateTmp=yes",
        "PrivateDevices=yes",
        "RestrictAddressFamilies=AF_INET AF_INET6 AF_UNIX",
        "SystemCallFilter=~@privileged @resources",
        "UMask=0077",
    ):
        assert directive in unit, directive
    assert re.search(r"^StartLimitIntervalSec=", unit, re.M)  # in [Unit], where systemd reads it


def test_the_unit_waits_for_the_database() -> None:
    assert "After=network-online.target postgresql.service redis-server.service" in UNIT.read_text()


def test_the_install_script_cleans_up_on_any_failed_exit_and_changes_no_data() -> None:
    text = INSTALL.read_text()
    assert INSTALL.stat().st_mode & 0o100, "install-release.sh must be executable"
    assert "trap cleanup_on_failure EXIT" in text and "trap - EXIT" in text
    assert "services/app/main.py" in text and "requirements/app.txt" in text
    assert "import app.main" in text
    code = _code(INSTALL)
    # It installs files. It never starts anything and never touches the database.
    for forbidden in ("systemctl", "alembic upgrade", "-m alembic", "psql", "DATABASE_URL"):
        assert forbidden not in code, forbidden


def test_the_database_roles_hold_no_password_and_the_service_role_cannot_change_the_schema() -> (
    None
):
    sql = _sql(ROLES)
    assert "password" not in sql.lower().replace("\\password", "")  # set at a prompt, never here
    assert "CREATE ROLE ratel_owner LOGIN;" in sql and "CREATE ROLE ratel_app LOGIN;" in sql
    for forbidden in ("SUPERUSER", "CREATEDB", "CREATEROLE", "BYPASSRLS"):
        assert forbidden not in sql
    # The runtime role gets row rights and nothing that creates, alters or drops.
    grants = [line for line in sql.splitlines() if "TO ratel_app" in line]
    assert grants, "the service role is granted nothing"
    for line in grants:
        assert not re.search(r"\b(ALL|CREATE|TRUNCATE|REFERENCES|TRIGGER)\b", line), line
    assert "REVOKE ALL ON SCHEMA public FROM PUBLIC;" in sql


def test_the_proxy_template_denies_by_default_and_never_logs_a_path() -> None:
    text = NGINX.read_text()
    locations = re.findall(r"location ([^{]+)\{(.*?)\n    \}", text, re.S)
    public = [
        name.strip() for name, _ in locations if "deny  all;" not in _ and "return 404" not in _
    ]
    assert public == ["= /v1/pay/vouchers/redeem"]  # the one public path, an exact match
    for _name, block in locations:
        if "return 404" in block or "= /v1/pay/vouchers/redeem" in _name:
            continue
        assert "deny  all;" in block, block
    assert "log_format ratel_app_privacy" in text
    log_line = re.search(r"log_format ratel_app_privacy (.*);", text)
    assert log_line and "$request_uri" not in log_line.group(1) and "$uri" not in log_line.group(1)
    assert "proxy_pass http://127.0.0.1:8000;" in text
    assert "limit_req_status 429" in text


def test_no_file_in_bss_app_holds_a_secret_or_real_address() -> None:
    forbidden = [
        r"102\.214\.",
        r"172\.22\.",
        r"BEGIN [A-Z ]*PRIVATE KEY",
        r"rlk_[a-z0-9-]+\.[A-Za-z0-9_-]{20,}",
        r"postgresql(\+psycopg)?://[^:\s]+:(?!<password>)[^@\s]+@",
    ]
    for path in (p for p in DEPLOY.rglob("*") if p.is_file()):
        text = path.read_text()
        for pattern in forbidden:
            assert not re.search(pattern, text), f"{path.relative_to(ROOT)} matches {pattern}"


def test_the_public_redeem_path_has_its_own_limit_a_tiny_body_and_nothing_else_public() -> None:
    text = NGINX.read_text()
    block = re.search(r"location = /v1/pay/vouchers/redeem \{(.*?)\n    \}", text, re.S)
    assert block is not None
    body = block.group(1)
    assert "limit_req zone=ratel_redeem" in body
    assert "limit_req_zone $binary_remote_addr zone=ratel_redeem" in text
    assert "limit_req_status 429" in body
    assert re.search(r"client_max_body_size 1k;", body)
    assert "include /etc/nginx/ratel-pay-key.conf;" in body  # the key is added here and only here
    assert text.count("include /etc/nginx/ratel-pay-key.conf;") == 1  # in no other location
    assert "allow" not in body.replace(
        "# ", ""
    )  # it is public: no address list to forget to fill in
    assert not re.search(r"location\s+(~\*?\s+)?/v1/pay", text)  # no wider public prefix


JOBS = {
    "ratel-rating": "app.bss_money.rating_cli",
    "ratel-ledger-check": "app.bss_money.check_cli",
}


def test_the_job_units_run_the_installed_code_as_the_service_user_with_the_same_hardening() -> None:
    app_unit = UNIT.read_text()
    hardening = [
        line for line in app_unit.splitlines() if re.match(r"^(Protect|Restrict|Private)\w+=", line)
    ]
    assert hardening  # the app unit does carry hardening to compare against
    for name, module in JOBS.items():
        service = (DEPLOY / f"{name}.service").read_text()
        assert "\nType=oneshot\n" in service
        assert "\nUser=ratelbss\n" in service and "\nGroup=ratelbss\n" in service
        assert "EnvironmentFile=/etc/ratel-app/ratel-app.env" in service
        assert f"ExecStart=/opt/ratel-app/current/venv/bin/python -m {module}\n" in service
        assert "\nCapabilityBoundingSet=\n" in service and "\nAmbientCapabilities=\n" in service
        assert "ReadOnlyPaths=/opt/ratel-app /etc/ratel-app" in service
        assert "After=network-online.target postgresql.service" in service
        for line in hardening:
            assert line in service, (name, line)
        module_file = ROOT / "services" / (module.replace(".", "/") + ".py")
        assert module_file.exists(), module  # the unit points at a module that exists


def test_the_timers_start_their_service_and_catch_up_after_a_power_cut() -> None:
    rating = (DEPLOY / "ratel-rating.timer").read_text()
    ledger = (DEPLOY / "ratel-ledger-check.timer").read_text()
    assert "Unit=ratel-rating.service" in rating and "Unit=ratel-ledger-check.service" in ledger
    assert "OnCalendar=*:02/5" in rating  # two minutes after each agent interval ends
    assert "OnCalendar=daily" in ledger
    for timer in (rating, ledger):
        assert "\nPersistent=true\n" in timer  # the servers lose power every night
        assert "WantedBy=timers.target" in timer


def test_the_readme_installs_and_enables_the_timers() -> None:
    readme = (DEPLOY / "README.md").read_text()
    for name in ("ratel-rating", "ratel-ledger-check"):
        assert f"{name}.service" in readme and f"{name}.timer" in readme
    assert "systemctl enable --now ratel-rating.timer ratel-ledger-check.timer" in readme
