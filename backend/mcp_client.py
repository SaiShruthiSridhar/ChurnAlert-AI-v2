import os
import requests
import json
import hashlib
import base64
import secrets
import datetime
from dotenv import load_dotenv

load_dotenv()

HUBSPOT_CLIENT_ID = os.getenv("HUBSPOT_CLIENT_ID", "b26bba85-9cc1-4be1-ab45-83853b1c91d8")
HUBSPOT_CLIENT_SECRET = os.getenv("HUBSPOT_CLIENT_SECRET", "612727fc-191f-42dc-a14d-f0f40ed7c436")
HUBSPOT_REDIRECT_URI = os.getenv("HUBSPOT_REDIRECT_URI", "http://localhost:5000/hubspot/callback")
HUBSPOT_TOKEN_URL = os.getenv("HUBSPOT_TOKEN_ENDPOINT", "https://mcp.hubspot.com/oauth/v3/token")
HUBSPOT_AUTH_ENDPOINT = os.getenv("HUBSPOT_AUTH_ENDPOINT", "https://mcp-na2.hubspot.com/oauth/authorize/user")
HUBSPOT_MCP_SERVER_URL = os.getenv("HUBSPOT_MCP_SERVER_URL", "https://mcp.hubspot.com/")
HUBSPOT_BASE_URL = os.getenv("HUBSPOT_BASE_URL", "https://api.hubapi.com")

# Global storage for PKCE code_verifier (used between /connect and /callback)
_pkce_code_verifier = None

# Permanent In-Memory Cache
_companies_cache = None
_tickets_cache = {}
_connection_status = None




def generate_pkce_pair():
    """Generates a PKCE code_verifier and code_challenge pair."""
    global _pkce_code_verifier
    code_verifier = secrets.token_urlsafe(64)
    _pkce_code_verifier = code_verifier
    code_challenge = base64.urlsafe_b64encode(
        hashlib.sha256(code_verifier.encode()).digest()
    ).rstrip(b'=').decode()
    return code_verifier, code_challenge


def get_pkce_verifier():
    """Returns the stored code_verifier for use in token exchange."""
    return _pkce_code_verifier


def get_access_token():
    """Retrieve access token from database, falling back to env var."""
    try:
        from database import SessionLocal
        from models import HubSpotToken
        session = SessionLocal()
        record = session.query(HubSpotToken).order_by(HubSpotToken.updated_at.desc()).first()
        session.close()
        if record and record.access_token:
            return record.access_token
    except Exception as e:
        print(f"[HubSpot] DB token read error: {e}")
    return os.getenv("HUBSPOT_ACCESS_TOKEN", "")


def get_refresh_token():
    """Retrieve refresh token from database, falling back to env var."""
    try:
        from database import SessionLocal
        from models import HubSpotToken
        session = SessionLocal()
        record = session.query(HubSpotToken).order_by(HubSpotToken.updated_at.desc()).first()
        session.close()
        if record and record.refresh_token:
            return record.refresh_token
    except Exception as e:
        print(f"[HubSpot] DB refresh token read error: {e}")
    return os.getenv("HUBSPOT_REFRESH_TOKEN", "")


def save_tokens(access_token, refresh_token):
    """Save tokens to database so they persist across restarts."""
    os.environ["HUBSPOT_ACCESS_TOKEN"] = access_token
    os.environ["HUBSPOT_REFRESH_TOKEN"] = refresh_token or ""
    try:
        from database import SessionLocal
        from models import HubSpotToken
        session = SessionLocal()
        record = session.query(HubSpotToken).first()
        if record:
            record.access_token = access_token
            record.refresh_token = refresh_token or ""
            record.updated_at = datetime.datetime.utcnow()
        else:
            record = HubSpotToken(
                access_token=access_token,
                refresh_token=refresh_token or "",
                updated_at=datetime.datetime.utcnow()
            )
            session.add(record)
        session.commit()
        session.close()
        print("[HubSpot] Tokens saved to database.")
    except Exception as e:
        print(f"[HubSpot] Could not save tokens to database: {e}")


def get_oauth_url():
    code_verifier, code_challenge = generate_pkce_pair()
    auth_base = HUBSPOT_AUTH_ENDPOINT or "https://mcp.hubspot.com/oauth/authorize/user"
    if "mcp" in auth_base:
        url = (
            f"{auth_base}"
            f"?client_id={HUBSPOT_CLIENT_ID}"
            f"&redirect_uri={HUBSPOT_REDIRECT_URI}"
            f"&response_type=code"
            f"&code_challenge={code_challenge}"
            f"&code_challenge_method=S256"
        )
    else:
        scopes = (
            "crm.objects.companies.read "
            "crm.objects.companies.write "
            "crm.objects.contacts.read "
            "crm.objects.deals.read "
            "crm.objects.notes.write "
            "tickets"
        )
        url = (
            f"{auth_base}"
            f"?client_id={HUBSPOT_CLIENT_ID}"
            f"&redirect_uri={HUBSPOT_REDIRECT_URI}"
            f"&scope={scopes.replace(' ', '%20')}"
            f"&code_challenge={code_challenge}"
            f"&code_challenge_method=S256"
        )
    return url


def exchange_code_for_tokens(code):
    try:
        code_verifier = get_pkce_verifier()
        if not code_verifier:
            print("[HubSpot] No PKCE code_verifier found. Please restart OAuth flow.")
            return False, None

        payload = {
            "grant_type": "authorization_code",
            "client_id": HUBSPOT_CLIENT_ID,
            "client_secret": HUBSPOT_CLIENT_SECRET,
            "redirect_uri": HUBSPOT_REDIRECT_URI,
            "code": code,
            "code_verifier": code_verifier
        }
        # Prioritize MCP token endpoint, then standard API endpoints
        token_urls = [
            HUBSPOT_TOKEN_URL,
            "https://mcp.hubspot.com/oauth/v3/token",
            "https://api.hubapi.com/oauth/v1/token"
        ]
        token_urls = list(dict.fromkeys(token_urls))
        for token_url in token_urls:
            try:
                response = requests.post(token_url, data=payload, timeout=15)
                data = response.json()
                if "access_token" in data:
                    save_tokens(data["access_token"], data.get("refresh_token", ""))
                    print(f"[HubSpot] OAuth tokens obtained successfully via {token_url}")
                    return True, data["access_token"]
                else:
                    print(f"[HubSpot] Token exchange failed at {token_url}: {data}")
            except Exception as e:
                print(f"[HubSpot] Token exchange error at {token_url}: {e}")
        return False, None
    except Exception as e:
        print(f"[HubSpot] Token exchange error: {e}")
        return False, None


def refresh_access_token():
    refresh_token = get_refresh_token()
    if not refresh_token:
        print("[HubSpot] No refresh token available.")
        return False
    token_urls = [
        HUBSPOT_TOKEN_URL,
        "https://mcp.hubspot.com/oauth/v3/token",
        "https://api.hubapi.com/oauth/v1/token"
    ]
    token_urls = list(dict.fromkeys(token_urls))
    for url in token_urls:
        try:
            response = requests.post(url, data={
                "grant_type": "refresh_token",
                "client_id": HUBSPOT_CLIENT_ID,
                "client_secret": HUBSPOT_CLIENT_SECRET,
                "refresh_token": refresh_token
            }, timeout=15)
            data = response.json()
            if "access_token" in data:
                save_tokens(data["access_token"], data.get("refresh_token", refresh_token))
                print(f"[HubSpot] Access token refreshed successfully via {url}.")
                return True
            else:
                print(f"[HubSpot] Token refresh failed at {url}: {data}")
        except Exception as e:
            print(f"[HubSpot] Token refresh error at {url}: {e}")
    return False


def _get_auth_headers():
    """Return Authorization headers with current access token. Auto-refreshes if needed."""
    token = get_access_token()
    return {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}


def _hubspot_get(path, params=None):
    """Make an authenticated GET request to HubSpot REST API. Auto-refreshes token on 401."""
    url = f"{HUBSPOT_BASE_URL}{path}"
    headers = _get_auth_headers()
    resp = requests.get(url, headers=headers, params=params, timeout=20)
    if resp.status_code == 401:
        print("[HubSpot] Token expired. Attempting refresh...")
        if refresh_access_token():
            headers = _get_auth_headers()
            resp = requests.get(url, headers=headers, params=params, timeout=20)
    return resp


def _hubspot_post(path, payload):
    """Make an authenticated POST request to HubSpot REST API. Auto-refreshes token on 401."""
    url = f"{HUBSPOT_BASE_URL}{path}"
    headers = _get_auth_headers()
    resp = requests.post(url, headers=headers, json=payload, timeout=20)
    if resp.status_code == 401:
        print("[HubSpot] Token expired. Attempting refresh...")
        if refresh_access_token():
            headers = _get_auth_headers()
            resp = requests.post(url, headers=headers, json=payload, timeout=20)
    return resp


def _load_fallback_companies():
    """Load local 30 HubSpot companies dataset as persistent fallback so startup never blocks."""
    possible_paths = [
        os.path.join(os.path.dirname(os.path.dirname(__file__)), 'hubspot_30_companies.csv'),
        os.path.join(os.path.dirname(__file__), 'hubspot_30_companies.csv'),
        'hubspot_30_companies.csv'
    ]
    csv_path = None
    for p in possible_paths:
        if os.path.exists(p):
            csv_path = p
            break
    if not csv_path:
        return []
    import csv
    companies = []
    try:
        with open(csv_path, mode='r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            for idx, row in enumerate(reader, 1):
                monthly = float(row.get('monthly_charges') or 0)
                companies.append({
                    "id": f"HS-{idx}",
                    "hubspot_id": str(idx),
                    "name": row.get("Company name", "Unknown"),
                    "domain": row.get("Domain name", ""),
                    "industry": row.get("Industry", ""),
                    "annual_revenue": float(row.get("Annual revenue") or 0),
                    "city": row.get("City", ""),
                    "country": row.get("Country", ""),
                    "description": row.get("Description", ""),
                    "last_modified": "",
                    "created_date": "",
                    "assigned_csm": row.get("assigned_csm", "Unassigned"),
                    "contract_type": row.get("contract_type", "Month-to-month"),
                    "tenure": int(float(row.get("tenure_months") or 0)),
                    "monthly_charges": monthly,
                    "contract_value": monthly * 12,
                    "feature_adoption_pct": float(row.get("feature_adoption_pct") or 0),
                    "login_frequency": int(float(row.get("login_frequency") or 0)),
                    "session_duration_avg": float(row.get("session_duration_avg") or 0),
                    "renewal_date": row.get("renewal_date", ""),
                    "last_login_date": row.get("last_login_date", ""),
                    "status": "Active",
                    "source": "hubspot"
                })
        print(f"[HubSpot] Loaded {len(companies)} companies from local dataset.")
    except Exception as e:
        print(f"[HubSpot] Fallback load error: {e}")
    return companies


def is_hubspot_connected(force_check=False):
    """Verify HubSpot connection by calling the token info endpoint (cached in memory)."""
    global _connection_status
    if not force_check and _connection_status is not None:
        return _connection_status

    token = get_access_token()
    if not token:
        _connection_status = False
        return False
    try:
        resp = requests.get(
            f"https://api.hubapi.com/oauth/v1/access-tokens/{token}",
            timeout=5
        )
        if resp.status_code == 200:
            print("[HubSpot] Connection verified via token info endpoint.")
            _connection_status = True
            return True
        # Token might be expired — try refreshing
        if resp.status_code == 401:
            print("[HubSpot] Token expired during connection check. Refreshing...")
            if refresh_access_token():
                new_token = get_access_token()
                resp2 = requests.get(
                    f"https://api.hubapi.com/oauth/v1/access-tokens/{new_token}",
                    timeout=5
                )
                _connection_status = (resp2.status_code == 200)
                return _connection_status
        print(f"[HubSpot] Connection check failed: {resp.status_code}")
        _connection_status = False
        return False
    except Exception as e:
        print(f"[HubSpot] Connection check error: {e}")
        _connection_status = False
        return False


def fetch_companies(force_refresh=False):
    """Fetch companies permanently into memory with fallback support."""
    global _companies_cache
    if not force_refresh and _companies_cache is not None:
        return _companies_cache

    if not is_hubspot_connected():
        if _companies_cache is None:
            _companies_cache = _load_fallback_companies()
        return _companies_cache

    print("[HubSpot] Fetching companies via HubSpot CRM REST API...")
    properties = [
        "name", "domain", "industry", "annualrevenue",
        "numberofemployees", "city", "country", "description",
        "hs_lastmodifieddate", "createdate",
        "assigned_csm", "contract_type", "tenure_months",
        "monthly_charges", "feature_adoption_pct", "login_frequency",
        "session_duration_avg", "renewal_date", "last_login_date",
        "renewal", "last_login"
    ]
    try:
        all_results = []
        after = None
        while True:
            params = {
                "properties": ",".join(properties),
                "limit": 100
            }
            if after:
                params["after"] = after

            resp = _hubspot_get("/crm/v3/objects/companies", params=params)
            if resp.status_code != 200:
                print(f"[HubSpot] Companies fetch failed: {resp.status_code} {resp.text[:200]}")
                if not _companies_cache:
                    _companies_cache = _load_fallback_companies()
                return _companies_cache

            data = resp.json()
            all_results.extend(data.get("results", []))

            paging = data.get("paging", {})
            next_page = paging.get("next", {})
            after = next_page.get("after")
            if not after:
                break

        companies = []
        for result in all_results:
            props = result.get("properties", {})
            cid = result.get("id", "unknown")
            renewal_val = props.get("renewal_date") or props.get("renewal") or ""
            last_login_val = props.get("last_login_date") or props.get("last_login") or ""
            monthly = float(props.get("monthly_charges") or 0)
            companies.append({
                "id": f"HS-{cid}",
                "hubspot_id": cid,
                "name": props.get("name", "Unknown"),
                "domain": props.get("domain", ""),
                "industry": props.get("industry", ""),
                "annual_revenue": float(props.get("annualrevenue") or 0),
                "city": props.get("city", ""),
                "country": props.get("country", ""),
                "description": props.get("description", ""),
                "last_modified": props.get("hs_lastmodifieddate", ""),
                "created_date": props.get("createdate", ""),
                "assigned_csm": props.get("assigned_csm", "Unassigned"),
                "contract_type": props.get("contract_type", "Month-to-month"),
                "tenure": int(float(props.get("tenure_months") or 0)),
                "monthly_charges": monthly,
                "contract_value": monthly * 12,
                "feature_adoption_pct": float(props.get("feature_adoption_pct") or 0),
                "login_frequency": int(float(props.get("login_frequency") or 0)),
                "session_duration_avg": float(props.get("session_duration_avg") or 0),
                "renewal_date": renewal_val,
                "last_login_date": last_login_val,
                "status": "Active",
                "source": "hubspot"
            })
        if companies:
            print(f"[HubSpot] Fetched {len(companies)} companies with full data.")
            _companies_cache = companies
        elif not _companies_cache:
            _companies_cache = _load_fallback_companies()
        return _companies_cache
    except Exception as e:
        print(f"[HubSpot] fetch_companies error: {e}")
        if not _companies_cache:
            _companies_cache = _load_fallback_companies()
        return _companies_cache


def warm_cache():
    """Permanent pre-load of all data on startup so UI renders with zero delay."""
    global _companies_cache, _connection_status
    print("[Startup] Pre-loading all HubSpot data into memory...")
    try:
        connected = is_hubspot_connected(force_check=True)
        if connected:
            companies = fetch_companies(force_refresh=True)
            print(f"[Startup] Pre-loaded {len(companies)} live HubSpot companies.")
        else:
            companies = fetch_companies()
            print(f"[Startup] Pre-loaded {len(companies)} companies into memory.")
        print("[Startup] All data ready in memory. Zero-delay rendering active.")
        return True
    except Exception as e:
        print(f"[Startup] Cache warming error: {e}")
        return False


def fetch_company_details(hubspot_company_id):
    """Fetch a single company's details from HubSpot CRM REST API."""
    print(f"[HubSpot] Fetching details for company {hubspot_company_id}...")
    properties = [
        "name", "domain", "industry", "annualrevenue",
        "numberofemployees", "city", "country", "description",
        "hs_lastmodifieddate", "createdate", "notes_last_contacted",
        "closedate", "hs_num_open_deals",
        "assigned_csm", "contract_type", "tenure_months",
        "monthly_charges", "feature_adoption_pct", "login_frequency",
        "session_duration_avg", "renewal_date", "last_login_date",
        "renewal", "last_login"
    ]
    try:
        resp = _hubspot_get(
            f"/crm/v3/objects/companies/{hubspot_company_id}",
            params={"properties": ",".join(properties)}
        )
        if resp.status_code != 200:
            print(f"[HubSpot] Company details fetch failed: {resp.status_code}")
            return None
        data = resp.json()
        props = data.get("properties", {})
        renewal_val = props.get("renewal_date") or props.get("renewal") or ""
        last_login_val = props.get("last_login_date") or props.get("last_login") or ""
        monthly = float(props.get("monthly_charges") or 0)
        return {
            "id": f"HS-{hubspot_company_id}",
            "hubspot_id": hubspot_company_id,
            "name": props.get("name", "Unknown"),
            "domain": props.get("domain", ""),
            "industry": props.get("industry", ""),
            "annual_revenue": float(props.get("annualrevenue") or 0),
            "city": props.get("city", ""),
            "country": props.get("country", ""),
            "description": props.get("description", ""),
            "last_contacted": props.get("notes_last_contacted", ""),
            "close_date": props.get("closedate", ""),
            "open_deals": props.get("hs_num_open_deals", 0),
            "assigned_csm": props.get("assigned_csm", "Unassigned"),
            "contract_type": props.get("contract_type", "Month-to-month"),
            "tenure": int(float(props.get("tenure_months") or 0)),
            "monthly_charges": monthly,
            "contract_value": monthly * 12,
            "renewal_date": renewal_val,
            "last_login_date": last_login_val
        }
    except Exception as e:
        print(f"[HubSpot] fetch_company_details error: {e}")
        return None


def find_company_by_name(company_name):
    """Search HubSpot for a company by name using the CRM search API."""
    try:
        payload = {
            "filterGroups": [{
                "filters": [{
                    "propertyName": "name",
                    "operator": "CONTAINS_TOKEN",
                    "value": company_name
                }]
            }],
            "properties": ["name", "domain"],
            "limit": 5
        }
        resp = _hubspot_post("/crm/v3/objects/companies/search", payload)
        if resp.status_code != 200:
            print(f"[HubSpot] Company search failed: {resp.status_code}")
            return None
        data = resp.json()
        results = data.get("results", [])
        if results:
            return results[0].get("id")
        return None
    except Exception as e:
        print(f"[HubSpot] find_company_by_name error: {e}")
        return None


def create_hubspot_note(company_id, note_body, csm_name="ChurnAlert AI"):
    """Create a note on a HubSpot company record and associate it."""
    try:
        # Step 1: Create the note engagement
        note_payload = {
            "properties": {
                "hs_note_body": f"[ChurnAlert AI Outreach — Approved by {csm_name}]\n\n{note_body}",
                "hs_timestamp": str(int(datetime.datetime.utcnow().timestamp() * 1000))
            }
        }
        resp = _hubspot_post("/crm/v3/objects/notes", note_payload)
        if resp.status_code not in (200, 201):
            print(f"[HubSpot] Note creation failed: {resp.status_code} {resp.text[:200]}")
            return False

        note_id = resp.json().get("id")
        if not note_id:
            print("[HubSpot] Note created but no ID returned.")
            return False

        # Step 2: Associate note with the company
        assoc_payload = {
            "inputs": [{
                "from": {"id": note_id},
                "to": {"id": str(company_id)},
                "type": "note_to_company"
            }]
        }
        assoc_resp = _hubspot_post("/crm/v3/associations/notes/companies/batch/create", assoc_payload)
        if assoc_resp.status_code in (200, 201, 207):
            print(f"[HubSpot] Note created and associated with company {company_id}.")
            return True
        else:
            print(f"[HubSpot] Note created but association failed: {assoc_resp.status_code}")
            return True  # Note was still created even if association had issues
    except Exception as e:
        print(f"[HubSpot] create_hubspot_note error: {e}")
        return False


def fetch_company_tickets(hubspot_company_id):
    """Fetch support tickets associated with a company via HubSpot CRM REST API (cached in memory)."""
    global _tickets_cache
    if hubspot_company_id in _tickets_cache:
        return _tickets_cache[hubspot_company_id]

    if not is_hubspot_connected():
        _tickets_cache[hubspot_company_id] = []
        return []

    try:
        # Search tickets associated with this company
        payload = {
            "filterGroups": [],
            "properties": ["subject", "hs_ticket_priority", "hs_pipeline_stage", "createdate"],
            "limit": 10
        }
        # Use associations endpoint to get tickets for this company
        resp = _hubspot_get(
            f"/crm/v3/objects/companies/{hubspot_company_id}/associations/tickets"
        )
        if resp.status_code != 200:
            _tickets_cache[hubspot_company_id] = []
            return []

        ticket_ids = [item.get("id") for item in resp.json().get("results", [])]
        if not ticket_ids:
            _tickets_cache[hubspot_company_id] = []
            return []

        tickets = []
        for ticket_id in ticket_ids[:10]:
            t_resp = _hubspot_get(
                f"/crm/v3/objects/tickets/{ticket_id}",
                params={"properties": "subject,hs_ticket_priority,hs_pipeline_stage,createdate"}
            )
            if t_resp.status_code == 200:
                props = t_resp.json().get("properties", {})
                subject = props.get("subject", "Support ticket")
                priority = props.get("hs_ticket_priority", "MEDIUM")
                stage = props.get("hs_pipeline_stage", "1")
                sentiment = "negative" if priority == "HIGH" else "neutral"
                is_resolved = stage in ["4", "closed"]
                createdate = props.get("createdate") or datetime.datetime.utcnow().isoformat() + "Z"
                tickets.append({
                    "subject": subject,
                    "sentiment": sentiment,
                    "is_resolved": is_resolved,
                    "created_at": createdate
                })

        print(f"[HubSpot] Fetched {len(tickets)} tickets for company {hubspot_company_id}.")
        _tickets_cache[hubspot_company_id] = tickets
        return tickets
    except Exception as e:
        print(f"[HubSpot] fetch_company_tickets error: {e}")
        _tickets_cache[hubspot_company_id] = []
        return []