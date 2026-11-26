# Runbook: RatelDesk at desk.ratelplus.net (decision 61)

Never put an address, a key or a password into this page, a ticket or a chat. Say "the site's public address", not the address.

- **Last verified:** TODO (written 2026-11-26; not yet run on bss-app)
- **Owner:** the project lead (DNS and the site router: the network team)
- **Runs on:** the domain's DNS provider, the site router, the laptop, bss-app

After this, `https://desk.ratelplus.net/` opens RatelDesk from anywhere, with a Let's Encrypt certificate that renews itself.
Only the Desk, staff sign-in and the staff API become public ([decision 61](../DECISIONS_PENDING.md), risk R-20). The
meter, calls, self-care, webhook and `/healthz` paths keep their address lists. Nothing in the app or its settings changes.

## 0. Before you start (the network team)

| Check | Who | Done |
| --- | --- | --- |
| An **A record** `desk.ratelplus.net` points at the **site's public address**. `dig +short desk.ratelplus.net` on the laptop prints it (do not paste it) | whoever holds the ratelplus.net DNS account, with the address from the network team | |
| The **site router forwards TCP 80 and 443** from the public address to bss-app | the network team | |
| Nothing else on the site already uses ports 80 or 443 on that public address | the network team | |

DNS can take minutes to an hour to reach every resolver. Go on only when `dig` prints the address.

## 1. The firewall: open port 80 on bss-app

On the laptop, in the repository, on `main` after the merge:

```bash
scp deploy/firewall/bss-app.nft deploy/bss-app/nginx/make-desk-public.py ratelplus-bss-app:/tmp/
```

On bss-app. The rollback timer removes the firewall by itself after ten minutes if the new rules lock you out
([firewall README](../../deploy/firewall/README.md), "Apply"):

```bash
sudo cp -p /etc/ratel-fw/ratel-fw.nft /root/ratel-fw.nft.before-desk-public
sudo install -m 0644 /tmp/bss-app.nft /etc/ratel-fw/ratel-fw.nft
sudo nft -c -f /etc/ratel-fw/ratel-fw.nft && echo syntax ok
sudo systemd-run --on-active=600 --unit=ratel-fw-rollback /usr/sbin/nft delete table inet ratel_fw
sudo nft -f /etc/ratel-fw/ratel-fw.nft
```

From a **second terminal on the laptop**, open a new SSH connection to bss-app. If it connects, back in the first one:

```bash
sudo nft list tables | grep ratel_fw
sudo systemctl stop ratel-fw-rollback.timer
sudo nft list chain inet ratel_fw input | grep -E 'dport (80|443)'
```

Expect `table inet ratel_fw`, and both `tcp dport 443 accept` and `tcp dport 80 accept`.

## 2. nginx, step one: answer the certificate check

```bash
sudo cp -p /etc/nginx/conf.d/ratel-app.conf /root/ratel-app.conf.before-desk-public
sudo install -d -m 0755 /var/www/letsencrypt
sudo python3 /tmp/make-desk-public.py acme /etc/nginx/conf.d/ratel-app.conf --name desk.ratelplus.net
sudo nginx -t && sudo systemctl reload nginx
```

Expect `done`, then `syntax is ok` and `test is successful`. The backup goes to `/root`, not `conf.d`, so nginx never loads it.

Check from **outside the site** (a phone on another network, Wi-Fi off) that `http://desk.ratelplus.net/` answers. It
redirects to `https://`, which shows a certificate warning for now. That is expected until step 3. No answer at all means
DNS or the router forward (section 0).

## 3. The certificate

`certbot` is a new package on bss-app (from Ubuntu's archive):

```bash
sudo apt-get install -y certbot
sudo certbot certonly --webroot -w /var/www/letsencrypt -d desk.ratelplus.net --deploy-hook "systemctl reload nginx"
```

certbot asks for an email address for expiry notices (use the team's, typed at the prompt) and to accept Let's Encrypt's
terms: those answers are yours to give. Expect `Successfully received certificate` and the path
`/etc/letsencrypt/live/desk.ratelplus.net/fullchain.pem`. Then prove renewal works, which changes nothing:

```bash
sudo certbot renew --dry-run
systemctl list-timers --all --no-pager | grep -i certbot
```

Expect `Congratulations, all simulated renewals succeeded` and a `certbot.timer`. The deploy hook reloads nginx after each
renewal.

## 4. nginx, step two: the name, the certificate, and the Desk opened

```bash
sudo python3 /tmp/make-desk-public.py public /etc/nginx/conf.d/ratel-app.conf --name desk.ratelplus.net
sudo nginx -t && sudo systemctl reload nginx
```

It refuses if the certificate is not there yet. It adds the name next to the old one, points the HTTPS server at the new
certificate, and removes the address list from three blocks only (each now says `PUBLIC since decision 61`):

```bash
sudo grep -c 'PUBLIC since decision 61' /etc/nginx/conf.d/ratel-app.conf
```

Expect `4`: the three blocks, plus the redirect on port 80.

## 5. Check it, from outside the site

On a phone on another network (Wi-Fi off), or the laptop away from the office:

| Open | Expect |
| --- | --- |
| `https://desk.ratelplus.net/` | RatelDesk's sign-in page, a valid padlock, no warning |
| Sign in as the admin, open Lines | The lines list, as through the tunnel |
| `https://desk.ratelplus.net/pay` | The RatelPay page |
| `http://desk.ratelplus.net/` | Redirected to `https://` |

And that the closed paths stay closed, from the laptop away from the office:

```bash
for p in /healthz /v1/usage /v1/calls; do printf '%s ' "$p"; curl -s -o /dev/null -w '%{http_code}\n' -X POST "https://desk.ratelplus.net$p"; done
```

Expect `403` for all three.

The SSH tunnel to `https://localhost:8443/` still works, but now shows a name warning: the certificate is for
`desk.ratelplus.net`, not `localhost`.

## Afterwards

- **Payments:** if card payments are in use, `PAYMENT_CALLBACK_URL` in `/etc/ratel-app/ratel-app.env` may still name the old
  host. Changing it is a settings change and an app restart: do it on a quiet day, not before a demo.
- **Watch for guessing** for a few days (risk R-20): `sudo awk '$4==401 || $4==429' /var/log/nginx/ratel-app.access.log | tail`
  shows refused and rate-limited requests (time, address, method, status; the log keeps no path, on purpose). Many from one
  address means someone is trying passwords.
- Staff accounts nobody uses: disable them. Staff passwords: long and unique.

## Roll back

On bss-app, either step on its own:

```bash
sudo cp -p /root/ratel-app.conf.before-desk-public /etc/nginx/conf.d/ratel-app.conf && sudo nginx -t && sudo systemctl reload nginx
sudo cp -p /root/ratel-fw.nft.before-desk-public /etc/ratel-fw/ratel-fw.nft && sudo nft -f /etc/ratel-fw/ratel-fw.nft
```

The Desk is then office-only again, as before. The certificate can stay; it does no harm.
