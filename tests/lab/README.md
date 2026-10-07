# Lab tests

Tests that need the lab core (core-cp, core-up). Mark them `@pytest.mark.lab`. They are excluded
from `make test` and from CI, and **must never be pointed at production**.

Required before "done" for anything that touches the network (see docs/TESTING_STRATEGY.md).
Record in the PR: date, what ran, what you saw. Credentials and addresses come from your local
environment, never from the repository. Use synthetic or lab-issued test SIMs only.
