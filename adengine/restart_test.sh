#!/bin/bash
sudo systemctl restart xh-adengine
sleep 2
echo "service: $(sudo systemctl is-active xh-adengine)"
echo "--- test order (email skipped if no pass) ---"
curl -s -X POST https://xhagents.xyz/api/ad-order -H 'Content-Type: application/json' \
  --data '{"size":"300x250","network":"base","email":"test@demo.com","title":"T","text":"t","landing_url":"https://e.com"}' -w " [HTTP %{http_code}]\n"
# cleanup test order
cd /home/ubuntu/prpo_ai/adengine && /home/ubuntu/prpo_ai/venv/bin/python -c "import sqlite3;c=sqlite3.connect('ads.db');c.execute('DELETE FROM orders WHERE status=\"pending\"');c.commit();print('cleaned')"
