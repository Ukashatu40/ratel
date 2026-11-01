// The page's logic, run without a browser: node --test web/pay/tests
// The page is one file with no build step, so the test reads its <script>, runs it in an empty
// context (no document, so only the pure logic is set up) and drives it with a fake network.
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { webcrypto } from "node:crypto";
import { test } from "node:test";
import vm from "node:vm";

const html = readFileSync(new URL("../index.html", import.meta.url), "utf8");
const script = /<script>([\s\S]*?)<\/script>/.exec(html)[1];
const context = { crypto: webcrypto };
vm.createContext(context);
vm.runInContext(script, context);
const L = context.RatelPayLogic;

// A fake network: answers from a queue and records what was sent. The synthetic numbers below
// are made up (docs/SECURITY_AND_PRIVACY.md): no real number, card or PIN.
function network(...answers) {
  const sent = [];
  const post = (path, body, key) => {
    sent.push({ path, body, key });
    const next = answers.length > 1 ? answers.shift() : answers[0];
    return Promise.resolve(next);
  };
  return { post, sent };
}
const PHONE = "0800 000 0000";
const CARD = "12345678901234567890";
const PIN = "12345678901234";
const fields = { phone: PHONE, card: CARD, pin: PIN, amount: "1000" };
const fresh = () => ({ sig: null, key: null });
// Objects made inside the page's context have another prototype; compare their content.
const plain = (value) => JSON.parse(JSON.stringify(value));

test("a typed phone number becomes the stored form, or is refused", () => {
  assert.equal(L.toMsisdn("0800 000 0000"), "2348000000000");
  assert.equal(L.toMsisdn("+234 800-000-0000"), "2348000000000");
  assert.equal(L.toMsisdn("2348000000000"), "2348000000000");
  assert.equal(L.toMsisdn("800 000 0000"), null);
  assert.equal(L.toMsisdn("080000"), null);
  assert.equal(L.toMsisdn("abc"), null);
  assert.equal(L.toMsisdn(""), null);
  assert.equal(L.toMsisdn(undefined), null);
});

test("card number and PIN must have exactly the right digits, spaces allowed", () => {
  assert.equal(L.cardNumber("1234 5678 9012 3456 7890"), CARD);
  assert.equal(L.cardNumber("1234567890123456789"), null);
  assert.equal(L.cardNumber("1234567890123456789a"), null);
  assert.equal(L.pin("1234 5678 9012 34"), PIN);
  assert.equal(L.pin("1234567890123"), null);
});

test("naira become whole kobo with integers only", () => {
  assert.equal(L.nairaToKobo("1000"), 100000);
  assert.equal(L.nairaToKobo("1,500"), 150000);
  assert.equal(L.nairaToKobo("₦2,000.5"), 200050);
  assert.equal(L.nairaToKobo("0.01"), 1);
  assert.equal(L.nairaToKobo("10.10"), 1010);
  assert.equal(L.nairaToKobo("0"), null);
  assert.equal(L.nairaToKobo("0.00"), null);
  assert.equal(L.nairaToKobo("-5"), null);
  assert.equal(L.nairaToKobo("1.234"), null);
  assert.equal(L.nairaToKobo("1e3"), null);
  assert.equal(L.nairaToKobo(""), null);
  assert.ok(Number.isInteger(L.nairaToKobo("123456789.99")));
});

test("kobo are shown as naira with separators and two decimals", () => {
  assert.equal(L.formatNaira(100000), "₦1,000.00");
  assert.equal(L.formatNaira(5), "₦0.05");
  assert.equal(L.formatNaira(123456789), "₦1,234,567.89");
});

test("a redemption sends the stored phone form, the card and the PIN, with a key", async () => {
  const { post, sent } = network({ status: 200, body: { amount_kobo: 50000, balance_kobo: 125000 } });
  const r = await L.redeem(fields, post, fresh());
  assert.equal(r.ok, true);
  assert.equal(r.clear, true);
  assert.match(r.message, /₦500\.00 added/);
  assert.match(r.message, /₦1,250\.00/);
  assert.equal(sent.length, 1);
  assert.equal(sent[0].path, "/v1/pay/vouchers/redeem");
  assert.deepEqual(plain(sent[0].body), { msisdn: "2348000000000", card_number: CARD, pin: PIN });
  assert.match(sent[0].key, /^[0-9a-f]{32}$/);
});

test("a bad input never reaches the network", async () => {
  const { post, sent } = network({ status: 200, body: {} });
  for (const [change, field] of [
    [{ phone: "123" }, "phone"],
    [{ card: "1" }, "card"],
    [{ pin: "1" }, "pin"],
  ]) {
    const r = await L.redeem({ ...fields, ...change }, post, fresh());
    assert.equal(r.ok, false);
    assert.equal(r.field, field);
  }
  assert.equal(sent.length, 0);
});

test("every refusal of a card is the same words, and says nothing about the card or the line", async () => {
  const seen = new Set();
  for (const status of [400]) {
    const { post } = network({ status, body: { error: { code: "voucher_refused", message: "x" } } });
    seen.add((await L.redeem(fields, post, fresh())).message);
  }
  assert.equal(seen.size, 1);
  const [message] = seen;
  assert.doesNotMatch(message, /pin|already|expired|locked|unknown|phone number|wrong|not found/i);
});

test("the other answers are told apart only as far as the person needs", async () => {
  const cases = [
    [422, L.MSG.malformed],
    [429, L.MSG.limited],
    [500, L.MSG.trouble],
    [503, L.MSG.trouble],
    [401, L.MSG.trouble],
    [0, L.MSG.trouble],
  ];
  for (const [status, expected] of cases) {
    const { post } = network({ status, body: null });
    const r = await L.redeem(fields, post, fresh());
    assert.equal(r.ok, false, String(status));
    assert.equal(r.message, expected, String(status));
    assert.notEqual(r.clear, true);
  }
});

test("a success without both amounts is not shown as a success", async () => {
  const { post } = network({ status: 200, body: { amount_kobo: 50000 } });
  assert.equal((await L.redeem(fields, post, fresh())).ok, false);
});

test("a retry after a lost reply sends the same key, and a new attempt a new one", async () => {
  const attempt = fresh();
  const lost = network({ status: 0, body: null });
  await L.redeem(fields, lost.post, attempt);
  await L.redeem(fields, lost.post, attempt);
  assert.equal(lost.sent[0].key, lost.sent[1].key);

  const changed = network({ status: 0, body: null });
  await L.redeem({ ...fields, pin: "99999999999999" }, changed.post, attempt);
  assert.notEqual(changed.sent[0].key, lost.sent[0].key);

  const answered = network({ status: 400, body: null }, { status: 400, body: null });
  const again = fresh();
  await L.redeem(fields, answered.post, again);
  await L.redeem(fields, answered.post, again);
  assert.notEqual(answered.sent[0].key, answered.sent[1].key); // an answer we understood ends the attempt
});

test("starting a payment sends whole kobo and returns the gateway address", async () => {
  const body = { payment_id: "abcdefghijklmnop12345678", status: "pending", amount_kobo: 100000, checkout_url: "https://checkout.example/pay/abc" };
  const { post, sent } = network({ status: 200, body });
  const r = await L.startPayment(fields, post, fresh());
  assert.equal(r.ok, true);
  assert.equal(r.checkoutUrl, body.checkout_url);
  assert.equal(r.paymentId, body.payment_id);
  assert.equal(sent[0].path, "/v1/pay/payments");
  assert.deepEqual(plain(sent[0].body), { msisdn: "2348000000000", amount_kobo: 100000 });
  assert.ok(Number.isInteger(sent[0].body.amount_kobo));
  assert.ok(sent[0].key.length >= 1 && sent[0].key.length <= 120);
});

test("the page only follows an https gateway address", async () => {
  for (const url of ["http://checkout.example/x", "javascript:alert(1)", "//checkout.example/x", ""]) {
    const { post } = network({ status: 200, body: { payment_id: "abcdefghijklmnop12345678", status: "pending", amount_kobo: 1, checkout_url: url } });
    assert.equal((await L.startPayment(fields, post, fresh())).ok, false, url);
  }
});

test("payment refusals: one wording for a refused payment, a clear one when payments are off", async () => {
  const refused = new Set();
  for (const status of [400, 422]) {
    refused.add((await L.startPayment(fields, network({ status, body: null }).post, fresh())).message);
  }
  assert.equal(refused.size, 1);
  assert.equal((await L.startPayment(fields, network({ status: 503, body: null }).post, fresh())).message, L.MSG.unavailable);
  assert.equal((await L.startPayment({ ...fields, amount: "0" }, network({ status: 200, body: {} }).post, fresh())).field, "amount");
});

test("a payment's status is told in plain words and never by trusting the page", async () => {
  const id = "abcdefghijklmnop12345678";
  const get = (status, body) => () => Promise.resolve({ status, body });
  assert.equal((await L.checkPayment(id, get(200, { payment_id: id, status: "pending", amount_kobo: 1 }))).state, "pending");
  const ok = await L.checkPayment(id, get(200, { payment_id: id, status: "succeeded", amount_kobo: 250000 }));
  assert.equal(ok.state, "succeeded");
  assert.match(ok.message, /₦2,500\.00 added/);
  assert.equal((await L.checkPayment(id, get(200, { payment_id: id, status: "failed", amount_kobo: 1 }))).state, "failed");
  assert.equal((await L.checkPayment(id, get(404, null))).state, "failed");
  assert.equal((await L.checkPayment(id, get(500, null))).state, "unknown");
  assert.equal((await L.checkPayment("../etc", get(200, {}))).state, "unknown"); // never put it in a path
});

test("no message names a card, a PIN, a phone number or a person", () => {
  for (const text of Object.values(L.MSG)) {
    assert.doesNotMatch(text, /\d{6,}/);
  }
});
