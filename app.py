import os
import re
from pathlib import Path
from datetime import datetime, timezone
import csv
import io
import hmac

from dotenv import load_dotenv
from flask import Flask, jsonify, render_template, request, session, redirect, url_for, Response

from pymongo import MongoClient, ASCENDING
from pymongo.errors import PyMongoError

try:
    from openai import OpenAI
except ImportError:
    OpenAI = None

BASE_DIR = Path(__file__).resolve().parent
KNOWLEDGE_PATH = BASE_DIR / "knowledge_base.md"

load_dotenv(BASE_DIR / ".env")

app = Flask(__name__)
app.config["JSON_SORT_KEYS"] = False
app.secret_key = os.getenv("SESSION_SECRET", "change-this-session-secret")
app.config["PERMANENT_SESSION_LIFETIME"] = 28800

def admin_password_configured():
    return bool(os.getenv("ADMIN_PASSWORD", "").strip())

def admin_logged_in():
    return session.get("admin_authenticated") is True

def require_admin():
    if not admin_logged_in():
        return redirect(url_for("admin_login"))
    return None


# ---------------------------------------------------------------------------
# MongoDB setup
# ---------------------------------------------------------------------------
MONGO_URI = os.getenv("MONGO_URI", "mongodb://localhost:27017").strip()
MONGO_DB_NAME = os.getenv("MONGO_DB_NAME", "jimmind").strip() or "jimmind"

mongo_client = MongoClient(MONGO_URI)
db = mongo_client[MONGO_DB_NAME]

service_inquiries_col = db["service_inquiries"]
clients_col = db["clients"]


def init_db():
    """Ensure indexes exist (Mongo creates collections lazily on first write)."""
    # Unique index on mobile for clients, mirroring the old SQLite UNIQUE constraint.
    clients_col.create_index([("mobile", ASCENDING)], unique=True)
    # Helpful index for querying inquiries by mobile/created_at.
    service_inquiries_col.create_index([("mobile", ASCENDING)])
    service_inquiries_col.create_index([("created_at", ASCENDING)])


def load_knowledge():
    try:
        return KNOWLEDGE_PATH.read_text(encoding="utf-8")
    except OSError:
        return ""


def valid_mobile(value):
    digits = "".join(ch for ch in value if ch.isdigit())
    return len(digits) == 10


def save_inquiry(data):
    name = data.get("name", "").strip()
    mobile = data.get("mobile", "").strip()
    city = data.get("city", "").strip()
    service = data.get("service", "").strip()
    language = data.get("language", "en").strip() or "en"

    if not name or not city or not service or not valid_mobile(mobile):
        return False, "Please enter a valid name, 10-digit mobile number, city and service."

    now = datetime.now(timezone.utc).isoformat()

    try:
        service_inquiries_col.insert_one(
            {
                "name": name,
                "mobile": mobile,
                "city": city,
                "service": service,
                "language": language,
                "created_at": now,
            }
        )

        # Upsert into clients, keyed on unique mobile number (mirrors the old
        # SQLite "ON CONFLICT(mobile) DO UPDATE" behavior).
        clients_col.update_one(
            {"mobile": mobile},
            {
                "$set": {
                    "name": name,
                    "city": city,
                    "updated_at": now,
                },
                "$setOnInsert": {
                    "mobile": mobile,
                    "created_at": now,
                },
            },
            upsert=True,
        )
    except PyMongoError:
        app.logger.exception("MongoDB write error while saving inquiry")
        return False, "Something went wrong while saving your inquiry. Please try again."

    return True, "Inquiry submitted successfully."


@app.get("/")
def landing():
    """Entry gate. Visitors can Skip straight to the main site."""
    return render_template("login.html")


@app.get("/home")
def home():
    return render_template("index.html")


@app.route("/admin/login", methods=["GET", "POST"])
def admin_login():
    error = None
    if request.method == "POST":
        password = request.form.get("password", "")
        configured = os.getenv("ADMIN_PASSWORD", "")
        if configured and hmac.compare_digest(password, configured):
            session.clear()
            session["admin_authenticated"] = True
            session.permanent = True
            return redirect(url_for("admin_dashboard"))
        error = "Invalid admin password." if configured else "ADMIN_PASSWORD is not configured in .env."
    return render_template("admin_login.html", error=error)

@app.get("/admin/logout")
def admin_logout():
    session.clear()
    return redirect(url_for("admin_login"))

def _build_inquiry_query(q, service):
    """Build a MongoDB filter mirroring the old SQLite LIKE/AND search."""
    clauses = []
    if q:
        pattern = {"$regex": re.escape(q), "$options": "i"}
        clauses.append({"$or": [
            {"name": pattern}, {"mobile": pattern}, {"city": pattern}, {"service": pattern},
        ]})
    if service:
        clauses.append({"service": service})
    if not clauses:
        return {}
    if len(clauses) == 1:
        return clauses[0]
    return {"$and": clauses}


def _serialize_inquiry(doc):
    return {
        "id": str(doc.get("_id", "")),
        "name": doc.get("name", ""),
        "mobile": doc.get("mobile", ""),
        "city": doc.get("city", ""),
        "service": doc.get("service", ""),
        "language": doc.get("language", "en"),
        "created_at": doc.get("created_at", ""),
    }


@app.get("/admin")
def admin_dashboard():
    gate = require_admin()
    if gate: return gate
    q = request.args.get("q", "").strip()
    service = request.args.get("service", "").strip()

    query = _build_inquiry_query(q, service)
    cursor = service_inquiries_col.find(query).sort("created_at", -1)
    rows = [_serialize_inquiry(doc) for doc in cursor]

    total = service_inquiries_col.count_documents({})
    clients = clients_col.count_documents({})

    services_agg = service_inquiries_col.aggregate([
        {"$group": {"_id": "$service", "count": {"$sum": 1}}},
        {"$sort": {"count": -1}},
    ])
    services = [{"service": s["_id"], "count": s["count"]} for s in services_agg]

    return render_template("admin.html", inquiries=rows, total=total, clients=clients, services=services, q=q, selected_service=service)

@app.get("/admin/export.csv")
def admin_export():
    gate = require_admin()
    if gate: return gate
    q = request.args.get("q", "").strip()
    service = request.args.get("service", "").strip()

    query = _build_inquiry_query(q, service)
    cursor = service_inquiries_col.find(query).sort("created_at", -1)

    out = io.StringIO()
    writer = csv.writer(out)
    writer.writerow(["ID","Name","Mobile","City","Service","Language","Created At (UTC)"])
    for doc in cursor:
        r = _serialize_inquiry(doc)
        writer.writerow([r["id"], r["name"], r["mobile"], r["city"], r["service"], r["language"], r["created_at"]])
    return Response("\ufeff" + out.getvalue(), mimetype="text/csv", headers={"Content-Disposition":"attachment; filename=jimmind_service_inquiries.csv"})

@app.get("/health")
def health():
    try:
        mongo_client.admin.command("ping")
        db_status = "ok"
    except PyMongoError:
        db_status = "unreachable"
    return jsonify({"status": "ok", "database": MONGO_DB_NAME, "mongo": db_status})


@app.post("/api/inquiry")
def inquiry():
    data = request.get_json(silent=True) or {}
    ok, message = save_inquiry(data)
    return jsonify({"ok": ok, "message": message}), (200 if ok else 400)


@app.post("/api/chat")
def chat():
    data = request.get_json(silent=True) or {}
    user_message = str(data.get("message", "")).strip()
    if not user_message:
        return jsonify({"ok": False, "message": "Please enter a question."}), 400

    api_key = os.getenv("OPENAI_API_KEY", "").strip()
    model = os.getenv("OPENAI_MODEL", "gpt-5.2").strip()
    knowledge = load_knowledge()

    if not api_key:
        return jsonify({
            "ok": False,
            "message": "Chat is temporarily unavailable because the OpenAI API key is not configured."
        }), 503

    if OpenAI is None:
        return jsonify({
            "ok": False,
            "message": "The OpenAI Python package is not installed. Run: pip install -r requirements.txt"
        }), 503

    system_prompt = f"""
You are the JIMMIND AI Voter Services Assistant.

STRICT SCOPE:
- Answer ONLY using the knowledge document below.
- The document is the exclusive source of truth.
- Do not use general knowledge, browsing, external websites, hidden knowledge, or assumptions.
- Do not invent fees, eligibility rules, documents, timelines, government charges, guarantees, or procedures.
- If the answer is not explicitly supported by the document, politely say that you can only answer questions about JIMMIND AI's listed voter services, consultation fees, eligibility requirements, and process steps.
- You may answer in English or Hindi according to the user's language.
- Keep answers concise and practical.
- JIMMIND AI is a private consultancy/service-assistance provider, not the Election Commission of India. Never imply that JIMMIND AI is a government department.

KNOWLEDGE DOCUMENT:
--- BEGIN KNOWLEDGE ---
{knowledge}
--- END KNOWLEDGE ---
""".strip()

    user_prompt = f"""
User question:
{user_message}

Answer strictly from the knowledge document. If the requested information is outside the document, refuse/redirect politely.
""".strip()

    try:
        client = OpenAI(api_key=api_key)
        response = client.responses.create(
            model=model,
            instructions=system_prompt,
            input=user_prompt,
            store=False,
            text={"verbosity": "low"},
        )
        answer = (response.output_text or "").strip()
        if not answer:
            raise RuntimeError("Empty model response.")
        return jsonify({"ok": True, "answer": answer})
    except Exception:
        app.logger.exception("OpenAI chatbot error")
        return jsonify({
            "ok": False,
            "message": "I'm unable to answer right now. Please try again or submit a service inquiry."
        }), 502


init_db()


@app.route("/download")
def download():
    from flask import send_from_directory
    return send_from_directory(app.root_path, "README.md", as_attachment=True, download_name="JIMMIND_AI_README.md")


if __name__ == "__main__":
    port = int(os.getenv("PORT", "5000"))
    debug = os.getenv("FLASK_DEBUG", "0") == "1"
    app.run(host="0.0.0.0", port=port, debug=debug)