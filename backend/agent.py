from typing import TypedDict, List, Annotated
from langgraph.graph import StateGraph, END
from langgraph.checkpoint.sqlite import SqliteSaver
import sqlite3
from llm import get_llm
from rules_engine import calculate_risk
from rag import retrieve_similar_cases
import json
import os
from dotenv import load_dotenv
from langsmith import traceable

load_dotenv()

os.environ["LANGCHAIN_TRACING_V2"] = os.getenv("LANGCHAIN_TRACING_V2", "true")
os.environ["LANGCHAIN_API_KEY"] = os.getenv("LANGCHAIN_API_KEY", "")
os.environ["LANGCHAIN_PROJECT"] = os.getenv("LANGCHAIN_PROJECT", "churneye")

# Initialize global SQLite connection and checkpointer
conn = sqlite3.connect("churn_ai_checkpoints.db", check_same_thread=False)
memory = SqliteSaver(conn)


class AgentState(TypedDict, total=False):
    account_id: str
    account_data: dict
    risk_info: dict
    similar_cases: List[dict]
    reasoning: str
    action_recommendation: str
    outreach_draft: str
    confidence: str
    query: str
    chat_response: str
    hubspot_used: bool
    brief: dict
    outcome: str

import data_loader

def monitor_node(state: AgentState):
    # Try HubSpot MCP first, fall back to CSV
    account_data = None
    hubspot_used = False

    try:
        from mcp_client import is_hubspot_connected, fetch_companies, fetch_company_details, fetch_company_tickets
        if is_hubspot_connected():
            print(f"[Monitor Node] Fetching account {state['account_id']} from HubSpot MCP...")
            companies = fetch_companies()
            # Match by account ID or company name
            account_id = state.get('account_id', '')
            hubspot_company = None
            for company in companies:
                if company.get('id') == account_id or company.get('hubspot_id') and f"HS-{company['hubspot_id']}" == account_id:
                    hubspot_company = company
                    break
            if hubspot_company:
                hubspot_id = hubspot_company.get('hubspot_id')
                tickets = fetch_company_tickets(hubspot_id) if hubspot_id else []
                account_data = {
                    'id': account_id,
                    'name': hubspot_company.get('name', 'Unknown'),
                    'tenure': hubspot_company.get('tenure', 0),
                    'monthly_charges': hubspot_company.get('monthly_charges', 0),
                    'contract_type': hubspot_company.get('contract_type', 'Month-to-month'),
                    'contract': hubspot_company.get('contract_type', 'Month-to-month'),
                    'assigned_csm': hubspot_company.get('assigned_csm', 'Unassigned'),
                    'status': hubspot_company.get('status', 'Active'),
                    'contract_value': hubspot_company.get('contract_value', 0),
                    'last_login_date': hubspot_company.get('last_login_date', ''),
                    'last_login': hubspot_company.get('last_login_date', ''),
                    'renewal_date': hubspot_company.get('renewal_date', ''),
                    'renewal': hubspot_company.get('renewal_date', ''),
                    'usage_metrics': [{
                        'feature_adoption_pct': hubspot_company.get('feature_adoption_pct', 0),
                        'login_frequency': hubspot_company.get('login_frequency', 0),
                        'session_duration_avg': hubspot_company.get('session_duration_avg', 0)
                    }],
                    'usage': [{
                        'feature_adoption_pct': hubspot_company.get('feature_adoption_pct', 0),
                        'login_frequency': hubspot_company.get('login_frequency', 0),
                        'session_duration_avg': hubspot_company.get('session_duration_avg', 0)
                    }],
                    'support_tickets': tickets,
                    'tickets': tickets,
                    'source': 'hubspot'
                }
                hubspot_used = True
                print(f"[Monitor Node] Account loaded from HubSpot: {account_data['name']}")
    except Exception as e:
        print(f"[Monitor Node] HubSpot fetch failed: {e}. Falling back to CSV.")

    # Fall back to CSV if HubSpot not used
    if not account_data:
        print(f"[Monitor Node] Loading account {state['account_id']} from CSV...")
        account = data_loader.get_account_details(state['account_id'])
        account_data = {
            "name": account['name'],
            "tenure": account['tenure'],
            "monthly_charges": account['monthly_charges'],
            "contract": account['contract_type'],
            "last_login": account['last_login_date'],
            "renewal": account['renewal_date'],
            "usage": account['usage_metrics'][:2],
            "tickets": account['support_tickets'][:3],
            "id": state['account_id'],
            "contract_type": account['contract_type'],
            "assigned_csm": account.get('assigned_csm', 'Unassigned'),
            "status": account.get('status', 'Active'),
            "contract_value": account.get('contract_value', 0),
            "last_login_date": account['last_login_date'],
            "renewal_date": account['renewal_date'],
            "source": "csv"
        }

    return {"account_data": account_data, "hubspot_used": hubspot_used}

def score_node(state: AgentState):
    account = state.get('account_data')
    if not account:
        account = data_loader.get_account_details(state['account_id'])
    score, tier, reasons, fired_rules = calculate_risk(account)
    return {"risk_info": {"score": score, "tier": tier, "reasons": reasons, "fired_rules": fired_rules}}

def retrieve_node(state: AgentState):
    # Retrieve similar cases based on risk reasons
    risk_reasons = state.get("risk_info", {}).get("reasons", [])
    if isinstance(risk_reasons, str):
        risk_reasons = [r.strip() for r in risk_reasons.split(";") if r.strip()]
    similar_cases = retrieve_similar_cases(risk_reasons, n_results=3)
    return {"similar_cases": similar_cases}


@traceable(name="reason_node — ChurnEye Risk Analysis")
def reason_node(state: AgentState):
    llm = get_llm()
    prompt = f"""
    You are a Senior Behavioral Scientist & Retention Strategist at ChurnAlert AI.
    Your goal is to synthesize raw telemetry into a psychological profile of the customer's health.
    
    ### CUSTOMER TELEMETRY
    Account: {json.dumps(state['account_data'])}
    
    ### DETERMINISTIC RISK SIGNALS
    Signals: {json.dumps(state['risk_info'])}
    
    ### TASK
    1. BEHAVIORAL REASONING: Analyze WHY this customer is behaving this way. Go beyond the surface. 
    2. STRATEGIC PRECRIPTION: Recommend a high-impact intervention. 
    3. EMPATHETIC OUTREACH: Draft a highly personalized, non-generic message.
    """
    similar_cases = state.get("similar_cases", [])
    cases_text = ""
    if similar_cases:
        cases_text = "\n\nSIMILAR HISTORICAL CHURN CASES (from IBM Telco Dataset):\n"
        for i, case in enumerate(similar_cases[:3], 1):
            cases_text += f"\nCase {i}:\n"
            cases_text += f"  Profile: {case.get('text', 'No details available')[:300]}\n"
            if case.get('churn_reason'):
                cases_text += f"  Churn Reason: {case.get('churn_reason')}\n"
            if case.get('similarity_score'):
                cases_text += f"  Similarity: {case.get('similarity_score')}\n"
            if case.get('action'):
                cases_text += f"  Recommended Action: {case.get('action')}\n"
    prompt += cases_text
    prompt += """
    Return a JSON object with exactly these 4 keys:
    {{
      "reasoning": "exactly 3 bullet points maximum. Format: • bullet 1 • bullet 2 • bullet 3. One sentence each. No paragraphs. No more than 3 bullets.",
      "recommendation": "exactly 3 bullet points. Format: • who to contact • when to contact • what to offer. One sentence each. No paragraphs.",
      "draft": "short outreach message — maximum 5 sentences total. Subject line first. Then 3 sentences body. Then sign off. No long paragraphs.",
      "confidence": "HIGH or MEDIUM or LOW — your confidence in this risk assessment based on signal strength and data quality"
    }}
    Return ONLY valid JSON. No extra text before or after.
    """
    response = llm.invoke(prompt)
    content = response.content.strip()
    try:
        # Improved JSON extraction
        json_start = content.find('{')
        json_end = content.rfind('}')
        if json_start != -1 and json_end != -1:
            json_str = content[json_start:json_end+1]
            res = json.loads(json_str, strict=False)
            return {
                "reasoning": res.get('reasoning', "Deep behavioral analysis required."),
                "action_recommendation": res.get('recommendation', "Executive Outreach"),
                "outreach_draft": res.get('draft', f"Hi {state['account_data']['name']}, I've been reviewing your account..."),
                "confidence": res.get('confidence', "MEDIUM")
            }
        raise ValueError("No JSON found in response")
    except Exception as e:
        print(f"AI Synthesis error: {e}")
        print(f"Raw Output was: {content}")
        return {
            "reasoning": "Manual analysis required: The AI reasoning engine encountered a format variance.",
            "action_recommendation": "Priority CSM Strategy Session",
            "outreach_draft": f"Hi {state['account_data']['name']}, I noticed some interesting patterns in your metrics today...",
            "confidence": "MEDIUM"
        }


@traceable(name="chat_node — ChurnEye Assistant")
def chat_node(state: AgentState):
    llm = get_llm()
    prompt = f"""
    You are the ChurnAI Intelligent Assistant. You have access to a customer's real-time data and risk profile.
    
    ### CUSTOMER DATA
    {json.dumps(state['account_data'])}
    
    ### RISK PROFILE
    {json.dumps(state['risk_info'])}
    
    ### USER QUESTION
    {state['query']}
    
    ### INSTRUCTIONS
    1. Always respond in bullet points only. No paragraphs. No long sentences.
    2. Maximum 4 bullet points per response.
    3. Each bullet must be one short sharp sentence.
    4. Reference specific metrics like login frequency, feature adoption, or charges when relevant.
    5. Never write more than 4 lines total.
    
    Respond in bullet points only:
    """
    response = llm.invoke(prompt)
    return {"chat_response": response.content}

def human_review_node(state: AgentState):
    """
    Pause point for CSM human review. The agent is interrupted here before
    the outcome node runs. A CSM must call /accounts/<id>/approve to resume.
    This node itself is a no-op — it just serves as the interrupt checkpoint.
    """
    account_name = state.get('account_data', {}).get('name', 'Unknown')
    tier = state.get('risk_info', {}).get('tier', 'UNKNOWN')
    print(f"[Human Review Node] Awaiting CSM approval for {account_name} — {tier} risk.")
    return {}

def brief_node(state: AgentState):
    risk_info = state.get('risk_info', {})
    account_data = state.get('account_data', {})
    tier = risk_info.get('tier', 'LOW')
    brief = {
        'account_id': state.get('account_id'),
        'account_name': account_data.get('name', 'Unknown'),
        'risk_tier': tier,
        'risk_score': risk_info.get('score', 0),
        'assigned_csm': account_data.get('assigned_csm', 'Unassigned'),
        'reasoning': state.get('reasoning', ''),
        'action_recommendation': state.get('action_recommendation', ''),
        'outreach_draft': state.get('outreach_draft', ''),
        'confidence': state.get('confidence', 'MEDIUM'),
        'priority_rank': 0 if tier == 'HIGH' else 1 if tier == 'MEDIUM' else 2
    }
    print(f"[Brief Node] Package ready for {brief['account_name']} — {tier} risk — CSM: {brief['assigned_csm']}")
    return {"brief": brief}

def outcome_node(state: AgentState):
    """
    Records agent analysis outcome: updates account status, saves to ChromaDB RAG,
    runs feedback loop with the rules that fired, and sets admin flag for high-risk churned accounts.
    """
    outcome = state.get('outcome', '')
    risk_info = state.get('risk_info', {})
    tier = risk_info.get('tier', 'LOW')
    account_id = state.get('account_id', '')
    account_name = state.get('account_data', {}).get('name', 'Unknown')
    fired_rules = risk_info.get('fired_rules', [])
    risk_reasons = risk_info.get('reasons', [])

    print(f"[Outcome Node] Processing {account_name} ({account_id}) — outcome: '{outcome}', tier: {tier}")

    if outcome == 'churned':
        try:
            from database import SessionLocal
            from models import Account
            import datetime
            session = SessionLocal()
            acc = session.query(Account).filter_by(id=account_id).first()
            if acc:
                acc.status = 'Churned'
                acc.was_successful = False
                acc.outcome_date = datetime.datetime.utcnow()
                acc.flagged_for_admin = True
                acc.flag_reason = "CSM-reported churn"
                session.commit()
            session.close()
            print(f"[Outcome Node] Marked {account_name} ({account_id}) as Churned in SQLite and flagged for admin.")
        except Exception as e:
            print(f"[Outcome Node] SQLite update error for churned outcome: {e}")

        try:
            from rag import add_outcome_to_rag
            add_outcome_to_rag(
                account_id=account_id,
                risk_reasons=risk_reasons,
                outcome='churned',
                csm_action="CSM reported churn outcome"
            )
            print(f"[Outcome Node] Saved {account_name} ({account_id}) to ChromaDB RAG with outcome='churned'.")
        except Exception as e:
            print(f"[Outcome Node] RAG update error: {e}")

        if fired_rules:
            try:
                from feedback_loop import run_feedback_loop
                run_feedback_loop(fired_rules=fired_rules)
                print(f"[Outcome Node] Feedback loop recalibrated for churned rules: {fired_rules}")
            except Exception as e:
                print(f"[Outcome Node] Feedback loop error: {e}")

    elif outcome == 'renewed':
        try:
            from database import SessionLocal
            from models import Account
            import datetime
            session = SessionLocal()
            acc = session.query(Account).filter_by(id=account_id).first()
            if acc:
                acc.status = 'Renewed'
                acc.was_successful = True
                acc.outcome_date = datetime.datetime.utcnow()
                session.commit()
            session.close()
            print(f"[Outcome Node] Marked {account_name} ({account_id}) as Renewed in SQLite.")
        except Exception as e:
            print(f"[Outcome Node] SQLite update error for renewed outcome: {e}")

        try:
            from rag import add_outcome_to_rag
            add_outcome_to_rag(
                account_id=account_id,
                risk_reasons=risk_reasons,
                outcome='renewed',
                csm_action="CSM reported renewed outcome"
            )
            print(f"[Outcome Node] Saved {account_name} ({account_id}) to ChromaDB RAG with outcome='renewed'.")
        except Exception as e:
            print(f"[Outcome Node] RAG update error: {e}")

    else:
        # outcome is empty — agent just finished analysis, no CSM decision yet
        if tier in ['HIGH', 'MEDIUM']:
            try:
                from database import SessionLocal
                from models import Account
                session = SessionLocal()
                acc = session.query(Account).filter_by(id=account_id).first()
                if acc and acc.status == 'Active':
                    if tier == 'HIGH':
                        contract_value = state.get('account_data', {}).get('contract_value', 0)
                        try:
                            contract_value = float(contract_value)
                        except (ValueError, TypeError):
                            contract_value = 0
                        if contract_value > 10000:
                            acc.flagged_for_admin = True
                            acc.flag_reason = f"Auto-flagged: HIGH risk account with ${contract_value:,.0f} contract value"
                    session.commit()
                session.close()
            except Exception as e:
                print(f"[Outcome Node] SQLite update error: {e}")

            try:
                from rag import add_outcome_to_rag
                add_outcome_to_rag(
                    account_id=account_id,
                    risk_reasons=risk_reasons,
                    outcome='at_risk',
                    csm_action=f"AI analysis completed — {tier} risk tier assigned"
                )
            except Exception as e:
                print(f"[Outcome Node] RAG update error: {e}")

            if tier == 'HIGH' and fired_rules:
                try:
                    from feedback_loop import run_feedback_loop
                    run_feedback_loop(fired_rules=fired_rules)
                    print(f"[Outcome Node] Feedback loop updated {len(fired_rules)} rule weights.")
                except Exception as e:
                    print(f"[Outcome Node] Feedback loop error: {e}")

            print(f"[Outcome Node] {account_name} — {tier} risk — queued for CSM review.")
        else:
            print(f"[Outcome Node] {account_name} is LOW risk. No immediate action needed.")

    return {}

def route_after_score(state: AgentState):
    """After scoring, skip AI for LOW risk accounts."""
    tier = state.get('risk_info', {}).get('tier', 'LOW')
    if tier == 'LOW':
        return END
    return "retrieve"

def get_agent():
    workflow = StateGraph(AgentState)

    workflow.add_node("monitor", monitor_node)
    workflow.add_node("score", score_node)
    workflow.add_node("retrieve", retrieve_node)
    workflow.add_node("reason", reason_node)
    workflow.add_node("brief", brief_node)
    workflow.add_node("human_review", human_review_node)
    workflow.add_node("outcome", outcome_node)

    workflow.set_entry_point("monitor")
    workflow.add_edge("monitor", "score")
    workflow.add_conditional_edges("score", route_after_score, {"retrieve": "retrieve", END: END})
    workflow.add_edge("retrieve", "reason")
    workflow.add_edge("reason", "brief")
    workflow.add_edge("brief", "human_review")
    workflow.add_edge("human_review", "outcome")
    workflow.add_edge("outcome", END)

    return workflow.compile(checkpointer=memory, interrupt_before=["human_review", "outcome"])

def get_chat_agent():
    workflow = StateGraph(AgentState)
    
    workflow.add_node("monitor", monitor_node)
    workflow.add_node("score", score_node)
    workflow.add_node("chat", chat_node)
    
    workflow.set_entry_point("monitor")
    workflow.add_edge("monitor", "score")
    workflow.add_edge("score", "chat")
    workflow.add_edge("chat", END)
    
    return workflow.compile(checkpointer=memory)

def run_analysis_agent(account_id: str):
    agent = get_agent()
    config = {"configurable": {"thread_id": f"analysis-{account_id}"}}
    result = agent.invoke({"account_id": account_id}, config=config)
    
    risk_info = result.get("risk_info", {})
    tier = risk_info.get("tier", "LOW")
    
    return {
        "account_id": account_id,
        "risk_tier": tier,
        "reasoning": result.get("reasoning"),
        "action_recommendation": result.get("action_recommendation"),
        "outreach_draft": result.get("outreach_draft"),
        "confidence": result.get("confidence", "MEDIUM"),
        "brief": result.get("brief")
    }
