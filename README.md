# Women Safety System: Backend

The Flask backend for the CEP project *Women Safety System* (PCU, Dept. of CSE-AI&DS). It follows the
blueprint in the project presentation:

| Blueprint item (PPT) | Implementation |
|---|---|
| Backend: Python + Flask | Flask 3 app factory, one blueprint per module |
| Database: SQLite → MySQL later | SQLAlchemy + Alembic migrations; switching to MySQL only means changing `DATABASE_URL` |
| Authentication: password hashing + secure sessions | Werkzeug scrypt hashes, Flask-Login HttpOnly/SameSite session cookies |
| SOS processing / 9-step algorithm | `app/services/emergency_engine.py` |
| Location API / Maps (Google Maps / OSM) | `app/api/location.py`, map links in alerts, live-tracking page on Leaflet + OpenStreetMap |
| Alert system (call / map / email icons) | `app/services/alert_service.py` with pluggable channels: console, email (SMTP), SMS (Twilio) |
| Voice Trigger → Verify Command | `app/api/voice.py` + fuzzy phrase matching |
| AI Detection → Risk Analysis (Low / Medium / High) | `app/services/risk/`: scikit-learn model plus a rule-based fallback |
| Track Incident / history | `app/api/incidents.py` |

```
SOS button ──► Get GPS ───────────┐
Voice ──► Verify command ─────────┼──► Emergency Engine ──► Create alert ──► Send to contacts (+ location) ──► Track incident
AI sensors ──► Risk analysis ─────┘        (one code path for every trigger)
```

## Quick start (Windows)

```powershell
python -m venv .venv
.venv\Scripts\pip install -r requirements.txt
Copy-Item .env.example .env
.venv\Scripts\flask db upgrade
.venv\Scripts\flask train-risk-model
.venv\Scripts\flask run
```

The API runs at `http://localhost:5000`. With the default `ALERT_CHANNELS=console`, alerts are printed in the
server terminal and saved in the database, so you can demo the whole flow without SMS or email accounts.

Run the tests:

```powershell
.venv\Scripts\python -m pytest
```

## How the main flows work

**SOS (the PPT's algorithm).** `POST /api/sos/trigger`:

1. Check for GPS. If the app sent no coordinates, use the last known location if it's less than 15 minutes old.
2. Load the emergency contacts, highest priority first.
3. Save the incident.
4. Send each contact a message on every enabled channel. The message has Google Maps and OpenStreetMap links and a
   private **live-tracking link**.
5. While the incident is active, every location the app posts extends the track that contacts see.
6. `POST /api/sos/<id>/cancel` ends the emergency, sends an "all clear", and stops location sharing.

Pressing SOS again while an emergency is active returns the same incident, so contacts don't get flooded with
duplicate alerts. SOS is **never rate-limited**. If an alert went out without a location, contacts get an update
as soon as the first GPS fix arrives.

**Voice.** The app does speech-to-text on the device (for example with the browser's Web Speech API) and sends
the transcript to `POST /api/voice/verify`. The backend fuzzy-matches it against the user's trigger phrases
(defaults: *help me*, *bachao*, *emergency*; Hindi in Devanagari works too). A match raises an emergency.

**AI risk detection.** The phone (shake or fall detection), or later the ESP32 wearable, posts sensor windows to
`POST /api/ai/assess`. The response follows the PPT policy:

| Score | Level | Action |
|---|---|---|
| < 0.40 | Low | No action |
| 0.40 – 0.75 | Medium | Ask the user "are you safe?". If they don't answer `POST /api/ai/assessments/<id>/respond` within 60 s, an alert goes out automatically |
| ≥ 0.75 | High | Emergency alert immediately |

Features used: peak acceleration, fall flag, movement variance, heart rate and its change from the user's resting
rate, voice-distress score, and night time. The model is a RandomForest trained by `flask train-risk-model` on a
**synthetic** dataset of everyday and danger scenarios (`app/services/risk/train.py`). Its accuracy figures only
measure performance on that simulated data. It proves the pipeline works but is not a validated safety model, so
retrain it on real wearable recordings once you have them. If the model file is missing, a transparent rule-based
scorer is used instead.

## API reference

All endpoints return JSON. `POST`/`PATCH` requests must send `Content-Type: application/json` (this is part of the
CSRF protection), even when the body is just `{}`. Errors always look like this:

```json
{"error": {"code": "validation_error", "message": "Request validation failed.", "details": {"phone": ["..."]}}}
```

Login uses a session cookie, so frontends must send requests with `credentials: "include"` and be listed in
`FRONTEND_ORIGINS`.

| Method & path | Body / query | Notes |
|---|---|---|
| `POST /api/auth/register` | `name, email, phone, password` | Logs the user in. Local 10-digit numbers get `+91` |
| `POST /api/auth/login` | `email` **or** `phone`, `password`, `remember?` | Rate-limited |
| `POST /api/auth/logout` | `{}` | |
| `GET /api/auth/me` | | User + active incident |
| `GET /api/dashboard` | | Everything the Safety Dashboard needs |
| `GET / PATCH /api/profile` | `name, email, phone, custom_message, baseline_heart_rate` | `custom_message` is added to every alert |
| `POST /api/profile/password` | `current_password, new_password` | |
| `GET / POST /api/contacts` | `name, phone?, email?, relation?, priority?, notify_sms?, notify_email?` | Max 10; needs a phone or email |
| `GET / PATCH / DELETE /api/contacts/<id>` | | |
| `POST /api/sos/trigger` | `lat?, lng?, accuracy_m?, note?` | 201 = new incident, 200 = already active |
| `GET /api/sos/active` | | |
| `POST /api/sos/<id>/location` | `lat, lng, accuracy_m?` | Live tracking |
| `POST /api/sos/<id>/cancel` | `reason: "safe" \| "false_alarm"` | Sends the all-clear |
| `POST /api/location` | `lat, lng, accuracy_m?` | Heartbeat; joins the live track during an emergency |
| `GET /api/location/last` | | |
| `GET /api/incidents` | `?page=&per_page=&status=` | History |
| `GET /api/incidents/<id>` | | Includes the track and the alert audit trail |
| `GET /api/incidents/<id>/alerts` | | |
| `GET / POST /api/voice/phrases` | `phrase` | Max 10 |
| `DELETE /api/voice/phrases/<id>` | | |
| `POST /api/voice/verify` | `transcript, confidence?, lat?, lng?` | Raises an emergency on a match |
| `POST /api/ai/assess` | `accel_peak_g, fall_detected, movement_variance, heart_rate?, voice_distress, local_hour?, lat?, lng?` | |
| `POST /api/ai/assessments/<id>/respond` | `safe: true \| false` | |
| `GET /api/ai/assessments` | `?status=` | |
| `GET /api/ai/model-info` | | Model version, metrics, policy |
| `GET /track/<token>` | | **Public** live map for contacts |
| `GET /api/track/<token>` | | Public JSON for that page; hides the location once the emergency ends |
| `GET /api/health` | | |

## Walkthrough with curl

These commands use bash syntax (Git Bash on Windows) and keep the session cookie in `jar.txt`:

```bash
B=http://localhost:5000/api; H='Content-Type: application/json'
curl -c jar.txt -b jar.txt -H "$H" -X POST $B/auth/register -d '{"name":"Aaroh Demo","email":"demo@example.com","phone":"9876501234","password":"demo-pass-123"}'
curl -c jar.txt -b jar.txt -H "$H" -X POST $B/contacts -d '{"name":"Mom","phone":"9123401234","relation":"mother"}'
curl -c jar.txt -b jar.txt -H "$H" -X POST $B/sos/trigger -d '{"lat":18.5204,"lng":73.8567,"accuracy_m":15}'
# open the tracking_url from the response in a browser, then:
curl -c jar.txt -b jar.txt -H "$H" -X POST $B/sos/1/location -d '{"lat":18.5212,"lng":73.8575}'
curl -c jar.txt -b jar.txt -H "$H" -X POST $B/sos/1/cancel -d '{"reason":"safe"}'
```

## Configuration

Every setting is an environment variable; see `.env.example`. The important ones:

- `DATABASE_URL`: SQLite by default. For MySQL, run `pip install PyMySQL`, set
  `mysql+pymysql://user:pass@host/women_safety?charset=utf8mb4`, then run `flask db upgrade`.
- `ALERT_CHANNELS`: `console`, `email`, `sms` (comma-separated). Email needs the `SMTP_*` settings. SMS needs
  `pip install twilio` and the `TWILIO_*` settings.
- `PUBLIC_BASE_URL`: the address contacts use to open the tracking link. It must be reachable from their phones
  once deployed.
- `RISK_MEDIUM_THRESHOLD`, `RISK_HIGH_THRESHOLD`, `RISK_CONFIRM_WINDOW_SECONDS`: the AI policy.
- `APP_ENV=production` requires a real `SECRET_KEY` and turns on Secure cookies (HTTPS only).

For production on Windows: run `pip install waitress`, then `waitress-serve --port=5000 wsgi:app`.

## Project layout

```
app/
  __init__.py          app factory, security hooks
  config.py            settings
  models/              users, contacts, incidents, location points, alerts, trigger phrases, risk assessments
  schemas.py           request validation
  api/                 auth, profile, dashboard, contacts, sos, location, incidents, voice, ai, tracking, health
  services/
    emergency_engine.py   the 9-step SOS algorithm, shared by every trigger
    alert_service.py      message building + delivery to contacts
    notifiers/            console / email / sms channels
    location_service.py   GPS fallback, map links
    voice_service.py      voice command verification
    risk/                 features, scorer, policy, training, assessment workflow
    sweeper.py            auto-escalates unanswered Medium-risk checks
  templates/, static/  live-tracking page for contacts
migrations/            Alembic migrations
ml/                    trained model (created by `flask train-risk-model`)
tests/                 pytest suite
```

## Security notes

- Passwords are hashed (scrypt), never stored or returned.
- Logging in starts a fresh session. Cookies are HttpOnly + SameSite=Lax, and Secure in production.
- All data is scoped to the logged-in user; another user's ids return 404.
- Tracking links use 256-bit random tokens and stop showing the location once the emergency ends. The tracking
  page sends a strict Content-Security-Policy and never leaks the token in the `Referer` header.
- Login, sensor and tracking endpoints are rate-limited. SOS is intentionally not.
- Outside an emergency, only the user's latest location is stored.
