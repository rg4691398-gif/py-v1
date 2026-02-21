# Flask Voucher System (Render-ready)

##Build Command
pip install -r requirements.txt

##Start Command
bash -c "python migrate.py && gunicorn app:app --bind 0.0.0.0:$PORT"

Username: admin
Password: change-me


## Local run
```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
export SECRET_KEY="dev-secret"
export BOOTSTRAP_ADMIN_USER="admin"
export BOOTSTRAP_ADMIN_PASS="admin123"
python migrate.py
python app.py
```

Open: http://127.0.0.1:5000

## Deploy to Render
- Push this repo to GitHub
- In Render: **New > Blueprint** and select repo (uses `render.yaml`)
- IMPORTANT: change `BOOTSTRAP_ADMIN_PASS` in Render environment variables after first deploy.

### SQLite persistence
This project expects DB at `DB_PATH` (default `/var/data/vouchers.db`), which is on a Render persistent disk (configured in `render.yaml`).

## Router auth API (NoDogSplash/BinAuth)
POST JSON to `/api/auth`:
```json
{
  "router_id":"R1",
  "mac":"aa:bb:cc:dd:ee:ff",
  "voucher":"AB12CD34",
  "ts": 1730000000,
  "nonce":"random-string",
  "sig":"hex-hmac-sha256"
}
```
`sig = HMAC_SHA256(router_secret, "router_id|mac|voucher|ts|nonce")` (hex lower-case).
