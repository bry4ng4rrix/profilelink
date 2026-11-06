#!/bin/sh
# Rewrites the list of Cloudflare ranges trusted by Nginx. Reload Nginx afterwards.
set -eu
cd "$(dirname "$0")/.."
ranges=$(curl -fsS https://www.cloudflare.com/ips-v4; echo; curl -fsS https://www.cloudflare.com/ips-v6)
{
  echo '# Source: https://www.cloudflare.com/ips/ — refresh with scripts/update-cloudflare-ips.sh'
  for ip in $ranges; do echo "set_real_ip_from $ip;"; done
} > nginx/cloudflare-real-ip.conf
