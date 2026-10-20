# RatelPay

Public customer top-up page. **Not started** (Week 5).

- A small page served by RatelBSS, public through a reverse proxy. The only part of the platform customers see.
- Shows nothing personal about a line's owner (TOP-2).
- Loads in under 3 seconds on 3G (TOP-3): no heavy framework bundle. Measure it.
- It and the payment webhook are the only public paths. Rate-limit both. Verify every webhook signature.
- Show West Africa Time here only.

## Planned structure (docs/adr/0008, for the frontend lead to confirm)

```
index.html
css/                     one small stylesheet per concern
js/                      one module per concern (page logic, API calls, validation)
```

No build step and no framework. Write the page-weight budget (KB over 3G in under 3 seconds) in
this file before building, and measure against it.

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

### Open point for the frontend lead

The planned structure above uses separate `css/` and `js/` files, which cannot meet this budget on the "3G" preset. The options are:

1. Write the CSS and JS inside `index.html`, keeping it small and organised in clearly marked sections.
2. Keep separate files and measure against the "Slow 4G" preset instead, which is a weaker promise than TOP-3.

Measured results are recorded in each PR that changes the page.