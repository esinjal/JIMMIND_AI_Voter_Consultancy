import os
import re
from pathlib import Path
from datetime import datetime, timezone
import csv
import io
import hmac

from dotenv import load_dotenv
from flask import Flask, jsonify, render_template, request, session, redirect, url_for, Response, abort

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
# MongoDB setup — used ONLY for the voter services domain (inquiries/clients).
# Tools and other future service verticals must not read/write these
# collections; give them their own collections/DB when they need persistence.
# ---------------------------------------------------------------------------
MONGO_URI = os.getenv("MONGO_URI", "mongodb://localhost:27017").strip()
MONGO_DB_NAME = os.getenv("MONGO_DB_NAME", "jimmind").strip() or "jimmind"

mongo_client = MongoClient(MONGO_URI)
db = mongo_client[MONGO_DB_NAME]

service_inquiries_col = db["service_inquiries"]
clients_col = db["clients"]


def init_db():
    """Ensure indexes exist (Mongo creates collections lazily on first write)."""
    clients_col.create_index([("mobile", ASCENDING)], unique=True)
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


# ---------------------------------------------------------------------------
# Content model — SERVICES and TOOLS.
#
# This drives the "Services"/"Tools" nav links and generates a dedicated page
# per item at /services/<slug> and /tools/<slug>, without duplicating page
# markup for every entry. To add a new service or tool, add an entry here
# (and, for a tool with custom interactive behaviour, a matching block in
# templates/tools/detail.html).
#
# Each service can offer multiple "request_types" — selectable sub-options
# shown as cards on that service's detail page and grouped in the inquiry
# form's dropdown. request_types["form_value"] is the exact string stored in
# MongoDB's "service" field; keep these stable once live, since existing
# inquiry/client records and the admin filter dropdown depend on them.
# ---------------------------------------------------------------------------
SERVICES = {
    "voter-service": {
        "slug": "voter-service",
        "icon": "🗳️",
        "no": "01",
        "title": "Voter Service",
        "short": "End-to-end assistance for new voter card, correction and mobile number update requests.",
        "fee_range": "₹99 – ₹199",
        "summary": (
            "JIMMIND AI assists voters through the full range of common voter-record "
            "requests — a new voter-registration application, a correction to an "
            "existing record, or a mobile-number update — with one consultant guiding "
            "you through preparation and submission."
        ),
        "who_for": "Anyone applying for a new voter record, correcting an existing one, or updating the mobile number linked to it.",
        "assistance": [
            "Understanding which request type applies to you",
            "Checking the information you supply for completeness",
            "Assisting with preparation of the application/request",
            "Guiding you through the applicable submission process",
            "Explaining how to keep your acknowledgement/reference details for follow-up",
        ],
        "documents": [
            "Proof of age and proof of ordinary residence (for a new application)",
            "Existing voter ID / EPIC number (for a correction or mobile update)",
            "Proof supporting a requested correction, where applicable",
            "A recent passport-size photograph, where applicable",
            "A valid mobile number for updates",
        ],
        "request_types_intro": "Voter Service covers three request types under one consultation flow. Pick the one that matches your need.",
        "fee_disclaimer": (
            "JIMMIND AI does not issue voter cards and cannot guarantee approval or "
            "processing time. Any separate government fee, if applicable, is not included."
        ),
        "request_types": [
            {
                "key": "new-voter-card",
                "form_value": "New voter card application",
                "title": "New Voter Card",
                "icon": "＋",
                "fee": "₹199",
                "fee_unit": "per application",
                "desc": "Preparing and submitting a new voter-registration application.",
            },
            {
                "key": "voter-correction",
                "form_value": "Voter card correction",
                "title": "Voter Card Correction",
                "icon": "↻",
                "fee": "₹149",
                "fee_unit": "per correction request",
                "desc": "Correcting name, address, age or photograph on an existing voter record.",
            },
            {
                "key": "mobile-update",
                "form_value": "Mobile number update",
                "title": "Mobile Number Update",
                "icon": "⌁",
                "fee": "₹99",
                "fee_unit": "per update request",
                "desc": "Updating the mobile number linked to an existing voter record.",
            },
        ],
    },
    "digital-media-influence": {
        "slug": "digital-media-influence",
        "icon": "📣",
        "no": "02",
        "title": "Digital Media Influence",
        "short": "Banners, articles, reels and promotional images to help your product reach an audience.",
        "fee_range": "₹399 – ₹1,499",
        "summary": (
            "JIMMIND AI helps businesses and individuals build a digital presence for "
            "their product — from designed banners and promotional images to written "
            "articles and short-form reel content — so you have ready-to-use material "
            "for your marketing and social channels."
        ),
        "who_for": "Businesses, creators or individuals who need design or content support to promote a product, service or brand online.",
        "assistance": [
            "Understanding your product and the audience you want to reach",
            "Recommending the content types (banner, article, reel, image) that fit your goal",
            "Producing the requested creative or written material",
            "Sharing drafts for your review before final delivery",
            "Delivering final files in formats ready to publish",
        ],
        "documents": [
            "Basic product/brand details (name, description, logo if available)",
            "Reference images or brand colours, if you have a preference",
            "Any existing marketing material you'd like matched in style",
            "A valid mobile number/email for sharing drafts",
        ],
        "request_types_intro": "Digital Media Influence covers four request types. Pick the one that matches what you need produced.",
        "fee_disclaimer": (
            "Fees shown are starting prices per deliverable and can vary with scope, "
            "revisions and turnaround time — your consultant will confirm the exact "
            "quote before work begins."
        ),
        "request_types": [
            {
                "key": "banner-design",
                "form_value": "Banner design",
                "title": "Banner Design",
                "icon": "🖼️",
                "fee": "₹499",
                "fee_unit": "per banner, starting price",
                "desc": "Custom-designed banners for your website, storefront or social media.",
            },
            {
                "key": "promo-images",
                "form_value": "Promotional images",
                "title": "Promotional Images",
                "icon": "🎨",
                "fee": "₹399",
                "fee_unit": "per image set, starting price",
                "desc": "Product/promotional images designed for social media and ads.",
            },
            {
                "key": "article-writing",
                "form_value": "Article and content writing",
                "title": "Article & Content Writing",
                "icon": "📝",
                "fee": "₹599",
                "fee_unit": "per article, starting price",
                "desc": "Written articles and marketing copy to promote your product or brand.",
            },
            {
                "key": "reels-promotion",
                "form_value": "Reels and short video promotion",
                "title": "Reels & Short Video Promotion",
                "icon": "🎬",
                "fee": "₹1,499",
                "fee_unit": "per reel, starting price",
                "desc": "Short-form video/reel content edited for Instagram, YouTube Shorts and similar platforms.",
            },
        ],
    },
    "website-designer": {
        "slug": "website-designer",
        "icon": "💻",
        "no": "03",
        "title": "Website Designer",
        "short": "End-to-end website design, development and deployment for your product, plus ongoing maintenance.",
        "fee_range": "₹499 – ₹4,999",
        "summary": (
            "JIMMIND AI designs and builds a website for your product from scratch — "
            "covering design, development and deployment — at a nominal one-time "
            "charge, with an optional low-cost monthly plan to keep it maintained and "
            "up to date afterward."
        ),
        "who_for": "Businesses or individuals who need a website built for their product/brand and want it deployed and kept running without managing it themselves.",
        "assistance": [
            "Understanding your product and what the website needs to do",
            "Designing the website layout and structure",
            "Building the website end-to-end",
            "Deploying the website so it's live and reachable",
            "Handing over access details and a short walkthrough",
            "Ongoing maintenance and updates, if you choose the maintenance plan",
        ],
        "documents": [
            "Business/product details and any existing branding (logo, colours)",
            "Content for the website (text, images) or a request to have it drafted",
            "Domain name, if you already own one",
            "A valid mobile number/email for coordination",
        ],
        "request_types_intro": "Website Designer covers two request types — a one-time build, and ongoing maintenance for a site already built with us.",
        "fee_disclaimer": (
            "Development fees are starting prices and vary with the number of pages "
            "and features requested — your consultant will confirm the exact quote "
            "before work begins. Domain and hosting charges, if applicable, are separate "
            "from JIMMIND AI's service fee."
        ),
        "request_types": [
            {
                "key": "website-development",
                "form_value": "Website development and deployment",
                "title": "Website Development & Deployment",
                "icon": "🚀",
                "fee": "₹4,999",
                "fee_unit": "onwards, one-time, scope-based",
                "desc": "End-to-end design, development and deployment of a new website from scratch.",
            },
            {
                "key": "website-maintenance",
                "form_value": "Website maintenance",
                "title": "Website Maintenance",
                "icon": "🛠",
                "fee": "₹499",
                "fee_unit": "per month",
                "desc": "Ongoing updates, fixes and upkeep for a website already built with JIMMIND AI.",
            },
        ],
    },
}

# Flat lookup of every request type across every service, keyed by "key" —
# used to populate the inquiry form's "Request type" select and to preselect
# it from a query string (?type=new-voter-card), regardless of which service
# a request type happens to belong to.
REQUEST_TYPES = {
    rt["key"]: rt for s in SERVICES.values() for rt in s["request_types"]
}

# No tools are available yet. Leave this empty; the "Tools" nav link and
# /tools page already handle the empty state gracefully. Add entries here
# (matching the same shape used previously) once a tool is ready to ship.
TOOLS = {}


@app.context_processor
def inject_globals():
    """Make the services/tools/request-type catalogue available to every template (navbar, footer, forms)."""
    return {
        "nav_services": SERVICES,
        "nav_tools": TOOLS,
        "nav_request_types": REQUEST_TYPES,
    }


# ---------------------------------------------------------------------------
# Public pages
# ---------------------------------------------------------------------------
@app.get("/")
def home():
    return render_template("home.html", page="home")


@app.get("/home")
def home_redirect():
    # Kept for backward compatibility with the previous single-page build.
    return redirect(url_for("home"), code=301)


@app.get("/services")
def services_list():
    # With a single service, skip the listing page and go straight to it.
    # If a second service is ever added, this automatically shows the list.
    if len(SERVICES) == 1:
        only_slug = next(iter(SERVICES))
        return redirect(url_for("service_detail", slug=only_slug))
    return render_template("services/list.html", page="services", services=SERVICES)


@app.get("/services/<slug>")
def service_detail(slug):
    service = SERVICES.get(slug)
    if not service:
        abort(404)
    return render_template("services/detail.html", page="services", service=service)


@app.get("/tools")
def tools_list():
    return render_template("tools/list.html", page="tools", tools=TOOLS)


@app.get("/tools/<slug>")
def tool_detail(slug):
    tool = TOOLS.get(slug)
    if not tool:
        abort(404)
    return render_template("tools/detail.html", page="tools", tool=tool)


@app.get("/process")
def process_page():
    return render_template("process.html", page="process")


@app.get("/fees")
def fees_page():
    return render_template("fees.html", page="fees", services=SERVICES, request_types=REQUEST_TYPES)


@app.get("/contact")
def contact_page():
    type_key = request.args.get("type", "").strip()
    preselect = REQUEST_TYPES.get(type_key)
    return render_template("contact.html", page="contact", services=SERVICES, preselect=preselect)


@app.get("/login")
def login_page():
    return render_template("login.html", page="login")


@app.get("/payment")
def payment_page():
    type_key = request.args.get("type", "").strip()
    selected = REQUEST_TYPES.get(type_key)
    return render_template("payment.html", page="payment", services=SERVICES, request_types=REQUEST_TYPES, selected=selected)


# ---------------------------------------------------------------------------
# Admin
# ---------------------------------------------------------------------------
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
    if gate:
        return gate
    q = request.args.get("q", "").strip()
    service = request.args.get("service", "").strip()

    try:
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
    except PyMongoError:
        app.logger.exception("MongoDB read error on /admin")
        return render_template(
            "admin.html",
            db_error=(
                "Could not load data from the database. Check that MONGO_URI and "
                "MONGO_DB_NAME are set correctly in this environment's variables "
                "(Vercel: Project → Settings → Environment Variables) and that this "
                "server's IP/region is allowed to connect to your MongoDB cluster "
                "(Atlas: Network Access → IP Access List)."
            ),
            inquiries=[], total=0, clients=0, services=[], q=q, selected_service=service,
        )

    return render_template("admin.html", db_error=None, inquiries=rows, total=total, clients=clients, services=services, q=q, selected_service=service)


@app.get("/admin/export.csv")
def admin_export():
    gate = require_admin()
    if gate:
        return gate
    q = request.args.get("q", "").strip()
    service = request.args.get("service", "").strip()

    try:
        query = _build_inquiry_query(q, service)
        cursor = list(service_inquiries_col.find(query).sort("created_at", -1))
    except PyMongoError:
        app.logger.exception("MongoDB read error on /admin/export.csv")
        return Response("Database unavailable — could not export.", status=503, mimetype="text/plain")

    out = io.StringIO()
    writer = csv.writer(out)
    writer.writerow(["ID", "Name", "Mobile", "City", "Service", "Language", "Created At (UTC)"])
    for doc in cursor:
        r = _serialize_inquiry(doc)
        writer.writerow([r["id"], r["name"], r["mobile"], r["city"], r["service"], r["language"], r["created_at"]])
    return Response("\ufeff" + out.getvalue(), mimetype="text/csv", headers={"Content-Disposition": "attachment; filename=jimmind_service_inquiries.csv"})


# ---------------------------------------------------------------------------
# API
# ---------------------------------------------------------------------------
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


@app.errorhandler(404)
def not_found(_err):
    return render_template("404.html", page=""), 404


if __name__ == "__main__":
    port = int(os.getenv("PORT", "5000"))
    debug = os.getenv("FLASK_DEBUG", "0") == "1"
    app.run(host="0.0.0.0", port=port, debug=debug)