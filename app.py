import os
import sqlite3
from pathlib import Path
from datetime import datetime, timezone

from dotenv import load_dotenv
from flask import Flask, jsonify, render_template, request

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

if __name__ == "__main__":
    port = int(os.getenv("PORT", "5000"))
    debug = os.getenv("FLASK_DEBUG", "0") == "1"
    app.run(host="0.0.0.0", port=port, debug=debug)
