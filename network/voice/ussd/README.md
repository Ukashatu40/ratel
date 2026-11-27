# Self-care: USSD `*123#` and SMS short number 555

One small service, the container `ussd` at 172.22.0.40 on the IMS network `ratel_ims` on the voice
VM, offers the same self-care functions two ways. Calls never pass through it: it only answers
the P-CSCF's and the SMS centre's prepaid questions (see "Prepaid checks" below).

| Channel | Works on | How it reaches the service |
| ---- | ---- | ---- |
| SMS to **555** | every phone that sends SMS over IMS (tested: iPhone, desk phone) | the SMSC hands texts to 555 to the service, answers come back from 555 |
| USSD `*123#` | Android phones whose line is EPS-only (see below); not iPhone, not the desk phone | the S-CSCF sends `*` and `#` dial strings to the service |

## SMS 555

Text one of these to 555 (any case):

```
MENU                       the list below
BAL                        airtime, and the data left with its end date
BUY 500                    a Paystack link to buy N500 airtime (within the card limits set in RatelDesk)
BUNDLES                    the bundles on sale on SMS, numbered, cheapest first
BUNDLE 2                   buy bundle number 2 from the list, paid from airtime
CARD <card number> <PIN>   recharge with a card (20 and 14 digits, spaces allowed)
```

Bundles, prices, airtime amounts and limits come from the catalogue an admin keeps in RatelDesk
(Plans & Bundles), through ratel-app's self-care API (`/v1/pay/airtime`, `/v1/pay/bundles?channel=`,
`/v1/pay/lines/{msisdn}/balance` and `/purchases`). A bundle appears on SMS only when it lists the
SMS channel, and on USSD only when it lists USSD.

Every text is a full command and gets one answer of at most 160 characters. Card numbers and PINs
are never logged, only the command word.

The SMSC change (`apply-smsc-shortcode.py`) does three things in `kamailio_smsc.cfg`, after the
`smsc` container's own Kamailio has checked the new file (`kamailio -c`):

1. In `route[SMS_FROM_3GPP]`, a text to 555 is passed to `http://172.22.0.40:8647/sms` with the
   sender's network-asserted number and the text hex encoded, instead of being queued.
2. The SMSC's HTTP entry point (`event_route[xhttp:request]`), which the service uses to send its
   answers and the customer SMS as sender 555, accepts requests from 172.22.0.40 only. It accepted
   anyone before, and nothing else in Ratelplus uses it. It also sets the coding the queue needs.
3. In `route[SEND_SMS]`, an SMS from a short number goes out with the address type "unknown" (0x81)
   instead of "international" (0x91), so phones show 555 and not +555 (`$tpdu(origen_flags)`, the
   sender address the phone shows; `$rpdata` has no such setting). The short number was 647
   until 25 Nov 2026, and phones showed it as +64 7.

On a config that has the 647 version (24 Nov), the script replaces it. Port 8647 is only the
service's internal port; it did not change with the number.

The service takes requests on port 8647 from the SMSC (172.22.0.33) only.

## USSD `*123#`

```
*123#
1. My balance
2. Buy airtime        (the amounts set in RatelDesk: answers with a Paystack payment link)
3. Buy a bundle       (numbered list of bundles sold on USSD; choose one to buy it from airtime)
4. Recharge card      (card number, a star, PIN)
*123*CARD*PIN#        recharge in one go
```

### Which phones (tested 24 Nov 2026)

- **Desk phone (ZXIC):** no USSD over IMS client. It sends `*123#` as an ordinary voice call.
- **iPhone:** refuses locally, even with an EPS-only attach. iOS sends USSD over IMS only when
  Apple's carrier bundle for the network enables it.
- **Android:** sends USSD over IMS only when it sees no circuit-switched service
  (`USSD_OVER_CS_PREFERRED`, the Android default). With `network_access_mode` 0 and the MSC on
  core-cp, phones are combined attached, believe CS is available and try CS fallback, which fails
  without 2G/3G. With `network_access_mode` 2 on the line, the MME answers EPS-only. Still to be
  confirmed on a real Android.

### How a session runs

1. The phone sends `INVITE tel:*123#` with a multipart body: an SDP with port 0 and
   `application/vnd.3gpp.ussd+xml` holding the dial string.
2. The S-CSCF rule (`scscf-ussd-rule.cfg`, at the top of `route[FINAL_ORIG]`) sends it here.
3. The service answers 200 OK with an SDP answer with port 0 and `Recv-Info: g.3gpp.ussd`.
4. Menus go to the phone as INFO (`Info-Package: g.3gpp.ussd`), the user's choices come back as
   INFO, and the final answer ends the session as a BYE carrying the text.

UDP towards the S-CSCF, with the SIP retransmission timers. Standard library only.

## Files

| File | What |
| ---- | ---- |
| `ussd_as.py` | the service (USSD and SMS 555) |
| `test_ussd.py` | plays a phone, the SMSC and a fake payments API against it: `python3 -I test_ussd.py` |
| `run-ussd.sh` | starts the container (`--stop` removes it) and checks both ports |
| `scscf-ussd-rule.cfg` | the S-CSCF block, for `route[FINAL_ORIG]` in `kamailio_scscf.cfg` |
| `apply-smsc-shortcode.py` | adds 555 to `kamailio_smsc.cfg`, or replaces the 647 version (dry run by default, `--apply` writes with a backup) |
| `test_apply_smsc.py` | its tests: `python3 -I test_apply_smsc.py` |
| `customer_sms.py` | sends the queued SMS to customers (welcome, call summaries) once the number is registered (one pass) |
| `test_customer_sms.py` | its tests, with a fake bss-app and a fake `docker`: `python3 -I test_customer_sms.py` |
| `install-sms-timer.sh` | installs the systemd timer that runs it every minute (`--stop` removes it) |

## SMS to customers: welcome and call summaries

bss-app queues two kinds of SMS to customers (docs/customer-sms.md), and this VM sends them from 555:

```
Welcome to Ratelplus! Your number is 0XXXXXXXXXX. Text MENU to 555 for balance, bundles and top-up.
Last call to 08031234567: 2m 15s, cost N22.50. Balance N477.50. Text MENU to 555.
```

`customer_sms.py` runs every minute (systemd timer `ratel-customer-sms.timer`, installed by
`./install-sms-timer.sh`) and, for each SMS due:

1. asks the S-CSCF whether the number is registered (`kamcmd ulscscf.showimpu tel:<number>`:
   `state: registered` with a contact). Not yet: it waits for a later pass, because the SMSC drops
   an SMS it cannot deliver after about a minute;
2. sends it from 555 through this container (`ussd_as.py --send-sms`, the address the SMSC takes);
3. tells bss-app it was sent. What was handed to the SMSC is kept in `customer-sms-sent.txt` first,
   so a failure to tell bss-app never sends a second SMS.

Logs: `journalctl -u ratel-customer-sms.service`. Off: `./install-sms-timer.sh --stop`.

## Payments

Both channels call ratel-app's payments API (`/v1/pay`, `Authorization: Bearer <PAY_API_KEY>`).
Put `RATEL_PAY_URL=<base URL>` in `ussd.env` and the key alone in `pay.key` (mode 600) next to
`run-ussd.sh`, then run it again. Neither file is committed. Without them every option answers
"not available yet".

Balance and buying a bundle by number need ratel-app with the catalogue release
(`feat/catalogue-and-voice-charging`) and bss-app's nginx rule for the voice VM
(`deploy/bss-app/nginx/add-selfcare-paths.py`).

## Prepaid checks (ADR 0013)

On the same HTTP port (8647) the service relays the prepaid questions to bss-app and answers in
plain text, so the Kamailio configs need no JSON or TLS (network/voice/prepaid):

| Path | Asked by | Answer |
| ---- | ---- | ---- |
| `/call/authorize?call_id=&caller=&dialled=` | the P-CSCF (`CALL_ALLOWED`, 172.22.0.21), at call set-up | `200 <max seconds>` (0: no limit) or `402 <reason>`; bss-app silent for 1.5 s: `200 120` |
| `/call/end?call_id=&seconds=` | the P-CSCF, at hang-up or a failed call | `200 ok` at once; bss-app is told in the background |
| `/sms/charge?id=&from=&to=` | the SMS centre (`SMS_ALLOWED`, 172.22.0.33), before queueing a text | `200 <reason>` to send, or `402 <reason>` and an SMS from 555 telling the sender why; bss-app silent: `200 unchecked` |

Logs show the last four digits only: `docker logs ussd 2>&1 | grep -E "call:|sms:" | tail`.

## Switching it off

- SMS 555: copy the `kamailio_smsc.cfg.bak-short-*` backup back and `docker restart smsc`.
- USSD: remove the block from `kamailio_scscf.cfg` and restart the `scscf` container (every phone
  then re-registers: airplane toggle).
- Both: `./run-ussd.sh --stop`. With the prepaid change installed, every call is then limited to
  two minutes and texts go unchecked, so roll that back first (network/voice/prepaid).
