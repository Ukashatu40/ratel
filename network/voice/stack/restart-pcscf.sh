#!/usr/bin/env bash
# Restart the P-CSCF on the voice VM and check it came back right (docs: CHANGES-FROM-UPSTREAM.md).
# Run on the voice VM, from anywhere: ./restart-pcscf.sh
#
# 1. restarts the pcscf container and checks it stays up for 30 seconds (no restart loop);
# 2. checks the IMS route with the MTU lock is there (pcscf_init.sh adds it at every start);
# 3. prints how many phones are registered;
# 4. tells you what to do on core-cp: the PCRF must hold exactly one ESTAB connection to the
#    P-CSCF on port 3871. If it does not, restart it there (sudo systemctl restart open5gs-pcrfd);
#    every phone then re-attaches once (airplane toggle), because the PCRF forgets data sessions.
set -uo pipefail
MTU="${UE_IMS_PATH_MTU:-1400}"
POOL="${UE_IPV4_IMS:-10.46.0.0/16}"
fail() { echo "FAIL: $*" >&2; exit 1; }

docker restart pcscf >/dev/null || fail "docker restart pcscf"
before=$(docker inspect -f '{{.RestartCount}}' pcscf)
sleep 30
after=$(docker inspect -f '{{.RestartCount}}' pcscf)
[ "$(docker inspect -f '{{.State.Running}}' pcscf)" = true ] && [ "$before" = "$after" ] \
	|| fail "pcscf is not staying up (restarts $before -> $after): docker logs --tail 40 pcscf"
echo "ok   pcscf up and stable (restarts $before -> $after)"

route=$(docker exec pcscf ip route show "$POOL")
if echo "$route" | grep -q "mtu lock $MTU"; then
	echo "ok   IMS route: $route"
else
	fail "no '$POOL ... mtu lock $MTU' route in pcscf (got: '${route:-none}'); check pcscf_init.sh and UE_IMS_PATH_MTU"
fi

echo "ok   registered phones now: $(docker exec pcscf kamcmd ulpcscf.status 2>/dev/null | grep -c 'State: registered')"
cat <<'NEXT'

Now on core-cp:
  echo "ESTAB: $(sudo ss -tan | grep ':3871' | grep -c ESTAB)  CLOSE-WAIT: $(sudo ss -tan | grep ':3871' | grep -c CLOSE-WAIT)"
  ESTAB 1 and CLOSE-WAIT 0: done. Otherwise: sudo systemctl restart open5gs-pcrfd, check again,
  then toggle airplane mode once on every phone.
NEXT
