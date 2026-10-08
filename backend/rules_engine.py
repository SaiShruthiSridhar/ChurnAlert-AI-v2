import datetime

_thresholds_cache = None
_weights_cache = None

def invalidate_rules_cache():
    global _thresholds_cache, _weights_cache
    _thresholds_cache = None
    _weights_cache = None

def get_thresholds(force_refresh=False):
    global _thresholds_cache
    if not force_refresh and _thresholds_cache is not None:
        return _thresholds_cache
    try:
        from database import SessionLocal
        from models import RuleThreshold
        session = SessionLocal()
        thresholds = session.query(RuleThreshold).all()
        session.close()
        _thresholds_cache = {t.rule_name: t.value for t in thresholds}
        return _thresholds_cache
    except Exception:
        return _thresholds_cache or {}

def get_weights(force_refresh=False):
    global _weights_cache
    if not force_refresh and _weights_cache is not None:
        return _weights_cache
    try:
        from database import SessionLocal
        from models import RuleWeight
        session = SessionLocal()
        weights = session.query(RuleWeight).all()
        session.close()
        _weights_cache = {w.rule_name: float(w.weight) for w in weights}
        return _weights_cache
    except Exception:
        return _weights_cache or {}

def calculate_risk(account):
    t = get_thresholds()

    NO_LOGIN_DAYS = t.get('no_login_days', 14)
    RENEWAL_WINDOW = t.get('renewal_window_days', 30)
    ADOPTION_CRITICAL = t.get('feature_adoption_critical', 20)
    ADOPTION_LOW = t.get('feature_adoption_low', 50)
    LOGIN_CRITICAL = t.get('login_frequency_critical', 3)
    LOGIN_LOW = t.get('login_frequency_low', 10)
    SESSION_MIN = t.get('session_duration_min', 5)
    NEGATIVE_TICKETS = t.get('negative_tickets_threshold', 3)
    HIGH_VALUE = t.get('high_value_contract', 10000)
    HIGH_SCORE = t.get('high_risk_score', 70)
    MEDIUM_SCORE = t.get('medium_risk_score', 35)
    TENURE_CRITICAL = t.get('tenure_critical', 3)
    TENURE_EARLY = t.get('tenure_early', 6)

    weights = get_weights()

    contract_score = 0
    usage_score = 0
    support_score = 0
    reasons = []
    fired_rules = []  # Track which rule names fired, for feedback loop

    # 1. Contract & Tenure (Max 25 pts)
    if account.get('contract_type') == "Month-to-month":
        w = weights.get('month_to_month', 1.0)
        contract_score += round(15 * w)
        reasons.append("High-risk Month-to-month contract")
        fired_rules.append('month_to_month')

    tenure = account.get('tenure', 0)
    if tenure < TENURE_CRITICAL:
        w = weights.get('tenure_critical', 1.0)
        contract_score += round(10 * w)
        reasons.append(f"Critical early-stage tenure (< {int(TENURE_CRITICAL)}m)")
        fired_rules.append('tenure_critical')
    elif tenure < TENURE_EARLY:
        w = weights.get('tenure_early', 1.0)
        contract_score += round(5 * w)
        reasons.append(f"Early-stage tenure (< {int(TENURE_EARLY)}m)")
        fired_rules.append('tenure_early')

    renewal_date = account.get('renewal_date')
    last_login = account.get('last_login_date')
    if renewal_date and last_login:
        try:
            if isinstance(renewal_date, str):
                renewal_dt = datetime.datetime.strptime(renewal_date[:10], '%Y-%m-%d')
            else:
                renewal_dt = renewal_date
            if isinstance(last_login, str):
                login_dt = datetime.datetime.strptime(last_login[:10], '%Y-%m-%d')
            else:
                login_dt = last_login
            days_to_renewal = (renewal_dt - datetime.datetime.utcnow()).days
            days_since_login = (datetime.datetime.utcnow() - login_dt).days
            if days_since_login >= NO_LOGIN_DAYS and days_to_renewal <= RENEWAL_WINDOW:
                w = weights.get('inactive_renewal', 1.0)
                contract_score += round(20 * w)
                if days_to_renewal < 0:
                    reasons.append(f"No login in {days_since_login} days and renewal overdue by {abs(days_to_renewal)} days — immediate HIGH risk")
                else:
                    reasons.append(f"No login in {days_since_login} days with renewal in {days_to_renewal} days — immediate HIGH risk")
                fired_rules.append('inactive_renewal')
            elif days_to_renewal <= RENEWAL_WINDOW:
                w = weights.get('renewal_approaching', 1.0)
                contract_score += round(10 * w)
                if days_to_renewal < 0:
                    reasons.append(f"Renewal overdue by {abs(days_to_renewal)} days")
                else:
                    reasons.append(f"Renewal approaching in {days_to_renewal} days")
                fired_rules.append('renewal_approaching')
        except Exception:
            pass

    # 2. Usage & Adoption (Max 40 pts)
    metrics = account.get('usage_metrics', [])
    if metrics:
        latest = metrics[0]
        adoption = latest.get('feature_adoption_pct', 100)
        if adoption < ADOPTION_CRITICAL:
            w = weights.get('low_adoption_critical', 1.0)
            usage_score += round(20 * w)
            reasons.append(f"Critically low feature adoption (< {int(ADOPTION_CRITICAL)}%)")
            fired_rules.append('low_adoption_critical')
        elif adoption < ADOPTION_LOW:
            w = weights.get('low_adoption', 1.0)
            usage_score += round(10 * w)
            reasons.append("Under-utilization of platform features")
            fired_rules.append('low_adoption')

        freq = latest.get('login_frequency', 30)
        if freq < LOGIN_CRITICAL:
            w = weights.get('inactive_critical', 1.0)
            usage_score += round(15 * w)
            reasons.append("Severe inactivity (low login frequency)")
            fired_rules.append('inactive_critical')
        elif freq < LOGIN_LOW:
            w = weights.get('inactive', 1.0)
            usage_score += round(5 * w)
            reasons.append("Declining engagement frequency")
            fired_rules.append('inactive')

        duration = latest.get('session_duration_avg', 30)
        if duration < SESSION_MIN:
            w = weights.get('low_session_duration', 1.0)
            usage_score += round(5 * w)
            reasons.append("Surface-level sessions (low duration)")
            fired_rules.append('low_session_duration')
    else:
        w = weights.get('no_usage_data', 1.0)
        usage_score += round(30 * w)
        reasons.append("No usage data recorded")
        fired_rules.append('no_usage_data')

    # 3. Support & Sentiment (Max 35 pts)
    tickets = account.get('support_tickets', [])
    negative_tickets = [t for t in tickets if t.get('sentiment') == "negative"]
    unresolved_tickets = [t for t in tickets if not t.get('is_resolved')]

    if negative_tickets:
        neg_count = len(negative_tickets)
        if neg_count > NEGATIVE_TICKETS:
            w = weights.get('negative_tickets_high', 1.0)
            support_score += round(25 * w)
            reasons.append(f"HIGH escalation — {neg_count} negative sentiment tickets (exceeds threshold of {int(NEGATIVE_TICKETS)})")
            fired_rules.append('negative_tickets_high')
        else:
            w = weights.get('negative_tickets', 1.0)
            support_score += round(min(20, neg_count * 10) * w)
            reasons.append(f"Detected {neg_count} negative sentiment ticket(s)")
            fired_rules.append('negative_tickets')

    if unresolved_tickets:
        unres_count = len(unresolved_tickets)
        w = weights.get('unresolved_tickets', 1.0)
        support_score += round(min(10, unres_count * 5) * w)
        reasons.append(f"{unres_count} unresolved support ticket(s) outstanding")
        fired_rules.append('unresolved_tickets')

    total_score = contract_score + usage_score + support_score
    final_score = min(100, total_score)

    contract_value = account.get('contract_value', 0)
    try:
        contract_value = float(contract_value)
    except (ValueError, TypeError):
        contract_value = 0
    if contract_value > HIGH_VALUE and total_score > 0:
        w = weights.get('high_value_account', 1.0)
        final_score = min(100, final_score + round(10 * w))
        reasons.append(f"High-value account (${contract_value:,.0f}) — escalate to senior CSM")
        fired_rules.append('high_value_account')

    if final_score >= HIGH_SCORE:
        tier = "HIGH"
    elif final_score >= MEDIUM_SCORE:
        tier = "MEDIUM"
    else:
        tier = "LOW"

    reasons = reasons[:5]
    return final_score, tier, reasons, fired_rules
