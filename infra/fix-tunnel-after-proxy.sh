#!/usr/bin/env bash
# Repair the tunnel after the proxy (Mihomo) is turned off.
#
# Why this is needed: Mihomo answers DNS in fake-ip mode, handing out 198.18.x.x addresses that only
# its own TUN device can reach. When Mihomo stops, systemd-resolved still holds those answers until
# their TTL expires, and cloudflared keeps dialling a virtual address that no longer exists —
# `Failed to dial to edge ... ip=198.18.0.x` / `no free edge addresses left to resolve to`. The
# tunnel goes down and the phone gets a Cloudflare 530 (origin unreachable), which looks exactly like
# "turning the proxy off broke it".
#
# Measured 2026-10-02: through Mihomo the TLS handshake to api.semispeak.com took 3.82 s and landed on
# colo=SJC (because Mihomo's exit node is in the US); direct it is 0.92 s. The proxy is not required
# by anything here — not by the API, not by the tunnel.
#
# Run this after switching Mihomo off, or any time `https://api.semispeak.com/api/v1/health` fails.
set -euo pipefail

echo "1) flushing the resolver cache (drops leftover fake-ip answers)"
resolvectl flush-caches || echo "   (flush failed — continuing, the restart below may be enough)"

echo "2) restarting the tunnel so it resolves the edge again"
systemctl --user restart cloudflared-voxora.service

echo "3) waiting for the connection to register"
for _ in $(seq 1 20); do
  sleep 2
  if journalctl --user -u cloudflared-voxora.service --since '1 minute ago' --no-pager 2>/dev/null \
      | grep -q 'Registered tunnel connection'; then
    echo "   tunnel connected"
    break
  fi
done

echo "4) checking the public endpoint"
curl -s -m 20 -o /dev/null -w "   https://api.semispeak.com/api/v1/health -> HTTP %{http_code}\n" \
  https://api.semispeak.com/api/v1/health

echo
echo "If this still reports 530, restart the API too:"
echo "  systemctl --user restart voxora-api.service"
