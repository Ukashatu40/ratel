# Runbook: put a new release on bss-app, switch on RatelPay and RatelDesk, and make a first sale

Keep it short. Use lab SIMs, lab numbers and made-up names. No password, key, card number or PIN goes into
this page, a ticket or a chat.

- **Last verified:** TODO (nobody has followed it on bss-app yet; the pieces are tested separately)
- **Owner:** the project lead
- **Runs on:** your machine (steps 1), bss-app (the rest). bss-app is already installed, its firewall is
  loaded and `healthz` answers ([deploy/bss-app/README.md](../../deploy/bss-app/README.md))

## 1. On your machine: build and copy

```bash
git switch main && git pull
OUT=~/ratel-releases && mkdir -p "$OUT"
scripts/release/build-release.sh app HEAD "$OUT"      # prints a SHA-256 (set RATEL_PIP=pip3 if pip is not found)
scripts/release/build-desk.sh HEAD "$OUT"             # prints a SHA-256 (needs Node and npm)
C=$(git rev-parse --short HEAD)
scp "$OUT/ratel-app-$C.tar.gz" "$OUT/ratel-desk-$C.tar.gz" deploy/bss-app/install-release.sh \
  deploy/bss-app/nginx/ratel-app.conf.example deploy/bss-app/nginx/add-pay-page-and-desk.py \
  ratelplus-bss-app:/tmp/
```

## 2. On bss-app: install the release, migrate, restart

`/tmp` is emptied at every reboot, so do this in one sitting.

```bash
cd /tmp
sha256sum ratel-app-*.tar.gz ratel-desk-*.tar.gz        # the same two values as in step 1
REL=$(basename /tmp/ratel-app-*.tar.gz .tar.gz)         # exactly one file must match
sudo ./install-release.sh $REL.tar.gz python3.12
sudo systemd-run --wait --pipe -p User=ratelbss -p EnvironmentFile=/etc/ratel-app/ratel-app-migrate.env \
  -p Environment=PYTHONPATH=/opt/ratel-app/current/services -p Environment=PYTHONDONTWRITEBYTECODE=1 \
  /opt/ratel-app/current/venv/bin/python -m alembic -c /opt/ratel-app/current/services/app/alembic.ini upgrade head
sudo systemctl restart ratel-app.service
sleep 3; curl -s http://127.0.0.1:8000/healthz; echo
curl -s -o /dev/null -w 'readyz %{http_code}\n' http://127.0.0.1:8000/readyz       # 200
```

## 3. RatelDesk's files

```bash
NAME=$(basename /tmp/ratel-desk-*.tar.gz .tar.gz)       # exactly one file must match
sudo install -d -m 0755 /var/www/desk-releases "/var/www/desk-releases/$NAME"
sudo tar -xzf "/tmp/$NAME.tar.gz" --strip-components=1 -C "/var/www/desk-releases/$NAME"
sudo chown -R root:root "/var/www/desk-releases/$NAME" && sudo chmod -R go-w "/var/www/desk-releases/$NAME"
sudo ln -sfn "/var/www/desk-releases/$NAME" /var/www/ratel-desk
```

## 4. nginx: add the RatelPay page and the Desk to the live config

The live file was made from an older template. The script adds the two new blocks and changes nothing else; no
address is typed again. Give it the office and VPN range (Muhammad's, or for a first test the address you browse
from; it is also what lets you open the Desk):

```bash
sudo cp -a /etc/nginx/conf.d/ratel-app.conf "/etc/nginx/conf.d/ratel-app.conf.bak-$(date +%F-%H%M)"
read -r -p 'office or VPN range: ' OFFICE
sudo python3 /tmp/add-pay-page-and-desk.py /tmp/ratel-app.conf.example /etc/nginx/conf.d/ratel-app.conf --office "$OFFICE"
sudo nginx -t && sudo systemctl reload nginx
```

If `nginx -t` complains, put the copy back (`sudo cp -a /etc/nginx/conf.d/ratel-app.conf.bak-<date-time> /etc/nginx/conf.d/ratel-app.conf`)
and tell whoever reviews this; do not edit by hand under pressure. Check on the server itself:

```bash
curl -sk -o /dev/null -w 'pay page %{http_code}\n' https://127.0.0.1/pay                    # 200
curl -sk -X POST https://127.0.0.1/v1/pay/vouchers/redeem -H 'Content-Type: application/json' -d '{}' \
  -o /dev/null -w 'redeem (empty body) %{http_code}\n'                                      # 422: the proxy added the key
```

(The Desk at `https://127.0.0.1/` answers 200 only if `127.0.0.1` is inside the range you gave; test it from your
browser instead.)

## 5. The lab's data

Every command below is run on bss-app. The helper loads the app's settings:

```bash
bss() {
  sudo -u ratelbss env PYTHONPATH=/opt/ratel-app/current/services \
    bash -c 'set -a; . /etc/ratel-app/ratel-app.env; set +a; exec "$@"' _ \
    /opt/ratel-app/current/venv/bin/python -m "$@"
}
```

**Staff.** An admin exists already. For the role test make an agent (the password is typed at a prompt):

```bash
bss app.bss_lines.staff_cli create --email agent@example.test --name "Lab Agent" --role agent
bss app.bss_lines.staff_cli list
```

**SIMs and numbers** (RatelBSS keeps a list; the keys live in RatelLink, so the SIMs must be imported there too).
Type the lab's own ICCIDs, IMSIs and numbers; the files hold identifiers, so delete them after:

```bash
cat > /tmp/sims.csv      # type or paste, then press Ctrl-D on an empty line:  iccid,imsi,batch  then one SIM per line
cat > /tmp/numbers.csv   # msisdn, then one number per line, in the form 234XXXXXXXXXX
bss app.bss_lines.stock_cli add-sims --file /tmp/sims.csv
bss app.bss_lines.stock_cli add-numbers --file /tmp/numbers.csv
bss app.bss_lines.stock_cli summary
shred -u /tmp/sims.csv /tmp/numbers.csv
```

**A plan, and a voucher batch** ([demo-setup.md](demo-setup.md) explains the values; TODO(PRD) for the real ones):

```bash
bss app.bss_money.ops_cli plan add --name "Lab weekly" --price-kobo 100000 --validity-days 7 \
  --data-bytes 2000000000 --up-mbps 10 --down-mbps 20 --on-exhaustion slow --slow-up-mbps 0.5 --slow-down-mbps 1
bss app.bss_money.ops_cli plan list
bss app.bss_money.voucher_cli create-batch --batch lab-1 --count 5 --value-kobo 120000 --out /tmp/lab-1.csv
for to in approved sent_to_printer in_stock on_sale; do bss app.bss_money.voucher_cli set-state --batch lab-1 --to $to; done
```

`/tmp/lab-1.csv` holds the card numbers and PINs (readable by `ratelbss` and root only). Show it on the console
with `sudo head -3 /tmp/lab-1.csv` when you need one card; never copy it into a chat or a file in the repo; `sudo shred -u` it when done.

## 6. A first sale, from your browser

The certificate is self-signed, so the browser warns once: accept it for this host.

1. Open `https://<bss-app>/` and sign in as the admin. The menu shows Dashboard, Sell SIM, Lines, Customers, Plans
   & Bundles and Wallet (no Stock, Reports or Staff: they have no API yet).
2. **Sell SIM**: register a customer (made-up name, an 11-digit test NIN, an email). Customers: open the
   customer as an **admin** and Approve (an agent is told only an admin decides).
3. Sell SIM again: pick the customer, a SIM, a number and the plan, then **Create line**.
4. **The customer pays:** open `https://<bss-app>/pay` (in another tab or on a phone), type the line's number
   (`0…` or `234…`), a card number and its PIN from `/tmp/lab-1.csv`, and press **Add credit**. The Desk's
   wallet balance follows within five seconds.
5. In the Desk: **Buy plan**, then **Activate line**. RatelLink must be reachable from bss-app with its key.
6. Open the line: state `active`, a History entry for each step, the wallet balance after the purchase. As the
   agent: no **Terminate** button; as the admin it is there (do not press it on a line you need).
7. Dashboard and Wallet: the top-up and the purchase show in the ledger as `top_up`, `purchase` and `vat`.

## 7. Roll back and forward once (the rehearsal)

```bash
ls -1t /opt/ratel-app/releases            # newest first; the second is the previous one
OLD=$(ls -1t /opt/ratel-app/releases | sed -n 2p)
sudo ln -sfn "/opt/ratel-app/releases/$OLD" /opt/ratel-app/current && sudo systemctl restart ratel-app.service
sleep 3; curl -s -o /dev/null -w 'readyz after rollback %{http_code}\n' http://127.0.0.1:8000/readyz
sudo ln -sfn "/opt/ratel-app/releases/$REL" /opt/ratel-app/current && sudo systemctl restart ratel-app.service
sleep 3; curl -s -o /dev/null -w 'readyz after the way forward %{http_code}\n' http://127.0.0.1:8000/readyz
```

A code rollback changes no data; a migration is not undone this way (see the README). The Desk goes back the same
way: `sudo ln -sfn /var/www/desk-releases/<older folder> /var/www/ratel-desk`.
Write the date and the result into "Last verified" above, and fix any step that did not work.
