#!/bin/bash
source /home/ubuntu/prpo_ai/duckdns/credentials.env
DOMAIN="$DUCKDNS_DOMAIN"
TOKEN="$DUCKDNS_TOKEN"
# Boss-specified VPS IP (override ipify detection)
CURRENT_IP="${VPS_IP:-43.128.111.166}"
RESPONSE=$(curl -s --max-time 10 "https://www.duckdns.org/update?domains=${DOMAIN}&token=${TOKEN}&ip=${CURRENT_IP}")
echo "[$(date -u +%FT%TZ)] ${DOMAIN}.duckdns.org -> ${CURRENT_IP} : ${RESPONSE}"
