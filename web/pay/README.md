# RatelPay

Public customer top-up page. **Not started** (Week 5).

- A small page served by RatelBSS, public through a reverse proxy. The only part of the platform customers see.
- Shows nothing personal about a line's owner (TOP-2).
- Loads in under 3 seconds on 3G (TOP-3): no heavy framework bundle. Measure it.
- It and the payment webhook are the only public paths. Rate-limit both. Verify every webhook signature.
- Show West Africa Time here only.
