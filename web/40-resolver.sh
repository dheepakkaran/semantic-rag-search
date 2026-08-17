#!/bin/sh
# Two things nginx needs at container start, both platform-specific.
#
# 1. A resolver. Without one, nginx resolves a proxy_pass hostname once and
#    caches the address forever, so a redeployed backend is never picked up.
#    Docker's embedded DNS is at 127.0.0.11; Kubernetes runs CoreDNS somewhere
#    else. The container's own resolv.conf already knows which.
#
# 2. The upstream address. nginx's resolver queries the name verbatim — it does
#    not apply the search domains from resolv.conf the way a normal lookup
#    does. So "node-api" works under Compose but is NXDOMAIN in Kubernetes,
#    where the service is node-api.<namespace>.svc.cluster.local. Rather than
#    guess, the deployment says which via NODE_API_UPSTREAM.
set -e

resolver=$(awk '/^nameserver/ { print $2; exit }' /etc/resolv.conf)
resolver=${resolver:-127.0.0.11}
upstream=${NODE_API_UPSTREAM:-http://node-api:3001}

echo "resolver: ${resolver} (from /etc/resolv.conf)"
echo "upstream: ${upstream}"

sed -i "s|__RESOLVER__|${resolver}|g; s|__UPSTREAM__|${upstream}|g" \
  /etc/nginx/conf.d/default.conf
