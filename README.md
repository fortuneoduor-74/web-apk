# ⚡ EarnNode Reward & Gigs Platform

A feature-complete Flask application leveraging high-concurrency background routing, real-time gaming engine simulations via WebSockets (`Flask-SocketIO` + `Eventlet`), account activation integrations via simulated M-Pesa webhooks, and administrative escrow micro-gigs.

## 🚀 System Architecture Features
* **Asynchronous Webhooks:** Handled via thread execution workers preventing client gateway timeout spikes.
* **Concurrent Event Loops:** Uses explicit `eventlet` monkey-patching for concurrent scaling under active WebSocket loads.
* **Safe Database Transactions:** Employs row-level database locks (`with_for_update()`) during account updates and reward balances to explicitly mitigate race conditions.
* **Dual Database Adaptability:** Seamless automated failover transitioning between localized testing (`SQLite`) and distributed production environments (`PostgreSQL`).

---

## 📂 Installation & Local Configuration

### 1. Set Up Environment
Clone your repository and build a virtual environment locally:
```bash
python -m venv venv
source venv/bin/activate  # On Windows use: venv\Scripts\activate
pip install -r requirements.txt
