# Patched HSS: a line keeps its number when its SIM moves to another handset

Open5GS 2.8.0 with two patches, installed with its own libraries under `/opt/open5gs-hss-ratel`
and started through the systemd drop-in `zz-ratel-hss.conf`.

## What core-cp runs, and why this is a complete build

core-cp does not run the packaged HSS (`open5gs-hss 2.8.0~jammy5`). Since 11 Oct 2026 the drop-in
`/etc/systemd/system/open5gs-hssd.service.d/fix4633.conf` starts a separate build from
`/opt/open5gs-hss`, with its own libraries (`LD_LIBRARY_PATH`). That build is 2.8.0 plus the
upstream fix for issue #4633 (commit 100ee681, "Stop IMSI extraction at IMPI realm separator").
Without that fix the HSS reads the digits in `ims.mnc002.mcc621...` as part of the IMSI and
rejects IMS registrations. An install archive of it is in `/home/ratel/open5gs-hss-2.8.0-fix4633.tgz`
on core-cp. No source or build notes were found. Its strings match 2.8.0 plus 100ee681 only: none
of the messages added upstream in July and August are in it, and it writes `tel:<number>`.

This build reproduces it (the PPA's 2.8.0 source plus 100ee681) and adds our patch. It installs
its own libraries so it never runs against another build's. The packaged HSS, `/opt/open5gs-hss`
and `fix4633.conf` are not touched. `zz-ratel-hss.conf` sorts after `fix4633.conf` and overrides
its start line and library path.

## The fault (found 23 Nov 2026)

SIM 454 worked in an Android. Moved to an iPhone, it registered for voice, but every call to or
from it failed at once. The S-CSCF held its registration with one identity only, the SIM identity
`sip:621002064730454@ims.mnc000...`. The number identities `tel:2342064730454` and
`sip:2342064730454@ims.mnc002...` were missing, so nothing could reach the line by its number and
its own calls were refused.

Cause, in the HSS (`src/hss/hss-context.c`, `hss_cx_associate_identity`):

1. The HSS links a line's number identities to the private identity (IMPI) that registers.
2. The Android registered as `621002064730454@ims.mnc002...`. The HSS linked the number
   identities to that IMPI.
3. The iPhone builds the home domain from a two digit MNC and registered the same SIM as
   `621002064730454@ims.mnc000...`, a second IMPI.
4. The HSS looks an identity up across all IMPIs and only adds it if nobody has it. The number
   identities stayed with the Android's IMPI. The iPhone's profile had the SIM identity only.
5. This lasts until the HSS restarts. The same code is still in Open5GS main.

A second, related fault was fixed upstream on 16 Nov 2026 (commit 57d1d5b0, not in any release
yet): after an HSS restart, if the S-CSCF already has a profile, the HSS skips linking the number
identities, and calls to the line fail until its profile is fetched again.

Any customer who moves a SIM between an iPhone and an Android would hit the first fault. Any HSS
restart would hit the second.

## The patches

`0000-upstream-100ee681-hss-cx-stop-imsi-extraction-at-realm.patch`: the #4633 fix the running
build already has, one line, taken unchanged from upstream.

`0001-hss-move-msisdn-identities-to-registering-impi.patch`, about 60 lines in three files:

- `hss_cx_associate_identity`: if an identity belongs to another IMPI, move it to the IMPI now
  registering and forget the old S-CSCF name, so lookups use the new registration. Logged as a
  warning, `Cx: move Public-Identity[...] from IMPI[...] to IMPI[...]`.
- Backport of upstream 57d1d5b0: link the number identities on every registration and
  re-registration, also when the S-CSCF already has the profile.

Not taken from upstream, on purpose:

- dc9c0559 (SIP number identity in the IMPI's domain). Our I-CSCF and S-CSCF look numbers up as
  `sip:<number>@ims.mnc002...`. With dc9c0559 an iPhone's number identity would be
  `@ims.mnc000...` and lookups for it would fail.
- 07250b0b (`tel:+<number>`). Our routing uses `tel:<number>` without the plus. Taking it means
  changing the number handling in the CSCFs at the same time (the known plus sign fault).

## Build (any Ubuntu 22.04 host with internet)

```
cd deploy/core-cp/hss && ./build-hssd.sh
```

Downloads the PPA's `open5gs 2.8.0~jammy5` source, checks its SHA-256 against the PPA index,
applies both patches, builds, installs under `/opt/open5gs-hss-ratel` in a staging folder and
writes `out/open5gs-hss-ratel.tgz` and its `.sha256`. It stops if our patch is not in the binary.
The first build on 23 Nov ran on the voice VM, which now has the build dependencies installed.

## Deploy (core-cp)

Copy `deploy-hssd.sh`, `out/open5gs-hss-ratel.tgz` and `out/open5gs-hss-ratel.tgz.sha256` into one
folder on core-cp, then:

```
sudo ./deploy-hssd.sh            # shows what would change, changes nothing
sudo ./deploy-hssd.sh --apply    # installs, restarts open5gs-hssd, checks the Diameter peers
```

The dry run shows the current drop-ins, checks the archive, confirms our patch is in it, compares
the `tel:` identity format with the running build and lists the freeDiameter extensions the HSS
loads. Then toggle airplane mode on every phone, so each one registers through the patched HSS.

Restarting the HSS takes seconds. Calls and data sessions in progress continue. The script checks
that the I-CSCF and S-CSCF have reconnected and shows which binary and libraries are running.

Rollback: `sudo ./deploy-hssd.sh --rollback`. It removes `zz-ratel-hss.conf`, which puts the
`fix4633.conf` build back in service.

## Test after deploying

1. Every phone registered with its number:
   ```
   ssh ratel-voice 'for N in 433 452 454 240; do printf "%s  " tel:2342064730$N; docker exec scscf kamcmd ulscscf.showimpu tel:2342064730$N 2>&1 | grep -oE "sip:[^ ]*10\.46\.[0-9]+\.[0-9]+:[0-9]+" | head -1; echo; done'
   ```
2. Move SIM 454 from the iPhone to an Android. Airplane toggle. Call it, and call out from it.
3. Move it back to the iPhone. Airplane toggle. Call it, and call out from it.
4. After each move, the HSS log shows the move:
   `sudo grep "move Public-Identity" /var/log/open5gs/hss.log | tail`

Before the patch, step 3 failed exactly as above.

## Interim procedure on the unpatched HSS

If a line has lost its number identities and the patch is not deployed:

1. core-cp: `sudo systemctl restart open5gs-hssd`, then check the I-CSCF and S-CSCF reconnect.
2. voice VM: `docker restart scscf` (registrations are in memory only, `db_mode 0`), then wait
   for the HSS to reconnect to the S-CSCF.
3. Airplane toggle on every phone.

Done on 23 Nov 2026 between 09:50 and 09:56 local. It fixed line 454.

## The underlying question

One SIM registers under two home domains because handsets read its MNC length differently: the
iPhone uses `mnc000`, the Androids `mnc002`, and the IMS core is configured as `mnc002`. The SIM
order of 29 Jul 2024 does not specify the MNC length on the card. Which MNC is the licensed one,
and whether future SIM batches should carry it explicitly, is open. Until it is settled, the
network has to accept both, which is what this patch makes safe.
