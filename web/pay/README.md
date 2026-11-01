# RatelPay

Public customer top-up page (M-21). **Built: a prepaid card can be redeemed from it. Paying by card is built
and switched off.**

- One file, `index.html`, served by the reverse proxy at `/pay` (the only thing nginx serves from disk). The
  release carries it (`web/pay/index.html` in `ratel-app-<commit>.tar.gz`).
- Shows nothing personal about a line's owner (TOP-2). It asks for the line's phone number, the card number and
  the PIN, and shows an amount and the new balance. Every refusal of a card is the same sentence.
- Loads in under 3 seconds on 3G (TOP-3): no framework, no second request. See the budget below.
- It and the payment webhook are the only public paths. Rate limits and the key the proxy adds are in
  `deploy/bss-app/nginx/ratel-app.conf.example`; the page sends no key.
- Show West Africa Time here only: the page shows no time today.

## How it is built (docs/adr/0008, option 1 of the open point below, decided)

Everything is inside `index.html`: a style block, the form, and one script in two parts. The first part is pure
logic (number forms, kobo, the calls and the words for each answer); it is exposed as `RatelPayLogic` so it can
be tested without a browser. The second part is the page, and starts only when there is a page.

```
index.html               the page (CSS, form and script inline)
tests/logic.test.mjs     the logic, run with: node --test web/pay/tests/logic.test.mjs
```

The tests are also run by `tests/tooling/test_pay_page.py`, which holds the weight budget, "nothing else is
loaded", "only the public pay paths of the contract are called" and "nothing is stored but a payment id".

What the page does:

- A phone number typed as `0800 000 0000`, `+234 800 000 0000` or `2348000000000` is sent as `2348000000000`.
  TODO(PRD): confirm how a typed number becomes the stored form.
- It sends `POST /v1/pay/vouchers/redeem` with a fresh `Idempotency-Key`. A retry after a lost reply sends the same
  key; a changed field or any answer it understood starts a new one. The card and PIN are cleared after a success
  and never stored, logged or put in a URL.
- 400 is one sentence for every reason; 422 asks to check the digits; 429 asks to wait; anything else says
  something went wrong and can be retried.
- Paying by card (`CARD_PAYMENTS` in the script, **false**): the amount is read as naira and sent as whole kobo,
  the customer is sent to the gateway address the API returns (only if it is `https`), and on coming back the page
  follows `GET /v1/pay/payments/{id}` until it succeeds or fails. Turn it on only when Paystack's sandbox is set up
  on bss-app and `PAYMENT_CALLBACK_URL` is this page's address.

TODO(PRD): the words on the page and what it says after a top-up; the lowest and highest payment (the API refuses
what is out of range with one sentence); bundles are not shown, because the API has no way to buy one yet.

## Run it on your machine

The page calls `/v1/pay/...` on its own address, so it needs something that answers there. With the API's mock
(`make mock`) or the real app behind a proxy, serve `index.html` from the same address. Opening the file straight
from disk shows the page but every call fails.

## Page-weight budget

Target (PRD TOP-3): the first load of the page completes in under 3 seconds on 3G.

### How it is measured

- Chrome DevTools, Network tab, throttling preset "3G" (checked in Chrome 155), "Disable cache" ticked, full reload.
- Size is the "transferred" figure at the bottom of the Network tab, not "resources".
- Time is the "Load" figure at the bottom of the Network tab.
- The voucher redeem call is not part of the first load. It happens after the customer submits the form.

### Budget for the first load

| Measure | Limit |
| ------- | ----- |
| Requests | 1 (`index.html` only) |
| Transferred size | 30 KB or less |
| Load time on "3G" | under 3 seconds |

This rules out web fonts, image files (small inline SVG is fine), third-party scripts, separate CSS or JS files, and a separate favicon request (use `<link rel="icon" href="data:,">`).

### Why one request

The "3G" preset adds about 2 seconds to every request, and files linked from `index.html` are only requested after it arrives. A second round of requests puts the page over 3 seconds whatever their size. One 30 KB response takes about 2.6 seconds: about 2 seconds of delay plus about 0.6 seconds of transfer at roughly 50 KB per second.

### Decided: option 1

The page keeps its CSS and script inside `index.html` (one request). Separate files cannot meet the budget on the
"3G" preset.

### Measured

| Date | What | Result |
| ---- | ---- | ------ |
| 2026-11-01 | `index.html` size | 13,297 bytes; 4,697 bytes compressed (gzip -9). Limit 30 KB |
| 2026-11-01 | Requests for the first load | 1 (checked by `tests/tooling/test_pay_page.py`: no script, stylesheet, image or font file, no other address) |
| | Load time on "3G" in Chrome DevTools | **Not measured yet.** TODO: measure from the proxy on bss-app and record it here |

Measured results are recorded in each PR that changes the page.
