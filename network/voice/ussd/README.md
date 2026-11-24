# Self-care: USSD `*123#` and SMS short number 647

One small service, the container `ussd` at 172.22.0.40 on the IMS network `ratel_ims` on the voice
VM, offers the same self-care functions two ways. Calls never pass through it.

| Channel | Works on | How it reaches the service |
| ---- | ---- | ---- |
| SMS to **647** | every phone that sends SMS over IMS (tested: iPhone, desk phone) | the SMSC hands texts to 647 to the service, answers come back from 647 |
| USSD `*123#` | Android phones whose line is EPS-only (see below); not iPhone, not the desk phone | the S-CSCF sends `*` and `#` dial strings to the service |

## SMS 647

Text one of these to 647 (any case):

```
MENU                       the list below
BAL                        your balance
BUY 500                    a Paystack link to buy N500 airtime (N100 to N50,000)
BUNDLES                    the bundles on sale
CARD <card number> <PIN>   recharge with a card (20 and 14 digits, spaces allowed)
```

Every text is a full command and gets one answer of at most 160 characters. Card numbers and PINs
are never logged, only the command word.

The SMSC change (`apply-smsc-647.py`) does two things in `kamailio_smsc.cfg`:

1. In `route[SMS_FROM_3GPP]`, a text to 647 is passed to `http://172.22.0.40:8647/sms` with the
   sender's network-asserted number and the text hex encoded, instead of being queued.
2. The SMSC's HTTP entry point (`event_route[xhttp:request]`), which the service uses to send its
   answers as sender 647, accepts requests from 172.22.0.40 only. It accepted anyone before, and
   nothing else in Ratelplus uses it. It also sets the coding the queue needs.

The service takes requests on port 8647 from the SMSC (172.22.0.33) only.

## USSD `*123#`

```
*123#
1. My balance
2. Buy airtime        (N100, N200, N500, N1000: answers with a Paystack payment link)
3. Buy a bundle       (lists the bundles on sale)
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
| `ussd_as.py` | the service (USSD and SMS 647) |
| `test_ussd.py` | plays a phone, the SMSC and a fake payments API against it: `python3 -I test_ussd.py` |
| `run-ussd.sh` | starts the container (`--stop` removes it) and checks both ports |
| `scscf-ussd-rule.cfg` | the S-CSCF block, for `route[FINAL_ORIG]` in `kamailio_scscf.cfg` |
| `apply-smsc-647.py` | adds 647 to `kamailio_smsc.cfg` (dry run by default, `--apply` writes with a backup) |

## Payments

Both channels call ratel-app's payments API (`/v1/pay`, `Authorization: Bearer <PAY_API_KEY>`).
Put `RATEL_PAY_URL=<base URL>` in `ussd.env` and the key alone in `pay.key` (mode 600) next to
`run-ussd.sh`, then run it again. Neither file is committed. Without them every option answers
"not available yet".

Balance (`GET /v1/pay/lines/{msisdn}/balance`) and buying a bundle by number are not in ratel-app
yet; they are step 3 of this work.

## Switching it off

- SMS 647: copy the `kamailio_smsc.cfg.bak-647-*` backup back and `docker restart smsc`.
- USSD: remove the block from `kamailio_scscf.cfg` and restart the `scscf` container (every phone
  then re-registers: airplane toggle).
- Both: `./run-ussd.sh --stop`.
