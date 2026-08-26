import os
import sqlite3
from pathlib import Path
from datetime import datetime, timezone
import csv
import io
import hmac

from dotenv import load_dotenv
from flask import Flask, jsonify, render_template, request, session, redirect, url_for, Response

try:
    from openai import OpenAI
except ImportError:
    OpenAI = None

BASE_DIR = Path(__file__).resolve().parent
DB_PATH = BASE_DIR / "jimmind.db"
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



def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    with get_db() as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS service_inquiries (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                mobile TEXT NOT NULL,
                city TEXT NOT NULL,
                service TEXT NOT NULL,
                language TEXT NOT NULL DEFAULT 'en',
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS clients (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                mobile TEXT NOT NULL UNIQUE,
                city TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
            """
        )


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
    with get_db() as conn:
        conn.execute(
            """
            INSERT INTO service_inquiries
            (name, mobile, city, service, language, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (name, mobile, city, service, language, now),
        )
        conn.execute(
            """
            INSERT INTO clients (name, mobile, city, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(mobile) DO UPDATE SET
                name=excluded.name,
                city=excluded.city,
                updated_at=excluded.updated_at
            """,
            (name, mobile, city, now, now),
        )
    return True, "Inquiry submitted successfully."


@app.get("/")
def index():
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

@app.get("/admin")
def admin_dashboard():
    gate = require_admin()
    if gate: return gate
    q = request.args.get("q", "").strip()
    service = request.args.get("service", "").strip()
    with get_db() as conn:
        clauses, params = [], []
        if q:
            clauses.append("(name LIKE ? OR mobile LIKE ? OR city LIKE ? OR service LIKE ?)")
            params.extend([f"%{q}%"] * 4)
        if service:
            clauses.append("service = ?")
            params.append(service)
        where = (" WHERE " + " AND ".join(clauses)) if clauses else ""
        rows = conn.execute(f"SELECT * FROM service_inquiries{where} ORDER BY id DESC", params).fetchall()
        total = conn.execute("SELECT COUNT(*) FROM service_inquiries").fetchone()[0]
        clients = conn.execute("SELECT COUNT(*) FROM clients").fetchone()[0]
        services = conn.execute("SELECT service, COUNT(*) count FROM service_inquiries GROUP BY service ORDER BY count DESC").fetchall()
    return render_template("admin.html", inquiries=rows, total=total, clients=clients, services=services, q=q, selected_service=service)

@app.get("/admin/export.csv")
def admin_export():
    gate = require_admin()
    if gate: return gate
    q = request.args.get("q", "").strip()
    service = request.args.get("service", "").strip()
    with get_db() as conn:
        clauses, params = [], []
        if q:
            clauses.append("(name LIKE ? OR mobile LIKE ? OR city LIKE ? OR service LIKE ?)")
            params.extend([f"%{q}%"] * 4)
        if service:
            clauses.append("service = ?")
            params.append(service)
        where = (" WHERE " + " AND ".join(clauses)) if clauses else ""
        rows = conn.execute(f"SELECT id,name,mobile,city,service,language,created_at FROM service_inquiries{where} ORDER BY id DESC", params).fetchall()
    out = io.StringIO()
    writer = csv.writer(out)
    writer.writerow(["ID","Name","Mobile","City","Service","Language","Created At (UTC)"])
    for r in rows: writer.writerow([r[k] for k in r.keys()])
    return Response("\ufeff" + out.getvalue(), mimetype="text/csv", headers={"Content-Disposition":"attachment; filename=jimmind_service_inquiries.csv"})

@app.get("/health")
def health():
    return jsonify({"status": "ok", "database": DB_PATH.name})


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
            "message": "I’m unable to answer right now. Please try again or submit a service inquiry."
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
