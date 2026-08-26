# JIMMIND AI — Online Voter Services Consultancy

A production-oriented Flask + SQLite website for JIMMIND AI's Phase 1 voter-service consultancy.

## Included

- Responsive premium website in English + Hindi.
- Hero, service cards, process, fees, client/team feedback section, contact/inquiry form.
- 3D CSS card effects, animated background grid, parallax-style motion and micro-interactions.
- SQLite database initialized automatically on first application start.
- Inquiry and client tables.
- OpenAI-powered chatbot restricted to `knowledge_base.md`.
- No RAG, vector database, semantic search, web search, external retrieval, or external government API.
- `.env.example` for secure API-key configuration.
- Gunicorn command for production deployment.
- Web-sourced voter imagery with attribution/source information in `IMAGE_SOURCES.md`.

## Requirements

- Python 3.10+
- An OpenAI API key for chatbot functionality.

## Local setup

### Windows PowerShell

```powershell
python -m venv .venv
.\\.venv\\Scripts\\Activate.ps1
pip install -r requirements.txt
Copy-Item .env.example .env
notepad .env
python app.py
```

### macOS/Linux

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
nano .env
python app.py
```

Open `http://127.0.0.1:5000`.

The SQLite file `jimmind.db` is created automatically.

## OpenAI chatbot

The backend uses the OpenAI Responses API and injects the complete contents of `knowledge_base.md` into the `instructions` prompt on every chatbot request. The user's message is then sent as the request input.

The relevant flow in `app.py` is:

1. `load_knowledge()` reads `knowledge_base.md`.
2. `system_prompt` embeds the document between `BEGIN KNOWLEDGE` and `END KNOWLEDGE`.
3. `client.responses.create(...)` sends the strict scope instructions plus the user's question.
4. `response.output_text` is returned to the browser.

The chatbot is deliberately not given any web-search or file-search tools. Its application prompt also instructs it not to use information outside the knowledge document.

## Changing the chatbot's knowledge

Edit only `knowledge_base.md` when changing services, eligibility guidance, process steps or consultation fees.

Because the document is read for each request, a server restart is not required for a content-only change in normal deployments.

## Security notes

- Never commit `.env`.
- Never put `OPENAI_API_KEY` in frontend JavaScript.
- Run behind HTTPS in production.
- Add authentication/role-based access before exposing administrative inquiry records.
- Add rate limiting and CSRF protection if the deployment becomes public/high-volume.
- The supplied Flask app intentionally has no admin dashboard, reducing the initial attack surface.

## Production start

```bash
gunicorn --bind 0.0.0.0:8000 app:app
```

Set environment variables through your hosting platform rather than committing `.env`.

## Database

`service_inquiries` stores:
- name
- mobile
- city
- service
- language
- created_at

`clients` stores:
- name
- mobile
- city
- created_at
- updated_at

The mobile number is unique in `clients` so repeat inquiries update the basic client record rather than creating duplicate client profiles.

## Important business/legal positioning

The website explicitly describes JIMMIND AI as a private consultancy/service-assistance provider and not as the Election Commission of India. Keep that distinction in all production copy and advertising.

## Image sourcing

See `IMAGE_SOURCES.md`. The site uses web-sourced voter imagery rather than generated placeholder graphics. CSS-generated 3D elements are used for decoration, so there are no missing local image assets.
