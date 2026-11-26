#!/usr/bin/env python3
"""Serve RatelDesk publicly under its own name (decision 61), in two steps.

    sudo python3 make-desk-public.py acme   <live file> --name desk.ratelplus.net
    sudo python3 make-desk-public.py public <live file> --name desk.ratelplus.net

The live file is /etc/nginx/conf.d/ratel-app.conf.

`acme` adds a plain-HTTP server for the name that answers Let's Encrypt's check from
/var/www/letsencrypt and sends everything else to HTTPS. Nothing else changes. Run it, reload nginx,
then ask certbot for the certificate (docs/runbooks/desk-public-domain.md).

`public` needs that certificate. It adds the name to the HTTPS server, points it at the certificate
under /etc/letsencrypt/live/<name>/, and removes the allow and deny lines from three blocks only:
the Desk (`location /`), staff sign-in (`location = /v1/auth/login`) and the staff API
(`location /v1/`). Every other block keeps its addresses: the meter's /v1/usage, the voice VM's
/v1/calls and self-care paths, Paystack's webhook and /healthz stay closed to the internet. The
sign-in rate limit (`ratel_login`) and the app's lock after 5 wrong passwords stay as they are.

It refuses a file it does not recognise and does nothing if the step is done already. Make a copy
of the live file first, then run `nginx -t` before reloading.
"""

from __future__ import annotations

import argparse
import os
import re
import sys
from pathlib import Path

NAME = re.compile(r"(?=.{1,253}$)([a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z]{2,63}")
HTTPS_SERVER = "server {\n    listen 443 ssl;\n"
SERVER_NAME = re.compile(r"(\n    listen 443 ssl;\n    server_name )([^;]+);")
CERT = re.compile(r"(\n    ssl_certificate\s+)[^;]+;")
CERT_KEY = re.compile(r"(\n    ssl_certificate_key\s+)[^;]+;")
ALLOW_OR_DENY = re.compile(r"\n +(allow [^;]+|deny +all);")
OPENED = ("= /v1/auth/login", "/v1/", "/")
MARK = "        # PUBLIC since decision 61 (2026-11-26): no address list here.\n"
WEBROOT = "/var/www/letsencrypt"
LIVE = "/etc/letsencrypt/live"


def acme_block(name: str) -> str:
    return (
        f"# Plain HTTP for {name} (decision 61): only Let's Encrypt's check, from {WEBROOT};\n"
        "# everything else is sent to HTTPS. Nothing is served over plain HTTP.\n"
        "server {\n"
        "    listen 80;\n"
        f"    server_name {name};\n"
        "    location /.well-known/acme-challenge/ {\n"
        f"        root {WEBROOT};\n"
        "    }\n"
        "    location / {\n"
        "        return 301 https://$host$request_uri;\n"
        "    }\n"
        "}\n\n"
    )


def _block(text: str, header: str) -> re.Match[str]:
    found = re.search(rf"\n    location {re.escape(header)} \{{\n.*?\n    \}}\n", text, re.S)
    if found is None:
        raise ValueError(f"the live file has no `location {header}` block: not a file this knows")
    return found


def add_acme(live: str, name: str) -> str:
    if f"    listen 80;\n    server_name {name};\n" in live:
        return live
    if live.count(HTTPS_SERVER) != 1:
        raise ValueError("the live file does not have exactly one HTTPS server: edit it by hand")
    return live.replace(HTTPS_SERVER, acme_block(name) + HTTPS_SERVER, 1)


def make_public(live: str, name: str) -> str:
    # Only the HTTPS server: the plain-HTTP server of the acme step has its own `location /`.
    if live.count(HTTPS_SERVER) != 1:
        raise ValueError("the live file does not have exactly one HTTPS server: edit it by hand")
    start = live.index(HTTPS_SERVER)
    head, out = live[:start], live[start:]
    server_name = SERVER_NAME.search(out)
    if server_name is None or len(CERT.findall(out)) != 1 or len(CERT_KEY.findall(out)) != 1:
        raise ValueError("the HTTPS server's name or certificate lines are not where expected")
    if name not in server_name.group(2).split():
        out = SERVER_NAME.sub(lambda m: f"{m.group(1)}{m.group(2)} {name};", out, count=1)
    out = CERT.sub(lambda m: f"{m.group(1)}{LIVE}/{name}/fullchain.pem;", out, count=1)
    out = CERT_KEY.sub(lambda m: f"{m.group(1)}{LIVE}/{name}/privkey.pem;", out, count=1)
    for header in OPENED:
        block = _block(out, header).group(0)
        opened = ALLOW_OR_DENY.sub("", block)
        if MARK not in opened:
            first = opened.index("{\n") + 2
            opened = opened[:first] + MARK + opened[first:]
        out = out.replace(block, opened, 1)
    return head + out


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="make-desk-public.py")
    parser.add_argument("step", choices=("acme", "public"))
    parser.add_argument("live", type=Path)
    parser.add_argument("--name", required=True, help="the public name, e.g. desk.ratelplus.net")
    parser.add_argument(
        "--cert-dir", type=Path, help=f"where the certificate is (default {LIVE}/<name>)"
    )
    args = parser.parse_args(argv)
    name = args.name.lower()
    if not NAME.fullmatch(name):
        sys.stderr.write("refused: --name must be a domain name such as desk.example.org\n")
        return 1
    live = args.live.read_text()
    try:
        if args.step == "acme":
            out = add_acme(live, name)
        else:
            cert_dir = args.cert_dir or Path(LIVE) / name
            missing = [f for f in ("fullchain.pem", "privkey.pem") if not (cert_dir / f).exists()]
            if missing:
                raise ValueError(
                    f"no certificate yet ({', '.join(missing)} missing in {cert_dir}): "
                    "run the acme step and certbot first"
                )
            out = make_public(live, name)
    except ValueError as exc:
        sys.stderr.write(f"refused: {exc}\n")
        return 1
    if out == live:
        sys.stdout.write("nothing to change: the step is done already\n")
        return 0
    tmp = args.live.with_name(args.live.name + ".new")
    tmp.write_text(out)
    tmp.chmod(args.live.stat().st_mode & 0o777)
    os.replace(tmp, args.live)
    sys.stdout.write("done: now run `sudo nginx -t` and, if it is ok, reload nginx\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
