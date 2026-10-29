# HyperDrop 🚀
### Hackathon-Ready AI Voice Agent for Last-Mile Delivery Exceptions

HyperDrop is an autonomous, multilingual AI voice delivery coordinator that resolves last-mile delivery exceptions in real time between a customer and a delivery rider—each speaking in their own native language.

---

## 🏗️ Architecture & Stack

- **Backend**: Python 3.11+, FastAPI, Pydantic v2
- **Data Layer**: SQLModel (SQLite default, PostgreSQL-ready)
- **Concurrency**: Native `asyncio` background tasks (no Celery required)
- **Live Updates**: Real-time WebSocket channel (`/ws/dashboard`)
- **Dashboard**: High-performance single-page split-screen console (HTML5 + CSS3 + Vanilla ES6 JS)
- **Voice Providers**:
  - `MockVoiceProvider` (**Default**): Simulates inbound/outbound calls with realistic conversational turn delays, zero external keys needed.
  - `BolnaVoiceProvider`: Real outbound telephony via [Bolna AI](https://bolna.dev) API with webhooks and function-calling intent extraction.
- **Translation Engine**: `Translator` interface powered by Anthropic Claude (with built-in high-fidelity spoken colloquial mock fallback across English, Hindi, Hinglish, Kannada, Tamil, and Telugu).
- **Payment Gateway**: `PaymentProvider` interface with Mock UPI integration (payment links + instant webhook confirmation).

---

## ⚡ Quickstart (Zero Keys Required)

### 1. Install Dependencies
```bash
pip install -r requirements.txt
```

### 2. Configure Environment (Optional)
```bash
cp .env.example .env
```
*Note: By default, HyperDrop runs in fully self-contained Mock mode with zero external API keys.*

### 3. Seed Sample Data
```bash
python seed.py
```
This populates sample customers (Hindi, English, Telugu), riders (Kannada, Tamil), and realistic delivery orders (Prepaid, High-Value, and COD).

### 4. Run the Application
```bash
uvicorn app.main:app --reload
```

Open your browser at **`http://localhost:8000`** to access the live split-screen dashboard.

---

## 🧪 Automated Test Suite

Run all unit and integration tests covering the state machine, token generation & expiry, COD payment gating, and extraction validation:

```bash
pytest -v
```

All 14 tests pass across:
1. `tests/test_state_machine.py`: Verifies valid transitions, illegal transitions, and human escalation fallbacks.
2. `tests/test_token_expiry.py`: Tests 6-digit one-time token generation, single-use invalidation, and 15-minute expiry enforcement.
3. `tests/test_cod_gating.py`: Enforces that COD deliveries block alternate handover until payment webhook confirmation.
4. `tests/test_extraction_validation.py`: Tests structured JSON validation, recipient role requirements, and high-value verbal confirmation rules.
5. `tests/test_api_scenarios.py`: End-to-end API test verifying exception creation, rate limiting, and scenario triggering.

---

## 🔄 Delivery State Machine

Every transition is timestamped, audited, and streamed in real time over WebSockets:

```
CREATED 
   │
   ▼
CALLING_CUSTOMER ───────────────► NO_ANSWER
   │                                 │
   │ (Resolved)                      ├─► RETRYING_CUSTOMER (Attempt 2)
   ▼                                 ├─► CALLING_ALT_PHONE / SECURITY DESK
RESOLVED                             ├─► FALLBACK_NOTIFICATION (WhatsApp/SMS)
   │                                 └─► ESCALATED_TO_HUMAN
   ├───────────────────────────────┐
   │ (If COD)                      │ (Prepaid)
   ▼                               │
AWAITING_PAYMENT                   │
   │ (Payment Webhook Confirmed)   │
   ▼                               │
PAYMENT_CONFIRMED                  │
   │                               │
   └───────────────┬───────────────┘
                   ▼
             CALLING_RIDER
                   │
                   ▼
             RIDER_CONFIRMED
                   │
                   ▼
             HANDOVER_VERIFIED (Token or Photo Proof)
                   │
                   ▼
                CLOSED
```

---

## 🛡️ Enforced Safety Rules

1. **Gate Security**: Permanent community codes are **never** spoken aloud or shared with riders. HyperDrop dynamically generates single-use 6-digit tokens (`GatePassToken`) with a 15-minute expiry.
2. **High-Value Protection**: Orders exceeding the high-value threshold (`HIGH_VALUE_THRESHOLD = ₹2000`) strictly require customer OTP or verbal confirmation before alternate drop instructions are accepted.
3. **COD Payment Gating**: The agent never holds or moves money. The rider is informed of successful payment **strictly after** the payment webhook fires. Handover without payment confirmation is rejected.
4. **Mandatory Call Disclosure**: Every customer and rider call leg discloses at call start: *"Namaste! This is an automated call from HyperDrop, recorded for delivery safety."*
5. **Audit Trail**: Every customer instruction and confirmation is stored in `ConsentLog` with reference transcripts and timestamps.
6. **Rate Limiting**: Exception generation is protected by sliding-window rate limiting (`EXCEPTION_RATE_LIMIT_PER_MINUTE = 20`).

---

## 🎙️ Bolna AI Outbound Voice Integration

To enable live phone calls via Bolna's conversational voice platform:

1. Create an account at [Bolna.dev](https://bolna.dev) and generate an API key.
2. Create an Outbound Agent in Bolna dashboard and copy the `Agent ID`.
3. In Bolna agent configuration:
   - Configure the function-calling tool `extract_delivery_outcome` matching the schema in `prompts/extractor_v1.txt`.
   - Set the webhook callback URL to `https://<YOUR-PUBLIC-URL>/webhooks/voice`.
4. Update your `.env`:
   ```ini
   VOICE_PROVIDER="bolna"
   BOLNA_API_KEY="your_bolna_api_key"
   BOLNA_AGENT_ID="your_bolna_agent_id"
   WEBHOOK_BASE_URL="https://<YOUR-PUBLIC-URL>"
   ```
5. When `VOICE_PROVIDER="bolna"`, outbound call legs are automatically dispatched through Bolna's low-latency telephony infrastructure, and transcript turns are streamed back into the HyperDrop dashboard via `/webhooks/voice`.

---

## 🎬 3-Minute Demo Script (For Hackathon Judges)

### **Minute 0:00 - 0:45 | Introduction & Problem Setup**
1. Open the HyperDrop Dashboard at `http://localhost:8000`.
2. **The Problem**: *"In last-mile delivery, 18% of failed deliveries happen because the customer and rider cannot communicate—either the customer is busy in a meeting, or there is a language barrier (e.g., a Kannada-speaking rider in Bengaluru and a Hindi-speaking customer), or COD payment is pending. Today, this leads to expensive RTO (Return to Origin)."*
3. Show the **Top KPI Strip**: Real-time average resolution time (&lt;30s), relay latency (~180ms), and cost per exception (₹1.80 vs ₹45 manual support).

### **Minute 0:45 - 1:30 | Scenario 2: Busy Customer & One-Time Gate Pass**
1. Click **`🏢 S2 Busy Customer`**.
2. **Observe Left Pane**: Agent calls customer Priya Sharma (Hinglish), gives the automated recording disclosure, and presents the delivery menu. Customer says: *"I'm in an urgent meeting, please leave the package with security guard Ramesh at Tower B gate."*
3. **Observe Center Pane**:
   - Agent validates extracted JSON via function calling.
   - Generates a **6-digit single-use Gate Pass Token** (e.g. `849201`) with a 15-minute countdown. Notice permanent codes are never read aloud.
4. **Observe Right Pane**: Agent calls rider Raju Gowda in **Kannada**:
   *"Raju avare, parcel annu security Ramesh ge kodi. Gate pass token code: 849201."*
5. Handover is verified with the token and the delivery closes automatically.

### **Minute 1:30 - 2:15 | Scenario 3: Cash On Delivery (COD) Payment Gating**
1. Click **`💳 S3 Cash On Delivery`**.
2. **The Problem**: Order is COD (₹1,299). The customer is away.
3. **Observe**:
   - Agent calls customer and generates an instant UPI payment link sent via WhatsApp.
   - State enters `AWAITING_PAYMENT`.
   - **Crucial Safety Rule**: Point out to judges that the rider is **NOT** told to drop the parcel yet.
   - Once the payment webhook fires (`PAYMENT_CONFIRMED`), the rider is called: *"Payment of ₹1299 confirmed via UPI. Do not collect cash."*
   - Rider uploads photo proof and order transitions to `CLOSED`.

### **Minute 2:15 - 3:00 | Scenario 1: Real-Time Dual-Leg Language Relay**
1. Click **`🌐 S1 Language Relay`**.
2. **The Wow Factor**: Customer speaks Hindi; Rider speaks Kannada.
3. The agent acts as an ultra-low-latency bridge:
   - Rider speaks Kannada (*"Naanu gate hattira idhini"*).
   - Agent translates and speaks to Customer in Hindi (*"Raju keh rahe hain: Main gate par hoon"*).
   - Customer replies in Hindi (*"Tower B basement gate par aane ko bolo"*).
   - Agent translates and speaks to Rider in Kannada (*"Raju avare, Tower B basement gate ge banni"*).
4. Point out the **Relay Latency pill (⚡ ~150ms)** on every turn and the updated KPI averages.
5. Conclude: *"HyperDrop eliminates RTO, protects privacy, and resolves last-mile exceptions in under 45 seconds at 1/20th the cost of human support."*

---

## 📡 API Reference Summary

| Method | Endpoint | Description |
|---|---|---|
| `POST` | `/exceptions` | Triggers a new delivery exception (Rate-limited) |
| `GET` | `/exceptions/{id}` | Fetches full state machine status, legs, and transcripts |
| `POST` | `/webhooks/voice` | Webhook for call events, speech turns, and extractions |
| `POST` | `/webhooks/payment` | Webhook for payment gateway confirmations |
| `POST` | `/handover/{id}/verify` | Verifies gate pass token or rider delivery photo |
| `GET` | `/kpis` | Returns real-time KPI metrics (resolution time, latency, cost) |
| `WS` | `/ws/dashboard` | WebSocket channel for live event streaming |
| `POST` | `/demo/simulate/{scenario}` | Simulates `S1`, `S2`, `S3`, or `NO_ANSWER` end-to-end |
