# Draft issue for github.com/open5gs/open5gs

Title: [HSS] MSISDN identities stay linked to an old IMPI when the same subscriber registers with another IMPI

## Summary

`hss_cx_associate_identity()` only adds a Public Identity if no IMPI has it yet
(`impu_find_by_id()` searches all IMPIs). When the same subscriber registers with a second IMPI,
the MSISDN identities (`sip:<msisdn>@<domain>`, `tel:<msisdn>`) stay linked to the first IMPI. The
profile sent for the second registration contains only the IMSI-based identity, so the subscriber
cannot be reached by number and its originating requests are refused. This lasts until the HSS
restarts.

## How we hit it

Same USIM, two handsets that derive the home domain with different MNC lengths:

1. Android registers as `<imsi>@ims.mnc002.mcc621.3gppnetwork.org`. MSISDN identities are linked to
   this IMPI.
2. The USIM moves to an iPhone, which registers as `<imsi>@ims.mnc000.mcc621.3gppnetwork.org`.
3. SAR/SAA for the new IMPI returns a User-Data with one Public Identity,
   `sip:<imsi>@ims.mnc000...`. The S-CSCF shows only that identity. LIR for `tel:<msisdn>` does not
   lead to the new registration.

Seen on v2.8.0. The code is unchanged on main after 57d1d5b0 and dc9c0559 (16 Nov 2026).

## Proposed fix

In `hss_cx_associate_identity()`, when the identity exists but belongs to another IMPI, move it to
the IMPI that is registering and clear its stored server name (the old S-CSCF), so lookups fall
back to the new IMPI's server name:

```c
} else if (impu->impi != impi) {
    ogs_warn("Cx: move Public-Identity[%s] from IMPI[%s] to IMPI[%s]",
            impu->id, impu->impi->id, impi->id);
    ogs_list_remove(&impu->impi->impu_list, impu);
    impu->impi = impi;
    ogs_list_add(&impi->impu_list, impu);
    if (impu->server_name) {
        ogs_free(impu->server_name);
        impu->server_name = NULL;
    }
}
```

We run this on 2.8.0 together with 100ee681 (#4633) and a backport of 57d1d5b0. Happy to open a PR against main with a
test in `tests/volte`.
