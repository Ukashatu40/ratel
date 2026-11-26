# SMS to customers: welcome and call summaries

Decided by the project lead on 2026-11-25. The app sends two kinds of SMS to customers, from the
short number 555 (647 until 2026-11-25; changed before launch, so nothing announced 647):

| Kind | When | Text |
| ---- | ---- | ---- |
| `welcome` | once per line, after its activation in RatelDesk | `Welcome to Ratelplus! Your number is 0XXXXXXXXXX. Text MENU to 555 for balance, bundles and top-up.` |
| `call` | after each call that cost something | `Last call to 08031234567: 2m 15s, cost N22.50. Balance N477.50. Text MENU to 555.` |

When the wallet could not cover the whole call, the summary says so and how to top up:
`Last call to 08031234567: 2m 15s, cost N22.50, N7.50 unpaid. Balance N0.00. Text BUY 500 to 555 to top up.`

Every text fits one SMS of plain characters (160, ASCII). Naira is written N: the naira sign is not
in the GSM 7-bit alphabet and would make phones count 70 characters per SMS. A "service message"
(a pop-up that is not stored, network USSD or class 0 flash SMS) is not used: the iPhone and the
desk phone do not support USSD over IMS, the SMS centre does not set class 0, and iPhones mostly
do not show it.

## How it works

1. What an SMS reports queues it, in the same transaction, in `customer_sms`:
   - activation (bss_lines, `services/activation.py`): the welcome, key `welcome:<line>`;
   - call charging (bss_money, `services/call_charging.py`): the summary, key `call:<call record>`,
     with the balance after the charge.
   The key is unique, so a replayed activation or a call handled twice queues nothing more. An SMS
   problem can never fail what it reports. The text is final when queued.
2. The voice VM asks bss-app what is due (`GET /v1/pay/customer-sms`): unsent SMS of lines in
   service (active, out of data, expired), oldest first.
3. It sends one only once the number is registered on the IMS, because the SMS centre gives up on
   a phone it cannot reach after about a minute (6 retries). Sent from 555, through the same SMS
   centre entry point as the 555 answers.
4. It then marks it sent (`POST /v1/pay/customer-sms/{sms_id}/sent`). A repeat changes nothing.

RatelBSS does not talk to the network: the voice VM pulls the queue, as it does for 555 and USSD.
Both paths are voice VM only, through the reverse proxy, which adds the payments key
(`deploy/bss-app/nginx`, `add-selfcare-paths.py`).

Phones show 555 as it is, not as +555: the SMS centre sends a short number with the address type
"unknown" (0x81) instead of "international" (0x91), which made 647 show as +64 7
(network/voice/ussd, `apply-smsc-shortcode.py`).

## Timing

Calls are charged by their own job every minute (`calls_cli`, `ratel-calls.timer`), and the voice
VM checks the queue every minute, so a call summary arrives one to two minutes after the call. Not
during or right at the end of the call: that needs online charging in the IMS core, not built.
No call summary is sent while call charging is off (`CALL_CHARGING_FROM` unset).

## Rules

- One welcome per line, ever. Lines activated before this was deployed get none (no backfill).
- One summary per charged call. Calls that cost nothing (unanswered, before charging started, from
  another network) get none.
- A line not in service (suspended, terminated) is not sent anything while it is not.
- Marked sent means handed to the SMS centre while the number was registered. Delivery to the phone
  is not reported back by this SMS centre.
- These SMS cost the customer nothing. Texts customers send themselves are charged from airtime
  (2 naira to another Ratelplus line, free to 555, not sent to other networks): docs/catalogue.md,
  ADR 0013.
