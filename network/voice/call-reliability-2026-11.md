# Voice call reliability, 16 to 20 Nov 2026

Why calls failed after P-CSCF restarts and failed intermittently afterwards, what was changed on the live voice VM, and how to recover. All times UTC (Lagos is UTC+1). Phones are named by the last three digits of the SIM.

Status on 20 Nov 13:35: calls work. Two root causes fixed. One handset issue open. One fix is not yet persistent across a pcscf container restart.

## 1. Voice down after a P-CSCF restart (16 and 17 Nov)

1. The pcscf container was restarted on 16 Nov while testing a caller ID change.
2. Rx works like this: the PCRF on core-cp connects to the P-CSCF's Diameter acceptor, 172.22.0.21 port 3871 (ConnectPeer in pcrf.conf). The P-CSCF's own Peer entry for pcrf.localdomain:3868 never resolves inside the container. It fails once at startup and is harmless.
3. After the restart, open5gs-pcrfd kept dead connections (25 sockets in CLOSE-WAIT) and never made a working new one.
4. With WITH_RX on, the P-CSCF waits for the Rx AAR before answering REGISTER. With no Rx peer, REGISTER was never answered.
5. Wrong turn: WITH_RX was turned off. Phones registered, but calls stopped after 183 and PRACK, because the dedicated voice bearer is requested over Rx. Reverted.

Fix on 17 Nov: WITH_RX restored and pcscf restarted, then on core-cp `sudo systemctl restart open5gs-pcrfd`. One ESTAB connection to 3871 followed and has stayed up.

Side effect: the PCRF keeps Gx sessions in memory only. Its restart lost every existing data session, so every phone attached before it got "AAR failed on subscription to signalling" on REGISTER until it re-attached (airplane mode toggle).

## 2. Intermittent call failures (19 and 20 Nov)

Symptom: calls sometimes failed and worked again after an airplane mode toggle.

### Root cause A: a 3 second P-CSCF transaction timer

- `modparam("tm", "fr_timer", 3000)` in kamailio_pcscf.cfg: if the called phone sends nothing within 3 seconds, the P-CSCF fails the call with 408.
- Evidence (19 Nov, 451 calling 454): INVITE sent to the phone at 10:45:37.103, P-CSCF gave up at 10:45:40.087, the phone's first reply arrived at 10:45:40.577. The I-CSCF then tried another S-CSCF and the caller got "500 Server error on LIR select next S-CSCF".
- The called phone was idle and had to be paged (service request 0.3 s after the INVITE).
- Fix (19 Nov 10:53): `docker exec pcscf kamcmd cfg.set_now_int tm fr_timer 10000` at runtime (pcscf log: "tm.fr_timer has been changed to 10000"), and the same value in kamailio_pcscf.cfg line 325 on the voice VM. Backup there: kamailio_pcscf.cfg.bak-frtimer-20261119. The I-CSCF and S-CSCF already use 10000.
- Rollback: `kamcmd cfg.set_now_int tm fr_timer 3000` and restore the backup file.
- `kamcmd cfg.get tm fr_timer` is not readable on this build, and kamcmd returns success even on an RPC error, so an `&&` chain does not stop on it.

### Root cause B: IMS packets larger than the core-up tunnel

- On core-up, ogstun2 (IMS pool 10.46.0.0/16) has MTU 1400; ens18 has 1500.
- Packets from the P-CSCF over 1400 bytes with "don't fragment" set were dropped on core-up (IpFragFails 2622).
- A capture on core-up showed 1480 byte ESP packets from 172.22.0.21 arriving on ens18 and never leaving on ogstun2, while small packets passed.
- The P-CSCF only learned the 1400 limit after losing packets, and forgot it after about 10 minutes (`ip route get` showed "cache expires 485sec mtu 1400"). So the first large SIP message after a quiet spell, typically a call to an idle phone, was lost and retried, costing seconds.
- Fix (20 Nov 13:31), inside the pcscf container network namespace:

  ```
  P=$(docker inspect -f "{{.State.Pid}}" pcscf)
  sudo nsenter -t $P -n ip route add 10.46.0.0/16 via 172.22.0.1 dev eth0 mtu lock 1400
  ```

- Result for a call to 454: INVITE to first reply 3.20 s before, 0.52 s after. INVITE to 180 Ringing 3.83 s before, 1.14 s after.
- Rollback: the same command with `ip route del 10.46.0.0/16 via 172.22.0.1 dev eth0`.
- Not persistent: the route is lost when the pcscf container restarts. It belongs in the container startup (the container already has NET_ADMIN for IPsec), through a reviewed change.
- Raising ogstun2 to 1500 was rejected: the GTP header would then push packets over 1500 on the radio side.

## 3. SIM 452 in the UNIWA handset (open)

- Calls to it (19 Nov 10:55): INVITEs went to its registered address, which the SMF confirms was its current IMS address. No reply, and the MME shows no paging. The core believed the phone was connected while it was not listening: handset or radio side.
- Calls from it (19 Nov 10:56): the IMS INVITE went out normally. Ten seconds later the phone sent an Extended service request (fall back to 2G/3G), left LTE and showed emergency only. A handset silent redial to circuit switched, which fails here because there is no 2G/3G.
- Next: put SIM 452 in a handset that works. If it works there, the UNIWA is the problem.

## Ruled out, with evidence

- Rx peer flapping: one ESTAB to 3871 since 17 Nov 11:21 and no AAR failures on 19 and 20 Nov. The `drop_serviced_peer` log line is a hand-over between receivers, not a disconnect.
- MME timers: "Mobile Reachable timer started" lines are normal idle transitions; no implicit detach found.
- The 19 Nov 10:12 drop of several phones: each phone sent its own Detach request, most likely airplane toggles done as the workaround.
- Stale S-CSCF contacts: S-CSCF and P-CSCF agreed for every registered phone.
- IPsec entries: 28 states and 32 policies for two IPsec phones. A slow leak (`delete_unused_sa` netlink error on every REGISTER), not the cause.
- Foreign SIM attaches: thousands per day, all rejected by PLMN access control. Noise.
- I-CSCF `t_set_fr(5000, 5000)`: only in route[register].

## Recovery procedure until both fixes are in startup

Avoid restarting pcscf or open5gs-pcrfd. If pcscf restarts anyway:

1. core-cp: `sudo systemctl restart open5gs-pcrfd`, then `sudo ss -tan | grep :3871` must show one ESTAB.
2. voice VM: re-add the MTU route (command above).
3. Toggle airplane mode on every phone, then check registrations.

If open5gs-pcrfd restarts, every phone must re-attach.

## Commands that work on this stack

- P-CSCF registrations: `docker exec pcscf kamcmd ulpcscf.status` (`ul.dump` is empty here).
- S-CSCF registration for a number: `docker exec scscf kamcmd ulscscf.showimpu tel:2342064730NNN`. The iPhone's contact has no user part.
- IPsec entries: `docker exec pcscf ip xfrm state`
- Rx peer: on core-cp, `sudo ss -tan | grep :3871`
- Call timing: `docker logs -t pcscf`, filtered for `REQUEST: INVITE sip:` and `REPLY:` lines for the phone's address.
- `cdp.list_peers` does not exist on this build.

## Open items

1. MTU route into the pcscf container startup.
2. fr_timer 10000 into this repository's copy of the P-CSCF config (PR #224 captures the stack).
3. UNIWA SIM swap test.
4. Phones change IMS address and sometimes leave stale entries before re-registering. Unexplained.
5. Alerts: Rx peer not ESTAB on 3871; eNB down.
6. IPsec entry clean-up.
7. Remove the backup files left in ~/docker_open5gs/pcscf on the voice VM once this repository matches the live configuration.
