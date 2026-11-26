# Runbook: moving the VMs to the datacenter

- **Last verified:** not yet followed (written 2026-11-26)
- **Owner:** TODO (network team for the core and the radios, software team for bss-app and voice)
- **Runs on:** core-cp, core-up, voice, bss-app, ops, and the three eNodeBs

## Service and purpose

The five VMs are cloned to a new server in the datacenter, which becomes production. Every VM gets
a new address. The eNodeBs stay where they are, so the radio side (S1) now crosses the network to
the datacenter. The current server stays as it is until the datacenter has passed every test below,
and is the way back.

Real addresses never go in this repository (it is public). Keep the old to new table in the Build
Plan, and write `<old-core-cp>`, `<new-core-cp>` and so on here.

## Decide before cloning (blocking)

1. **The S1 path between the eNodeB site and the datacenter.** The eNodeBs need to reach core-cp on
   SCTP port 36412 (S1-MME) and core-up on UDP port 2152 (S1-U, user traffic), and core-up needs to
   reach them back on 2152. SCTP rarely survives NAT or consumer firewalls. Use a site-to-site tunnel
   (IPsec or WireGuard) between the eNodeB site router and the datacenter, so S1 is private and not
   on the open internet (3GPP expects it protected), and no NAT sits on it.
2. **MTU on that path.** A tunnel adds bytes to every GTP packet, and GTP already adds its own. Too
   large and calls and web pages stall in ways that look random (the voice VM already needed an MTU
   route on 20 Nov). Measure the path MTU through the tunnel before cutover and set the eNodeB S1 MTU
   or clamp TCP MSS for the phone pools (10.45.0.0/16 data, 10.46.0.0/16 IMS).
3. **Latency.** Measure the round trip from the eNodeB site to the datacenter (ping through the
   tunnel, 10 minutes, busy hour). Calls stay good under about 50 ms one way. Write the result in the
   Build Plan.
4. **Internet breakout.** Phone data now leaves through the datacenter. core-up must NAT the
   10.45.0.0/16 pool to a datacenter public address, with enough transit for every customer.
5. **The way data is carried over.** Cloning copies the databases at that moment. Anything sold,
   activated, topped up or used after the clone exists only on the old server. Pick one:
   - freeze: no activations, sales or top-ups in RatelDesk from the clone to the cutover, and stop
     the rating and call-charging timers on the old bss-app at cutover; or
   - re-copy at cutover: take a fresh backup of bss-app's PostgreSQL (docs/runbooks/bss-backup-restore.md)
     and core-cp's MongoDB (docs/runbooks/mongodb-core-cp.md) on the old server and restore them on
     the new one, minutes before the eNodeBs move.
   Never run both servers' timers against live customers: two sets of charges, two SMS senders.
6. **Names instead of addresses where possible.** A DNS name for bss-app (used by core-up, voice and
   RatelDesk) and for RatelLink's proxy means the next move changes DNS, not configs. TLS
   certificates issued for names survive a move; certificates issued for an address do not.

## Before cloning: list every address on the old VMs

On each old VM, with the old addresses of all five VMs in `OLD` (only on that VM's shell, not in a
file or the repository), list every file that holds one:

```bash
OLD='<old-core-cp>|<old-core-up>|<old-voice>|<old-bss-app>|<old-ops>'
sudo grep -rIlE "${OLD//./\\.}" /etc /opt /home/*/docker_open5gs /home/*/ratel-ussd 2>/dev/null | sort
```

Keep the lists with the Build Plan's address table. They are the checklist for the next section; a
file on a list and not changed below is a bug waiting.

## After cloning: what changes, VM by VM

The clones boot with the old addresses in their configs. Change these, then reboot each VM once.

### core-cp

- `/etc/open5gs/mme.yaml`: the S1AP address (what the eNodeBs connect to) and GTP-C.
- `/etc/open5gs/smf.yaml`: PFCP towards core-up, and the **P-CSCF address** handed to phones at
  attach (the new voice address). Phones that keep the old one cannot register for calls.
- freeDiameter files (`/etc/freeDiameter/*.conf`): `ListenOn` and every `ConnectPeer`, including the
  PCRF's Rx peer to the P-CSCF on voice (port 3871).
- The MSC (SGs) address if the MME config names it.
- RatelLink: `deploy/core-cp/nginx/ratel-link.conf.example` lists the callers (`allow` bss-app and
  core-up) and the host name; the certificate if it was issued for an address.
- Firewall: `/etc/ratel-fw/addresses.nft` (radios, core_up, bss_app), then `systemctl restart ratel-fw`.

### core-up

- `/etc/open5gs/sgwu.yaml` and `upf.yaml`: PFCP and the **GTP-U address the eNodeBs send user
  traffic to**. It must be the address reachable through the S1 tunnel, not a datacenter-internal
  one the eNodeB site cannot see.
- NAT for 10.45.0.0/16 to the datacenter public address (decision 4).
- RatelMeter agent: `/etc/ratel-meter/ratel-meter.env` (RatelLink and meter API addresses if they
  are not 127.0.0.1 tunnels), certificates it trusts.
- Firewall: `/etc/ratel-fw/addresses.nft` (radios, core_cp).

### voice

- `~/docker_open5gs/.env`: the host and container addresses the IMS uses; the IMS DNS zones are
  built from them. Then recreate the stack (`docker compose up -d`) and check every container is up.
- The Rx (Diameter) peer to the PCRF on core-cp.
- The P-CSCF MTU route (20 Nov) if the path MTU changed.
- Self-care and customer SMS: `~/ratel-ussd/network/voice/ussd/ussd.env` (`RATEL_PAY_URL`, the new
  bss-app) and `bss-ca.pem` (the new bss-app certificate if it changed). Then `./run-ussd.sh`.
- RatelMeter call agent: `/etc/ratel-meter/ratel-meter-calls.env`.
- Firewall: `/etc/ratel-fw/addresses.nft` (pyhss_clients).

### bss-app

- nginx (`/etc/nginx/conf.d/ratel-app.conf`): every `allow` that names the voice VM (call records and
  the 555/USSD self-care block) and core-up (usage), the office and VPN range, `server_name`.
- `/etc/ratel-app/ratel-app.env`: `RATEL_LINK_BASE_URL`, `PAYMENT_CALLBACK_URL`.
- TLS certificate for the new name or address; voice's `bss-ca.pem` must match it.
- Firewall: `deploy/firewall/bss-app.nft` and `/etc/ratel-fw/addresses.nft`.
- RatelDesk public name (decision 61, docs/runbooks/desk-public-domain.md): point DNS at the new
  address, not the old one.

### ops

- Whatever it watches by address (TODO: list when ops is confirmed).

### Outside the VMs

- **eNodeBs (all three):** the MME address becomes `<new-core-cp>` as seen through the tunnel. They
  learn the S-GW address from the MME, so that is the only core address they hold. Change one at a
  time (see Cutover).
- **The payment provider's dashboard:** the callback URL, if it holds an address.
- **VOS3000:** the gateway entry for interconnect, when interconnect is built (not live).
- **Remote access:** WireGuard peers that name the old server.

## Health checks after the move (before any customer traffic)

On each VM: every service up (`systemctl --failed` empty, `docker ps` all Up on voice), clock in sync
(`timedatectl`), firewall loaded, backups writing to their new place.

- core-cp: `curl -s http://127.0.0.1:8081/readyz` (RatelLink, 200), MME listening on 36412.
- bss-app: `/healthz` and `/readyz` 200, RatelDesk sign-in, `systemctl list-timers 'ratel-*'`.
- voice: `docker exec pcscf kamcmd ulpcscf.status` answers, Rx peer up
  (`ss -tan | grep :3871` on core-cp shows ESTAB).
- From voice: `curl --cacert bss-ca.pem "$RATEL_PAY_URL/v1/pay/airtime"` answers 200.

## Cutover

1. Old server: freeze, or take the final backups (decision 5).
2. New server: restore them if re-copying; start the timers.
3. Move **one** eNodeB to the new MME. On a phone under it: attach, data (open a page), call both ways
   to a phone on the same eNodeB, SMS both ways, text MENU to 555 (the reply shows 555), RatelDesk
   shows the line's usage after the next rating run.
4. If that passes, move the other two, one at a time, testing a call on each.
5. Old server: stop the rating, call-charging and customer SMS timers, so it can never charge or
   text anyone. Keep it powered and untouched for two weeks.

## Common failures

| Symptom | Likely cause | What to do |
| ------- | ------------ | ---------- |
| eNodeB never shows S1 up | SCTP blocked or NATed on the path | Check the tunnel; `ss -A sctp -l` on core-cp; firewall `radios` |
| Attach works, no data | GTP-U address not reachable from the eNodeB site, or no NAT for 10.45.0.0/16 | Fix sgwu/upf GTP-U address; NAT rule |
| Data works, pages stall | MTU | Lower eNodeB S1 MTU or clamp MSS |
| Phones show 4G but cannot call | SMF still hands out the old P-CSCF, or Rx peer down | smf.yaml P-CSCF; freeDiameter peers |
| 555 does not answer | `ussd.env` or `bss-ca.pem` still old, or bss-app nginx allows the old voice address | Fix and `./run-ussd.sh`; nginx `allow` |
| Usage stops in RatelDesk | meter agent points at the old bss-app, or nginx allows the old core-up | Agent env; nginx `allow` |

## Rollback

Point the eNodeBs back at the old MME address. The old server must still be running, unchanged, with
its timers on again. Anything done on the new server after cutover (sales, top-ups, usage) is then
missing on the old one: note the cutover time and reconcile from the new server's backup.

## Escalation

Network team for S1, the tunnel and the radios; software team for bss-app, voice and RatelLink;
project lead for the cutover decision. TODO: names and phone numbers.
