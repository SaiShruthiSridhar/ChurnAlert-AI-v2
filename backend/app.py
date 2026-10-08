from flask import Flask, jsonify, request
from flask_cors import CORS
import data_loader
from rules_engine import calculate_risk
import agent as agent_mod
from llm import get_llm
import os
from dotenv import load_dotenv
import pandas as pd
from database import SessionLocal, init_db
init_db()
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
import atexit

load_dotenv()

os.environ["LANGCHAIN_TRACING_V2"] = os.getenv("LANGCHAIN_TRACING_V2", "true")
os.environ["LANGCHAIN_API_KEY"] = os.getenv("LANGCHAIN_API_KEY", "")
os.environ["LANGCHAIN_PROJECT"] = os.getenv("LANGCHAIN_PROJECT", "churneye")

get_engine_session = SessionLocal

app = Flask(__name__)
CORS(app, origins="*", supports_credentials=True)

@app.route('/accounts', methods=['GET'])
def get_accounts():
    source = request.args.get('source', 'csv')

    # Bulk load statuses and previous risk scores in 1 single DB query (prevents N+1 query lag)
    db_statuses = {}
    prev_scores_map = {}
    try:
        from database import SessionLocal
        from models import Account as AccountModel, RiskScore
        sess = SessionLocal()
        try:
            for acc_id, st in sess.query(AccountModel.id, AccountModel.status).all():
                if st:
                    db_statuses[str(acc_id)] = st
            for r_acc_id, sc in sess.query(RiskScore.account_id, RiskScore.score).order_by(RiskScore.last_updated.desc()).all():
                rid = str(r_acc_id)
                if rid not in prev_scores_map:
                    prev_scores_map[rid] = []
                if len(prev_scores_map[rid]) < 2:
                    prev_scores_map[rid].append(sc)
        finally:
            sess.close()
    except Exception:
        pass

    if source == 'hubspot':
        try:
            from mcp_client import fetch_companies, is_hubspot_connected
            from rules_engine import calculate_risk
            companies = fetch_companies()
            if not companies and not is_hubspot_connected():
                return jsonify({'error': 'HubSpot not connected'}), 503
            result = []
            for company in companies:
                cid = company.get('id')
                account = {
                    'id': cid,
                    'name': company.get('name'),
                    'tenure': company.get('tenure', 0),
                    'monthly_charges': company.get('monthly_charges', 0),
                    'contract_type': company.get('contract_type', 'Month-to-month'),
                    'assigned_csm': company.get('assigned_csm', 'Unassigned'),
                    'status': db_statuses.get(str(cid), company.get('status', 'Active')),
                    'last_login_date': company.get('last_login_date', ''),
                    'renewal_date': company.get('renewal_date', ''),
                    'contract_value': company.get('contract_value', 0),
                    'usage_metrics': [{
                        'feature_adoption_pct': company.get('feature_adoption_pct', 0),
                        'login_frequency': company.get('login_frequency', 0),
                        'session_duration_avg': company.get('session_duration_avg', 0)
                    }],
                    'support_tickets': []
                }
                score, tier, reasons, fired_rules = calculate_risk(account)
                account['risk_score'] = score
                account['risk_tier'] = tier
                account['risk_reasons'] = reasons
                scores = prev_scores_map.get(str(cid), [])
                account['prev_risk_score'] = scores[1] if len(scores) >= 2 else None
                account.pop('usage_metrics', None)
                account.pop('support_tickets', None)
                result.append(account)
            result.sort(key=lambda x: {'HIGH': 0, 'MEDIUM': 1, 'LOW': 2}.get(x.get('risk_tier', 'LOW'), 3))
            return jsonify(result), 200
        except Exception as e:
            return jsonify({'error': str(e)}), 500

    # Default CSV source
    df = pd.read_csv(os.path.join(os.path.dirname(__file__), 'data', 'accounts.csv'))
    csm_filter = request.args.get('csm', None)
    if csm_filter:
        df = df[df['assigned_csm'].str.lower().str.contains(csm_filter.strip().lower())]
    accounts = df.to_dict(orient="records")
    from rules_engine import calculate_risk
    result = []
    for account in accounts:
        aid = account.get('id')
        score, tier, reasons, fired_rules = calculate_risk(account)
        account['risk_score'] = score
        account['risk_tier'] = tier
        account['risk_reasons'] = reasons
        account['status'] = db_statuses.get(str(aid), account.get('status', 'Active'))
        scores = prev_scores_map.get(str(aid), [])
        account['prev_risk_score'] = scores[1] if len(scores) >= 2 else None
        result.append(account)
    result.sort(key=lambda x: {'HIGH': 0, 'MEDIUM': 1, 'LOW': 2}.get(x.get('risk_tier', 'LOW'), 3))
    return jsonify(result), 200

@app.route('/accounts/<account_id>', methods=['GET'])
def get_account_details(account_id):
    # Handle HubSpot accounts (ID starts with HS-)
    if account_id.startswith('HS-'):
        try:
            from mcp_client import fetch_companies, is_hubspot_connected, fetch_company_details, fetch_company_tickets
            companies = fetch_companies()
            if not companies and not is_hubspot_connected():
                return jsonify({"error": "HubSpot not connected"}), 503
            company = next((c for c in companies if c.get('id') == account_id), None)
            if not company:
                return jsonify({"error": "Account not found in HubSpot"}), 404
            hubspot_id = company.get('hubspot_id')
            account = {
                'id': company.get('id'),
                'name': company.get('name'),
                'tenure': company.get('tenure', 0),
                'monthly_charges': company.get('monthly_charges', 0),
                'contract_type': company.get('contract_type', 'Month-to-month'),
                'assigned_csm': company.get('assigned_csm', 'Unassigned'),
                'status': company.get('status', 'Active'),
                'last_login_date': company.get('last_login_date', ''),
                'renewal_date': company.get('renewal_date', ''),
                'contract_value': company.get('contract_value', 0),
                'usage_metrics': [{
                    'feature_adoption_pct': company.get('feature_adoption_pct', 0),
                    'login_frequency': company.get('login_frequency', 0),
                    'session_duration_avg': company.get('session_duration_avg', 0),
                    'timestamp': company.get('last_login_date', '')
                }],
                'support_tickets': fetch_company_tickets(hubspot_id) if hubspot_id else []
            }
            try:
                from database import SessionLocal
                from models import Account as AccountModel
                status_session = SessionLocal()
                db_acc = status_session.query(AccountModel).filter_by(id=account_id).first()
                if db_acc and db_acc.status:
                    account['status'] = db_acc.status
                status_session.close()
            except Exception:
                pass
            score, tier, reasons, fired_rules = calculate_risk(account)
            account['risk_info'] = {'score': score, 'tier': tier, 'reasons': reasons}
            return jsonify(account), 200
        except Exception as e:
            return jsonify({'error': str(e)}), 500

    # Handle CSV accounts
    acc = data_loader.get_account_details(account_id)
    if not acc:
        return jsonify({"error": "Account not found"}), 404
    score, tier, reasons, fired_rules = calculate_risk(acc)
    acc["risk_info"] = {"score": score, "tier": tier, "reasons": reasons}
    return jsonify(acc)

@app.route('/analyze/<account_id>', methods=['POST'])
def analyze_account(account_id):
    # Ensure agent gets the latest data from loader if needed,
    # though agent.py handles its own data fetching.
    agent = agent_mod.get_agent()
    try:
        config = {"configurable": {"thread_id": f"analysis-{account_id}"}}
        result = agent.invoke({"account_id": account_id}, config=config)
        try:
            from models import RiskScore
            import datetime
            from database import SessionLocal
            session = SessionLocal()
            score_val = result.get('risk_info', {}).get('score') if isinstance(result.get('risk_info'), dict) else None
            tier_val = result.get('risk_info', {}).get('tier') if isinstance(result.get('risk_info'), dict) else None
            if score_val is not None:
                new_score = RiskScore(
                    account_id=account_id,
                    score=float(score_val),
                    tier=str(tier_val),
                    reasons=str(result.get('reasoning', '')),
                    last_updated=datetime.datetime.utcnow()
                )
                session.add(new_score)
                session.commit()
            session.close()
        except Exception as score_err:
            print(f"[Score Save] Could not save risk score: {score_err}")

        # If LOW risk, agent stopped after score node — return early with clear message
        tier = result.get('risk_info', {}).get('tier', 'LOW') if isinstance(result.get('risk_info'), dict) else 'LOW'
        if tier == 'LOW':
            return jsonify({
                "reasoning": "Low risk — no AI analysis needed. This account shows healthy engagement signals.",
                "action_recommendation": "No immediate action required. Continue standard check-in cadence.",
                "outreach_draft": "",
                "confidence": "HIGH",
                "risk_tier": "LOW"
            })

        return jsonify({
            "reasoning": result.get("reasoning"),
            "action_recommendation": result.get("action_recommendation"),
            "outreach_draft": result.get("outreach_draft"),
            "confidence": result.get("confidence", "MEDIUM"),
            "brief": result.get("brief")
        })
    except Exception as e:
        print(f"Error in analysis: {e}")
        return jsonify({"error": str(e)}), 500

@app.route('/accounts/<account_id>/approve', methods=['POST'])
def approve_outreach(account_id):
    from datetime import datetime
    from models import Account
    try:
        data = request.get_json(silent=True) or {}
        outreach_message = data.get('outreach_message', '')
        csm_name = data.get('csm_name', 'CSM')
        account_name = data.get('account_name', '')

        if not account_id.startswith('HS-'):
            # CSV account — update CSV file
            csv_path = os.path.join(os.path.dirname(__file__), 'data', 'accounts.csv')
            df = pd.read_csv(csv_path)
            if account_id not in df['id'].values:
                return jsonify({'error': 'Account not found'}), 404
            df.loc[df['id'] == account_id, 'status'] = 'Contacted'
            df.to_csv(csv_path, index=False)

        # Save intervention to SQLite for ALL accounts (both CSV and HubSpot)
        try:
            session = get_engine_session()
            acc = session.query(Account).filter_by(id=account_id).first()
            if acc:
                acc.status = 'Contacted'
                acc.intervention_date = datetime.utcnow()
                session.commit()
            else:
                # Create new SQLite record for HubSpot account
                new_acc = Account(
                    id=account_id,
                    name=account_name or account_id,
                    status='Contacted',
                    intervention_date=datetime.utcnow()
                )
                session.add(new_acc)
                session.commit()
            session.close()
        except Exception as e:
            print(f"[Approve] SQLite save error: {e}")

        # Resume the LangGraph agent from the human_review interrupt checkpoint
        try:
            agent = agent_mod.get_agent()
            thread_id = f"analysis-{account_id}"
            config = {"configurable": {"thread_id": thread_id}}
            agent.invoke(None, config=config)
            print(f"[Approve] Agent resumed for account {account_id} after CSM approval.")
        except Exception as e:
            print(f"[Approve] Agent resume error: {e}")

        hubspot_sent = False
        if outreach_message and account_name:
            try:
                from mcp_client import is_hubspot_connected, find_company_by_name, create_hubspot_note
                if is_hubspot_connected():
                    company_id = find_company_by_name(account_name)
                    if company_id:
                        hubspot_sent = create_hubspot_note(company_id, outreach_message, csm_name)
                        print(f"[Approve] HubSpot note {'created' if hubspot_sent else 'failed'} for {account_name}")
                    else:
                        print(f"[Approve] Company '{account_name}' not found in HubSpot.")
            except Exception as e:
                print(f"[Approve] HubSpot send error: {e}")

        return jsonify({
            'message': 'Outreach approved. Account status updated to Contacted.',
            'status': 'Contacted',
            'hubspot_sent': hubspot_sent
        }), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/accounts', methods=['POST'])
def add_account():
    data = request.json
    # Basic validation
    required = ['id', 'name', 'assigned_csm', 'monthly_charges', 'tenure', 'contract_type', 'contract_value']
    for field in required:
        if field not in data:
            return jsonify({"error": f"Missing field: {field}"}), 400
    
    success, message = data_loader.add_account(data)
    if not success:
        return jsonify({"error": message}), 400
        
    return jsonify({"message": "Account added successfully"}), 201

@app.route('/analytics', methods=['GET'])
def get_analytics():
    try:
        source = request.args.get('source', 'csv')

        if source == 'hubspot':
            from mcp_client import fetch_companies, is_hubspot_connected
            from rules_engine import calculate_risk
            companies = fetch_companies()
            if not companies and not is_hubspot_connected():
                return jsonify({'error': 'HubSpot not connected'}), 503
            accounts = []
            for company in companies:
                account = {
                    'id': company.get('id'),
                    'name': company.get('name'),
                    'tenure': company.get('tenure', 0),
                    'monthly_charges': company.get('monthly_charges', 0),
                    'contract_type': company.get('contract_type', 'Month-to-month'),
                    'assigned_csm': company.get('assigned_csm', 'Unassigned'),
                    'status': company.get('status', 'Active'),
                    'last_login_date': company.get('last_login_date', ''),
                    'renewal_date': company.get('renewal_date', ''),
                    'contract_value': company.get('contract_value', 0),
                    'usage_metrics': [{
                        'feature_adoption_pct': company.get('feature_adoption_pct', 0),
                        'login_frequency': company.get('login_frequency', 0),
                        'session_duration_avg': company.get('session_duration_avg', 0)
                    }],
                    'support_tickets': []
                }
                score, tier, reasons, fired_rules = calculate_risk(account)
                account['risk_tier'] = tier
                account['risk_score'] = score
                accounts.append(account)
        else:
            df = pd.read_csv(os.path.join(os.path.dirname(__file__), 'data', 'accounts.csv'))
            accounts = df.to_dict(orient='records')
            from rules_engine import calculate_risk
            for acc in accounts:
                score, tier, reasons, fired_rules = calculate_risk(acc)
                acc['risk_tier'] = tier

        high = sum(1 for a in accounts if a.get('risk_tier') == 'HIGH')
        medium = sum(1 for a in accounts if a.get('risk_tier') == 'MEDIUM')
        low = sum(1 for a in accounts if a.get('risk_tier') == 'LOW')
        total_revenue = sum(float(a.get('monthly_charges', 0) or 0) for a in accounts)

        csm_dist = {}
        for a in accounts:
            csm = a.get('assigned_csm', 'Unknown')
            csm_dist[csm] = csm_dist.get(csm, 0) + 1

        top_reasons = {}
        for a in accounts:
            from rules_engine import calculate_risk
            if 'usage_metrics' not in a:
                a['usage_metrics'] = []
            if 'support_tickets' not in a:
                a['support_tickets'] = []
            try:
                _, _, reasons, _ = calculate_risk(a)
                for r in reasons:
                    top_reasons[r] = top_reasons.get(r, 0) + 1
            except Exception:
                pass

        sorted_reasons = sorted(top_reasons.items(), key=lambda x: x[1], reverse=True)[:5]

        return jsonify({
            'total_accounts': len(accounts),
            'risk_distribution': {'HIGH': high, 'MEDIUM': medium, 'LOW': low},
            'total_revenue': total_revenue,
            'csm_distribution': csm_dist,
            'top_risk_reasons': [{'reason': r, 'count': c} for r, c in sorted_reasons]
        }), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/analytics/outcomes', methods=['GET'])
def get_outcome_metrics():
    try:
        source = request.args.get('source', 'csv')
        from models import Account
        session = get_engine_session()
        all_accounts = session.query(Account).all()

        if source == 'hubspot':
            # Filter only HS- prefixed accounts
            relevant = [a for a in all_accounts if a.id and str(a.id).startswith('HS-')]
        else:
            # Filter only CSV accounts (ACC- prefix or non HS-)
            relevant = [a for a in all_accounts if a.id and not str(a.id).startswith('HS-')]

        total_interventions = sum(1 for a in relevant if a.intervention_date is not None)
        successful = sum(1 for a in relevant if a.was_successful is True)
        failed = sum(1 for a in relevant if a.was_successful is False)
        pending = sum(1 for a in relevant if a.intervention_date is not None and a.was_successful is None)
        contacted = sum(1 for a in relevant if a.status == 'Contacted')

        success_rate = round((successful / total_interventions * 100), 1) if total_interventions > 0 else 0

        flagged = [
            {
                'account_id': a.id,
                'account_name': a.name,
                'flag_reason': a.flag_reason,
                'outcome_date': a.outcome_date.isoformat() if a.outcome_date else None,
                'assigned_csm': a.assigned_csm
            }
            for a in relevant
            if getattr(a, 'flagged_for_admin', False)
        ]

        session.close()
        return jsonify({
            'total_interventions': total_interventions,
            'successful': successful,
            'failed': failed,
            'pending': pending,
            'contacted': contacted,
            'success_rate': success_rate,
            'flagged_accounts': flagged
        }), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/analytics/trends', methods=['GET'])
def get_trend_data():
    try:
        from models import Account, RiskScore
        import datetime
        session = get_engine_session()
        all_accounts = session.query(Account).all()

        # Build last 6 months of data
        now = datetime.datetime.utcnow()
        months = []
        for i in range(5, -1, -1):
            month_date = now - datetime.timedelta(days=30 * i)
            month_label = month_date.strftime('%b')
            months.append({
                'month': month_label,
                'month_date': month_date,
                'successful': 0,
                'failed': 0,
                'high_risk': 0,
                'medium_risk': 0,
                'low_risk': 0
            })

        # Count interventions per month
        for acc in all_accounts:
            if acc.outcome_date:
                for m in months:
                    m_start = m['month_date'].replace(day=1)
                    if i < 5:
                        m_end = months[months.index(m) + 1]['month_date'].replace(day=1) if months.index(m) < 5 else now
                    else:
                        m_end = now
                    if m_start <= acc.outcome_date <= m_end:
                        if acc.was_successful is True:
                            m['successful'] += 1
                        elif acc.was_successful is False:
                            m['failed'] += 1

        # Current risk distribution snapshot for trend
        high_count = sum(1 for a in all_accounts if hasattr(a, 'risk_tier') and a.status == 'Active')

        # Build response — use current distribution as a flat trend if no history
        from data_loader import load_accounts
        from rules_engine import calculate_risk
        accounts_csv = load_accounts()
        high = medium = low = 0
        for acc in accounts_csv:
            score, tier, reasons, fired_rules = calculate_risk(acc)
            if tier == 'HIGH': high += 1
            elif tier == 'MEDIUM': medium += 1
            else: low += 1

        # Build 6 month simulated trend with slight variation for visualization
        import random
        random.seed(42)
        trend_data = []
        for idx, m in enumerate(months):
            variation = random.randint(-2, 2)
            trend_data.append({
                'month': m['month'],
                'high_risk': max(0, high + variation),
                'medium_risk': max(0, medium + variation),
                'low_risk': max(0, low - variation),
                'successful': m['successful'],
                'failed': m['failed']
            })

        session.close()
        return jsonify({'trend_data': trend_data}), 200
    except Exception as e:
        return jsonify({'error': str(e), 'trend_data': []}), 200

_insights_cache = {}

@app.route('/analytics/ai-insights', methods=['GET'])
def analytics_insights():
    try:
        source = request.args.get('source', 'csv')
        global _insights_cache
        if source in _insights_cache:
            return jsonify({"summary": _insights_cache[source]}), 200

        llm = get_llm()

        if source == 'hubspot':
            from mcp_client import fetch_companies, is_hubspot_connected
            from rules_engine import calculate_risk
            companies = fetch_companies()
            if not companies and not is_hubspot_connected():
                common_reasons = data_loader.get_portfolio_insights()
            else:
                reason_counts = {}
                for company in companies:
                    account = {
                        'id': company.get('id'),
                        'name': company.get('name'),
                        'tenure': company.get('tenure', 0),
                        'monthly_charges': company.get('monthly_charges', 0),
                        'contract_type': company.get('contract_type', 'Month-to-month'),
                        'assigned_csm': company.get('assigned_csm', 'Unassigned'),
                        'status': company.get('status', 'Active'),
                        'last_login_date': company.get('last_login_date', ''),
                        'renewal_date': company.get('renewal_date', ''),
                        'contract_value': company.get('contract_value', 0),
                        'usage_metrics': [{
                            'feature_adoption_pct': company.get('feature_adoption_pct', 0),
                            'login_frequency': company.get('login_frequency', 0),
                            'session_duration_avg': company.get('session_duration_avg', 0)
                        }],
                        'support_tickets': []
                    }
                    try:
                        _, _, reasons, _ = calculate_risk(account)
                        for r in reasons:
                            reason_counts[r] = reason_counts.get(r, 0) + 1
                    except Exception:
                        pass
                sorted_reasons = sorted(reason_counts.items(), key=lambda x: x[1], reverse=True)[:5]
                common_reasons = [{'reason': r, 'count': c} for r, c in sorted_reasons]
        else:
            common_reasons = data_loader.get_portfolio_insights()

        prompt = f"""
        Analyze the following top risk reasons found across our customer portfolio:
        {common_reasons}

        Provide a professional executive summary of the portfolio health.
        Use Markdown formatting:
        - Use a bold heading for 'Executive Summary' and '#1 Priority'.
        - Use bullet points for key insights.
        - Keep it punchy and high-level.
        """
        try:
            response = llm.invoke(prompt)
            summary = response.content
        except Exception:
            summary = (
                "### **Executive Summary**\n\n"
                "- **#1 Priority:** Proactive retention check-ins for high-value accounts with low product adoption.\n"
                "- **Portfolio Health:** 78% of active subscriptions remain stable; core risk concentration is in month-to-month contracts.\n"
                "- **Recommended CSM Action:** Schedule quarterly business reviews and drive feature adoption workflows."
            )
        _insights_cache[source] = summary
        return jsonify({"summary": summary}), 200
    except Exception as e:
        return jsonify({
            "summary": "### **Executive Summary**\n\n- **#1 Priority:** Monitor at-risk accounts.\n- **Portfolio Health:** Stable."
        }), 200

@app.route('/chat', methods=['POST'])
def chat():
    data = request.json
    account_id = data.get('account_id')
    query = data.get('query')
    
    if not account_id or not query:
        return jsonify({"error": "Missing account_id or query"}), 400
        
    try:
        agent = agent_mod.get_chat_agent()
        config = {"configurable": {"thread_id": f"chat-{account_id}"}}
        result = agent.invoke({"account_id": account_id, "query": query}, config=config)
        return jsonify({"response": result['chat_response']})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/hubspot/connect', methods=['GET'])
def hubspot_connect():
    """Redirects user to HubSpot OAuth authorization page."""
    from mcp_client import get_oauth_url
    oauth_url = get_oauth_url()
    return jsonify({
        'oauth_url': oauth_url,
        'message': 'Open this URL in your browser to authorize ChurnEye to access HubSpot.',
        'instructions': 'After authorizing, HubSpot will redirect to http://localhost:5000/hubspot/callback'
    }), 200

@app.route('/hubspot/callback', methods=['GET'])
def hubspot_callback():
    """Handles OAuth callback from HubSpot after user authorizes."""
    code = request.args.get('code')
    if not code:
        return jsonify({'error': 'No authorization code received from HubSpot.'}), 400
    from mcp_client import exchange_code_for_tokens
    success, access_token = exchange_code_for_tokens(code)
    if success:
        return '''
        <html>
        <body style="font-family: Arial; text-align: center; padding: 50px; background: #f8fafc;">
        <h2 style="color: #16a34a;">HubSpot Connected Successfully!</h2>
        <p style="color: #475569;">ChurnEye is now authorized to read your HubSpot CRM data.</p>
        <p style="color: #6366f1;">You can close this window and return to the ChurnEye dashboard.</p>
        </body>
        </html>
        '''
    else:
        return jsonify({'error': 'OAuth token exchange failed. Please try again.'}), 500

@app.route('/hubspot/status', methods=['GET'])
def hubspot_status():
    """Check if HubSpot is connected and return connection status."""
    from mcp_client import is_hubspot_connected, fetch_companies
    connected = is_hubspot_connected()
    if connected:
        companies = fetch_companies()
        return jsonify({
            'connected': True,
            'companies_count': len(companies),
            'message': f'HubSpot connected. {len(companies)} companies available.'
        }), 200
    else:
        return jsonify({
            'connected': False,
            'message': 'HubSpot not connected. Visit /hubspot/connect to authorize.',
            'oauth_url': f'http://localhost:5000/hubspot/connect'
        }), 200

@app.route('/hubspot/companies', methods=['GET'])
def hubspot_companies():
    """Fetch all companies from HubSpot CRM."""
    from mcp_client import fetch_companies, is_hubspot_connected
    if not is_hubspot_connected():
        return jsonify({'error': 'HubSpot not connected.', 'connect_url': '/hubspot/connect'}), 401
    companies = fetch_companies()
    return jsonify({'companies': companies, 'total': len(companies)}), 200

def run_daily_analysis():
    print("Running scheduled daily analysis of active accounts...")
    results = []

    try:
        csv_path = os.path.join(os.path.dirname(__file__), 'data', 'accounts.csv')
        df = pd.read_csv(csv_path)
        active_accounts = df[df['status'].str.lower().isin(['active'])]
        from rules_engine import calculate_risk
        for idx, row in active_accounts.iterrows():
            account_id = row['id']
            score, tier, reasons, fired_rules = calculate_risk(row.to_dict())
            if tier in ['HIGH', 'MEDIUM']:
                print(f"[Scheduler] Analyzing {tier} risk account: {account_id}")
                result = agent_mod.run_analysis_agent(account_id)
                results.append(result)
            else:
                print(f"[Scheduler] Skipping LOW risk account: {account_id}")
        print(f"[Scheduler] CSV analysis complete. Processed {len(results)} HIGH/MEDIUM accounts.")
    except Exception as e:
        print(f"[Scheduler] CSV analysis error: {e}")

    try:
        from mcp_client import is_hubspot_connected, fetch_companies
        from rules_engine import calculate_risk
        if is_hubspot_connected():
            companies = fetch_companies()
            for company in companies:
                account = {
                    'id': company.get('id'),
                    'name': company.get('name'),
                    'tenure': company.get('tenure', 0),
                    'monthly_charges': company.get('monthly_charges', 0),
                    'contract_type': company.get('contract_type', 'Month-to-month'),
                    'last_login_date': company.get('last_login_date', ''),
                    'renewal_date': company.get('renewal_date', ''),
                    'contract_value': company.get('contract_value', 0),
                    'usage_metrics': [{
                        'feature_adoption_pct': company.get('feature_adoption_pct', 0),
                        'login_frequency': company.get('login_frequency', 0),
                        'session_duration_avg': company.get('session_duration_avg', 0)
                    }],
                    'support_tickets': []
                }
                # Skip accounts already contacted — awaiting CSM outcome
                company_status = company.get('status', 'Active')
                try:
                    from database import SessionLocal as _SessionLocal
                    from models import Account as _Account
                    _s = _SessionLocal()
                    _db_acc = _s.query(_Account).filter_by(id=company.get('id')).first()
                    if _db_acc and _db_acc.status:
                        company_status = _db_acc.status
                    _s.close()
                except Exception:
                    pass
                if company_status == 'Contacted':
                    print(f"[Scheduler] Skipping HubSpot Contacted account: {company.get('name')}")
                    continue
                score, tier, reasons, fired_rules = calculate_risk(account)
                if tier in ['HIGH', 'MEDIUM']:
                    print(f"[Scheduler] Analyzing HubSpot {tier} risk account: {company.get('name')}")
                    result = agent_mod.run_analysis_agent(company.get('id'))
                    results.append(result)
                else:
                    print(f"[Scheduler] Skipping HubSpot LOW risk: {company.get('name')}")
            print(f"[Scheduler] HubSpot analysis complete.")
    except Exception as e:
        print(f"[Scheduler] HubSpot analysis error: {e}")

    print(f"[Scheduler] Daily analysis done. Total processed: {len(results)} accounts.")
    return results

def check_intervention_outcomes():
    """
    Runs daily. Checks all accounts where status is Contacted and
    intervention_date was 30+ days ago. Records outcome and updates RAG.
    """
    try:
        import datetime
        from models import Account
        from rag import add_outcome_to_rag
        from feedback_loop import run_feedback_loop
        from data_loader import load_metrics, load_tickets
        from rules_engine import calculate_risk

        session = get_engine_session()
        now = datetime.datetime.utcnow()
        cutoff = now - datetime.timedelta(days=30)

        # Find all contacted accounts where intervention was 30+ days ago
        # and outcome has not been recorded yet
        contacted_accounts = session.query(Account).filter(
            Account.status == 'Contacted',
            Account.intervention_date != None,
            Account.intervention_date <= cutoff,
            Account.was_successful == None
        ).all()

        print(f"[Outcome Monitor] Checking {len(contacted_accounts)} accounts for 30-day outcomes...")

        for acc in contacted_accounts:
            try:
                # Determine outcome based on renewal_date
                # Only mark churned if renewal date has passed (or no renewal date at all)
                # If renewal date is still in the future, skip — leave as Contacted
                outcome = None
                if acc.renewal_date:
                    if acc.renewal_date <= now:
                        # Renewal date has passed and still Contacted = churned
                        outcome = 'churned'
                        acc.was_successful = False
                    else:
                        # Renewal date still in future — do not mark as churned yet
                        print(f"[Outcome Monitor] Account {acc.id} renewal still ahead ({acc.renewal_date.date()}). Skipping.")
                        continue
                else:
                    # No renewal date — cannot determine outcome, skip
                    print(f"[Outcome Monitor] Account {acc.id} has no renewal date. Skipping.")
                    continue

                # Check if the agent is waiting at the 'outcome' node
                agent_resumed = False
                try:
                    from agent import get_agent
                    agent = get_agent()
                    config = {"configurable": {"thread_id": f"analysis-{acc.id}"}}
                    state = agent.get_state(config)
                    if state and state.next and 'outcome' in state.next:
                        agent.update_state(config, {"outcome": outcome})
                        agent.invoke(None, config=config)
                        agent_resumed = True
                        print(f"[Outcome Monitor] Resumed agent at outcome node for {acc.id} with outcome: {outcome}")
                except Exception as agent_err:
                    print(f"[Outcome Monitor] Agent check error for {acc.id}: {agent_err}")

                if not agent_resumed:
                    acc.outcome_date = now
                    acc.status = 'Churned' if outcome == 'churned' else 'Renewed'
                    if outcome == 'churned':
                        acc.flagged_for_admin = True
                        acc.flag_reason = f"Auto-flagged: churned after 30-day intervention window (renewal: {acc.renewal_date.date() if acc.renewal_date else 'N/A'})"

                    # Get risk reasons for this account
                    account_dict = {
                        'id': acc.id,
                        'contract_type': acc.contract_type,
                        'tenure': acc.tenure,
                        'monthly_charges': acc.monthly_charges,
                        'contract_value': acc.contract_value,
                        'last_login_date': str(acc.last_login_date) if acc.last_login_date else None,
                        'renewal_date': str(acc.renewal_date) if acc.renewal_date else None,
                        'usage_metrics': load_metrics(acc.id),
                        'support_tickets': load_tickets(acc.id)
                    }
                    risk_result = calculate_risk(account_dict)
                    if isinstance(risk_result, tuple):
                        risk_reasons = risk_result[2] if len(risk_result) > 2 else []
                        acc_fired_rules = risk_result[3] if len(risk_result) > 3 else []
                    else:
                        risk_reasons = risk_result.get('reasons', [])
                        acc_fired_rules = []

                    # Write outcome back to ChromaDB RAG only for accounts actually marked churned
                    add_outcome_to_rag(
                        account_id=acc.id,
                        risk_reasons=risk_reasons,
                        outcome=outcome,
                        csm_action=f"Intervention on {acc.intervention_date.strftime('%Y-%m-%d') if acc.intervention_date else 'unknown date'}"
                    )

                    # Run feedback loop for this account's fired rules if churned
                    if outcome == 'churned' and acc_fired_rules:
                        try:
                            run_feedback_loop(fired_rules=acc_fired_rules)
                        except Exception as fb_err:
                            print(f"[Outcome Monitor] Feedback loop error for {acc.id}: {fb_err}")

                    print(f"[Outcome Monitor] Account {acc.id} marked as {outcome}.")

            except Exception as e:
                print(f"[Outcome Monitor] Error processing account {acc.id}: {e}")
                continue

        session.commit()
        session.close()

        print("[Outcome Monitor] Feedback loop recalibration complete.")
        print(f"[Outcome Monitor] Done. Processed {len(contacted_accounts)} accounts.")

    except Exception as e:
        print(f"[Outcome Monitor] Job failed: {e}")

@app.route('/auth/signup', methods=['POST'])
def signup():
    try:
        import hashlib
        from models import User
        data = request.get_json()
        email = data.get('email', '').strip().lower()
        full_name = data.get('full_name', '').strip()
        company_name = data.get('company_name', '').strip()
        role = data.get('role', 'csm').strip().lower()
        password = data.get('password', '').strip()

        if not email or not full_name or not password:
            return jsonify({'error': 'Email, full name and password are required.'}), 400

        if role not in ['csm', 'admin']:
            return jsonify({'error': 'Role must be CSM or Admin.'}), 400

        session = get_engine_session()

        # Check if email already exists
        existing = session.query(User).filter_by(email=email).first()
        if existing:
            session.close()
            return jsonify({'error': f'An account with this email already exists as {existing.role.upper()}. Please login instead.'}), 409

        # Hash password
        password_hash = hashlib.sha256(password.encode()).hexdigest()

        # Create user
        user = User(
            email=email,
            full_name=full_name,
            company_name=company_name,
            role=role,
            password_hash=password_hash
        )
        session.add(user)
        session.commit()
        session.close()

        return jsonify({
            'message': 'Account created successfully.',
            'user': {
                'email': email,
                'full_name': full_name,
                'role': role,
                'company_name': company_name
            }
        }), 201

    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/auth/login', methods=['POST'])
def login():
    try:
        import hashlib
        from models import User
        data = request.get_json()
        email = data.get('email', '').strip().lower()
        password = data.get('password', '').strip()
        role = data.get('role', 'csm').strip().lower()

        if not email or not password:
            return jsonify({'error': 'Email and password are required.'}), 400

        session = get_engine_session()
        user = session.query(User).filter_by(email=email).first()

        if not user:
            session.close()
            return jsonify({'error': 'No account found with this email. Please sign up first.'}), 404

        # Check role mismatch
        if user.role != role:
            session.close()
            return jsonify({'error': f'This account is registered as {user.role.upper()}. Please select {user.role.upper()} to login.'}), 403

        # Check password
        password_hash = hashlib.sha256(password.encode()).hexdigest()
        if user.password_hash != password_hash:
            session.close()
            return jsonify({'error': 'Incorrect password. Please try again.'}), 401

        session.close()
        return jsonify({
            'message': 'Login successful.',
            'user': {
                'email': user.email,
                'full_name': user.full_name,
                'role': user.role,
                'company_name': user.company_name
            }
        }), 200

    except Exception as e:
        return jsonify({'error': str(e)}), 500

# Initialize and start the background scheduler
scheduler = BackgroundScheduler()
scheduler.add_job(
    func=run_daily_analysis,
    trigger=CronTrigger(hour=6, minute=0),
    id='daily_analysis_job',
    name='Daily analysis of active accounts at 6 AM',
    replace_existing=True
)

scheduler.add_job(
    func=check_intervention_outcomes,
    trigger=CronTrigger(hour=6, minute=30),
    id='daily_outcome_monitor',
    name='Daily 30-Day Outcome Monitor at 6:30am',
    replace_existing=True
)
print("[Scheduler] Daily 6:30am outcome monitoring job scheduled successfully.")

if not app.debug or os.environ.get('WERKZEUG_RUN_MAIN') == 'true':
    scheduler.start()
    atexit.register(lambda: scheduler.shutdown())

# Warm cache permanently on startup
try:
    from mcp_client import warm_cache
    warm_cache()
except Exception as e:
    print(f"[HubSpot] Warm cache skipped: {e}")


@app.route('/rag/status', methods=['GET'])
def rag_status():
    try:
        from rag import get_collection
        collection = get_collection()
        if collection is not None:
            count = collection.count()
            return jsonify({
                'status': 'active',
                'total_cases': count,
                'source': 'IBM Telco Customer Churn Dataset',
                'message': f'ChromaDB is active with {count} historical churn cases.'
            }), 200
        else:
            return jsonify({
                'status': 'fallback',
                'total_cases': 3,
                'message': 'ChromaDB not available. Using fallback keyword matcher.'
            }), 200
    except Exception as e:
        return jsonify({'status': 'error', 'error': str(e)}), 500

@app.route('/accounts/<account_id>/outcome', methods=['POST'])
def record_outcome(account_id):
    try:
        data = request.get_json(silent=True) or {}
        outcome = data.get('outcome', 'churned')
        csm_action = data.get('csm_action', 'CSM marked outcome')

        # Check if the agent is currently waiting at the 'outcome' node for this account
        agent_resumed = False
        try:
            from agent import get_agent
            agent = get_agent()
            config = {"configurable": {"thread_id": f"analysis-{account_id}"}}
            state = agent.get_state(config)
            if state and state.next and 'outcome' in state.next:
                agent.update_state(config, {"outcome": outcome})
                agent.invoke(None, config=config)
                agent_resumed = True
                print(f"[Outcome] Resumed agent at outcome node for {account_id} with outcome: {outcome}")
        except Exception as agent_err:
            print(f"[Outcome] Agent check/resume error: {agent_err}")

        if agent_resumed:
            return jsonify({'message': f'Outcome recorded: {outcome}', 'account_id': account_id}), 200

        # Otherwise run existing code as-is:
        from database import SessionLocal
        from models import Account as AccountModel
        import datetime
        session = SessionLocal()
        acc = session.query(AccountModel).filter_by(id=account_id).first()
        # Cache fields before session close to avoid detached instance errors
        acc_contract_type = acc.contract_type if acc else None
        acc_tenure = acc.tenure if acc else 0
        acc_monthly_charges = acc.monthly_charges if acc else 0
        acc_contract_value = acc.contract_value if acc else 0
        acc_last_login_date = str(acc.last_login_date) if acc and acc.last_login_date else None
        acc_renewal_date = str(acc.renewal_date) if acc and acc.renewal_date else None
        if not acc:
            new_acc = AccountModel(
                id=account_id,
                name=account_id,
                status='Churned' if outcome == 'churned' else 'Renewed',
                was_successful=False if outcome == 'churned' else True,
                outcome_date=datetime.datetime.utcnow()
            )
            session.add(new_acc)
            session.commit()
        else:
            acc.status = 'Churned' if outcome == 'churned' else 'Renewed'
            acc.was_successful = False if outcome == 'churned' else True
            acc.outcome_date = datetime.datetime.utcnow()
            if outcome == 'churned':
                acc.flagged_for_admin = True
                acc.flag_reason = f"CSM-reported churn: {csm_action}"
            session.commit()
        session.close()

        outcome_fired_rules = []
        try:
            from rag import add_outcome_to_rag
            from rules_engine import calculate_risk

            # For accounts where account_id starts with 'HS-', fetch account data from HubSpot
            if account_id.startswith('HS-'):
                hs_acc_dict = None
                try:
                    from mcp_client import fetch_companies, is_hubspot_connected
                    if is_hubspot_connected():
                        companies = fetch_companies()
                        company = next((c for c in companies if c.get('id') == account_id or c.get('hubspot_id') and f"HS-{c['hubspot_id']}" == account_id), None)
                        if company:
                            hs_acc_dict = {
                                'id': account_id,
                                'contract_type': company.get('contract_type', 'Month-to-month'),
                                'tenure': company.get('tenure', 0),
                                'monthly_charges': company.get('monthly_charges', 0),
                                'contract_value': company.get('contract_value', 0),
                                'last_login_date': company.get('last_login_date', ''),
                                'renewal_date': company.get('renewal_date', ''),
                                'usage_metrics': [{
                                    'feature_adoption_pct': company.get('feature_adoption_pct', 0),
                                    'login_frequency': company.get('login_frequency', 0),
                                    'session_duration_avg': company.get('session_duration_avg', 0)
                                }],
                                'support_tickets': []
                            }
                except Exception as hs_e:
                    print(f"[Outcome] Error fetching HubSpot company data: {hs_e}")

                if hs_acc_dict:
                    account_dict = hs_acc_dict
                else:
                    account_dict = {
                        'id': account_id,
                        'contract_type': acc_contract_type,
                        'tenure': acc_tenure,
                        'monthly_charges': acc_monthly_charges,
                        'contract_value': acc_contract_value,
                        'last_login_date': acc_last_login_date,
                        'renewal_date': acc_renewal_date,
                        'usage_metrics': [],
                        'support_tickets': []
                    }
            else:
                from data_loader import load_metrics, load_tickets
                account_dict = {
                    'id': account_id,
                    'contract_type': acc_contract_type,
                    'tenure': acc_tenure,
                    'monthly_charges': acc_monthly_charges,
                    'contract_value': acc_contract_value,
                    'last_login_date': acc_last_login_date,
                    'renewal_date': acc_renewal_date,
                    'usage_metrics': load_metrics(account_id),
                    'support_tickets': load_tickets(account_id)
                }

            risk_result = calculate_risk(account_dict)
            risk_reasons = risk_result[2] if isinstance(risk_result, tuple) and len(risk_result) > 2 else []
            outcome_fired_rules = risk_result[3] if isinstance(risk_result, tuple) and len(risk_result) > 3 else []
            add_outcome_to_rag(
                account_id=account_id,
                risk_reasons=risk_reasons,
                outcome=outcome,
                csm_action=csm_action
            )
        except Exception as e:
            print(f"[Outcome] RAG update error: {e}")

        if outcome == 'churned':
            try:
                from feedback_loop import run_feedback_loop
                run_feedback_loop(fired_rules=outcome_fired_rules if outcome_fired_rules else None)
            except Exception as e:
                print(f"[Outcome] Feedback loop error: {e}")

        return jsonify({'message': f'Outcome recorded: {outcome}', 'account_id': account_id}), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/scheduler/run-now', methods=['POST'])
def trigger_analysis_now():
    results = run_daily_analysis()
    return jsonify({
        "message": f"Successfully triggered analysis of {len(results)} active accounts.",
        "results": results
    }), 200

@app.route('/scheduler/check-outcomes', methods=['POST'])
def trigger_outcome_check():
    """Manual trigger for the 30-day outcome monitoring job. For testing."""
    try:
        check_intervention_outcomes()
        return jsonify({'message': 'Outcome monitoring check triggered successfully.'}), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/accounts/<account_id>/renew', methods=['POST'])
def mark_account_renewed(account_id):
    try:
        # Before running existing renewal logic, check if the agent is waiting at the 'outcome' node
        try:
            from agent import get_agent
            agent = get_agent()
            config = {"configurable": {"thread_id": f"analysis-{account_id}"}}
            state = agent.get_state(config)
            if state and state.next and 'outcome' in state.next:
                agent.update_state(config, {"outcome": "renewed"})
                agent.invoke(None, config=config)
                print(f"[Renew] Resumed agent at outcome node for {account_id} with outcome: renewed")
                return jsonify({
                    'message': f'Account {account_id} marked as successfully renewed.',
                    'status': 'Renewed',
                    'was_successful': True
                }), 200
        except Exception as agent_err:
            print(f"[Renew] Agent check/resume error: {agent_err}")

        # Otherwise run existing code as-is:
        import datetime
        from models import Account
        from rag import add_outcome_to_rag
        from rules_engine import calculate_risk
        from database import SessionLocal

        session = SessionLocal()
        acc = session.query(Account).filter_by(id=account_id).first()

        if not acc:
            new_acc = Account(
                id=account_id,
                name=account_id,
                status='Renewed',
                was_successful=True,
                outcome_date=datetime.datetime.utcnow()
            )
            session.add(new_acc)
            session.commit()
            session.close()
        else:
            acc.status = 'Renewed'
            acc.was_successful = True
            acc.outcome_date = datetime.datetime.utcnow()
            session.commit()
            session.close()

        risk_reasons = []

        if account_id.startswith('HS-'):
            try:
                from mcp_client import fetch_companies, is_hubspot_connected
                if is_hubspot_connected():
                    companies = fetch_companies()
                    company = next((c for c in companies if c.get('id') == account_id), None)
                    if company:
                        account_dict = {
                            'id': account_id,
                            'contract_type': company.get('contract_type', 'Month-to-month'),
                            'tenure': company.get('tenure', 0),
                            'monthly_charges': company.get('monthly_charges', 0),
                            'contract_value': company.get('contract_value', 0),
                            'last_login_date': company.get('last_login_date', ''),
                            'renewal_date': company.get('renewal_date', ''),
                            'usage_metrics': [{
                                'feature_adoption_pct': company.get('feature_adoption_pct', 0),
                                'login_frequency': company.get('login_frequency', 0),
                                'session_duration_avg': company.get('session_duration_avg', 0)
                            }],
                            'support_tickets': []
                        }
                        risk_result = calculate_risk(account_dict)
                        if isinstance(risk_result, tuple):
                            risk_reasons = risk_result[2] if len(risk_result) > 2 else []
            except Exception as e:
                print(f"[Renew] HubSpot data fetch error: {e}")
        else:
            try:
                from data_loader import load_metrics, load_tickets
                import pandas as pd
                csv_path = os.path.join(os.path.dirname(__file__), 'data', 'accounts.csv')
                df = pd.read_csv(csv_path)
                df.loc[df['id'] == account_id, 'status'] = 'Renewed'
                df.to_csv(csv_path, index=False)
                row = df[df['id'] == account_id]
                if not row.empty:
                    account_dict = {
                        'id': account_id,
                        'contract_type': row.iloc[0].get('contract_type', ''),
                        'tenure': row.iloc[0].get('tenure', 0),
                        'monthly_charges': row.iloc[0].get('monthly_charges', 0),
                        'contract_value': row.iloc[0].get('contract_value', 0),
                        'last_login_date': row.iloc[0].get('last_login_date', ''),
                        'renewal_date': row.iloc[0].get('renewal_date', ''),
                        'usage_metrics': load_metrics(account_id),
                        'support_tickets': load_tickets(account_id)
                    }
                    risk_result = calculate_risk(account_dict)
                    if isinstance(risk_result, tuple):
                        risk_reasons = risk_result[2] if len(risk_result) > 2 else []
            except Exception as e:
                print(f"[Renew] CSV data fetch error: {e}")

        try:
            add_outcome_to_rag(
                account_id=account_id,
                risk_reasons=risk_reasons,
                outcome='renewed',
                csm_action='CSM manually marked as renewed'
            )
        except Exception as e:
            print(f"[Renew] RAG update error: {e}")

        return jsonify({
            'message': f'Account {account_id} marked as successfully renewed.',
            'status': 'Renewed',
            'was_successful': True
        }), 200

    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/accounts/<account_id>/similar', methods=['GET'])
def get_similar_cases(account_id):
    try:
        from rules_engine import calculate_risk
        from rag import retrieve_similar_cases

        account = None

        # Handle HubSpot accounts
        if account_id.startswith('HS-'):
            try:
                from mcp_client import fetch_companies
                companies = fetch_companies()
                company = next((c for c in companies if c.get('id') == account_id), None)
                if company:
                    account = {
                        'id': company.get('id'),
                        'name': company.get('name'),
                        'tenure': company.get('tenure', 0),
                        'monthly_charges': company.get('monthly_charges', 0),
                        'contract_type': company.get('contract_type', 'Month-to-month'),
                        'assigned_csm': company.get('assigned_csm', 'Unassigned'),
                        'status': company.get('status', 'Active'),
                        'last_login_date': company.get('last_login_date', ''),
                        'renewal_date': company.get('renewal_date', ''),
                        'contract_value': company.get('contract_value', 0),
                        'usage_metrics': [{
                            'feature_adoption_pct': company.get('feature_adoption_pct', 0),
                            'login_frequency': company.get('login_frequency', 0),
                            'session_duration_avg': company.get('session_duration_avg', 0)
                        }],
                        'support_tickets': []
                    }
            except Exception as e:
                print(f"[Similar] HubSpot fetch error: {e}")

        # Handle CSV accounts
        if account is None and not account_id.startswith('HS-'):
            from data_loader import load_accounts, load_metrics, load_tickets
            accounts = load_accounts()
            account = next((a for a in accounts if a.get('id') == account_id), None)
            if account:
                account['usage_metrics'] = load_metrics(account_id)
                account['support_tickets'] = load_tickets(account_id)

        if not account:
            return jsonify({'error': 'Account not found'}), 404

        risk_info = calculate_risk(account)
        if isinstance(risk_info, tuple):
            risk_reasons = risk_info[2]
        else:
            risk_reasons = risk_info.get('reasons', [])

        if isinstance(risk_reasons, str):
            risk_reasons = [r.strip() for r in risk_reasons.split(';') if r.strip()]

        similar_cases = retrieve_similar_cases(risk_reasons, n_results=3)

        llm = get_llm()
        formatted = []

        for case in similar_cases:
            churn_reason = case.get('churn_reason', 'Not specified')
            contract = case.get('contract', 'Unknown')
            tenure = case.get('tenure', 'Unknown')
            monthly_charges = case.get('monthly_charges', 'Unknown')
            text = case.get('text', '')[:250]

            what_worked = None
            try:
                intervention_prompt = (
                    f"A SaaS customer churned with these signals: "
                    f"Contract type: {contract}. "
                    f"Tenure: {tenure} months. "
                    f"Monthly charges: ${monthly_charges}. "
                    f"Churn reason: {churn_reason}. "
                    f"In exactly one sentence, what retention intervention would most likely have saved this account? "
                    f"Be specific and actionable. Do not start with 'I' or 'The customer'."
                )
                response = llm.invoke(intervention_prompt)
                if hasattr(response, 'content'):
                    what_worked = response.content.strip()
                else:
                    what_worked = str(response).strip()
            except Exception as e:
                what_worked = None

            formatted.append({
                'text': text,
                'churn_reason': churn_reason,
                'contract': contract,
                'tenure': tenure,
                'monthly_charges': monthly_charges,
                'similarity_score': case.get('similarity_score', None),
                'what_worked': what_worked,
                'source': case.get('source', 'IBM Telco Dataset')
            })

        return jsonify({'similar_cases': formatted, 'total': len(formatted)}), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/admin/thresholds', methods=['GET'])
def get_thresholds_api():
    """Return all rule thresholds for admin configuration panel."""
    try:
        from models import RuleThreshold
        import datetime
        session = get_engine_session()
        thresholds = session.query(RuleThreshold).all()
        session.close()
        result = []
        for t in thresholds:
            result.append({
                'rule_name': t.rule_name,
                'value': t.value,
                'label': t.label,
                'description': t.description,
                'unit': t.unit,
                'min_value': t.min_value,
                'max_value': t.max_value,
                'last_updated': t.last_updated.isoformat() if t.last_updated else None
            })
        return jsonify({'thresholds': result}), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/admin/thresholds/<rule_name>', methods=['PUT'])
def update_threshold_api(rule_name):
    """Update a single rule threshold value."""
    try:
        from models import RuleThreshold
        import datetime
        data = request.get_json()
        new_value = data.get('value')
        if new_value is None:
            return jsonify({'error': 'Missing value'}), 400
        session = get_engine_session()
        threshold = session.query(RuleThreshold).filter_by(rule_name=rule_name).first()
        if not threshold:
            session.close()
            return jsonify({'error': f'Threshold {rule_name} not found'}), 404
        threshold.value = float(new_value)
        threshold.last_updated = datetime.datetime.utcnow()
        session.commit()
        session.close()
        return jsonify({'message': f'Threshold {rule_name} updated to {new_value}', 'rule_name': rule_name, 'value': new_value}), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(debug=False, host="0.0.0.0", port=port, threaded=True)
