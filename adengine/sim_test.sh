#!/bin/bash
# Simulate full ad flow: order + payment -> emails to Bossy Gmail
cd /home/ubuntu/prpo_ai/adengine
echo "=== 1. ORDER (triggers invoice email to advertiser + notify marketing) ==="
RESP=$(curl -s -X POST https://xhagents.xyz/api/ad-order -H 'Content-Type: application/json' \
  --data '{"size":"728x90","network":"solana","email":"yusliarifn78@gmail.com","title":"TestCo AI","text":"Best agent ever","landing_url":"https://testco.example.com"}')
echo "$RESP"
OID=$(echo "$RESP" | /home/ubuntu/prpo_ai/venv/bin/python -c "import sys,json;print(json.load(sys.stdin)['order_id'])")
echo "order_id=$OID"
sleep 3
echo "=== 2. SIMULATE PAYMENT (activate -> triggers 'ad live' email) ==="
curl -s -X POST https://xhagents.xyz/api/ads/activate -H 'Content-Type: application/json' \
  --data "{\"id\":\"$OID\",\"size\":\"728x90\",\"title\":\"TestCo AI\",\"text\":\"Best agent ever\",\"image_url\":\"\",\"landing_url\":\"https://testco.example.com\",\"email\":\"yusliarifn78@gmail.com\"}" -w " [HTTP %{http_code}]\n"
sleep 2
echo "=== 3. ads.json ==="
curl -s https://xhagents.xyz/ads.json
echo ""
echo "=== cleanup test ad ==="
echo "[]" > /home/ubuntu/prpo_ai/adengine/ads.json
/home/ubuntu/prpo_ai/venv/bin/python -c "import sqlite3;c=sqlite3.connect('ads.db');c.execute('DELETE FROM orders');c.commit();print('db cleaned')"