from database import init_db, SessionLocal
from models import Account, RiskScore, UsageMetric, SupportTicket, RuleWeight
from rules_engine import calculate_risk
from faker import Faker
import random
import datetime

fake = Faker()

def seed():
    init_db()
    db = SessionLocal()
    
    # Initialize Rule Weights
    rules = [
        "month_to_month", "tenure_critical", "tenure_early", "inactive_renewal",
        "renewal_approaching", "low_adoption_critical", "low_adoption",
        "inactive_critical", "inactive", "low_session_duration", "no_usage_data",
        "negative_tickets_high", "negative_tickets", "unresolved_tickets", "high_value_account"
    ]
    for r in rules:
        if not db.query(RuleWeight).filter(RuleWeight.rule_name == r).first():
            db.add(RuleWeight(rule_name=r, weight=1.0))
    db.commit()

    # Seed Accounts
    contract_types = ["Month-to-month", "One year", "Two year"]
    today = datetime.datetime.utcnow()
    
    for _ in range(100):
        acc_id = fake.uuid4()[:8].upper()
        tenure = random.randint(1, 72)
        monthly_charges = round(random.uniform(20.0, 180.0), 2)
        contract = random.choice(contract_types)
        
        account = Account(
            id=acc_id,
            name=fake.company(),
            tenure=tenure,
            monthly_charges=monthly_charges,
            contract_type=contract,
            assigned_csm=fake.name(),
            last_login_date=today - datetime.timedelta(days=random.randint(0, 45)),
            renewal_date=today + datetime.timedelta(days=random.randint(5, 400)),
            contract_value=monthly_charges * (12 if contract != "Month-to-month" else 1)
        )
        db.add(account)
        db.flush()
        
        # Usage Metrics (more history)
        for i in range(8):
            usage = UsageMetric(
                account_id=account.id,
                login_frequency=random.randint(0, 15),
                feature_adoption_pct=random.uniform(0, 100),
                session_duration_avg=random.uniform(2, 90),
                timestamp=today - datetime.timedelta(weeks=i)
            )
            db.add(usage)
        
        # Support Tickets (more tickets)
        for _ in range(random.randint(0, 6)):
            ticket = SupportTicket(
                account_id=account.id,
                subject=fake.sentence(nb_words=5),
                sentiment=random.choice(["negative", "neutral", "positive", "negative"]), # Bias towards negative for testing
                is_resolved=random.choice([True, False])
            )
            db.add(ticket)
        
        db.flush()
        
        # Initial risk calculation
        account_dict = {
            'id': account.id,
            'name': account.name,
            'tenure': account.tenure,
            'monthly_charges': account.monthly_charges,
            'contract_type': account.contract_type,
            'assigned_csm': account.assigned_csm,
            'last_login_date': str(account.last_login_date) if account.last_login_date else None,
            'renewal_date': str(account.renewal_date) if account.renewal_date else None,
            'contract_value': account.contract_value,
            'usage_metrics': [{
                'login_frequency': u.login_frequency,
                'feature_adoption_pct': u.feature_adoption_pct,
                'session_duration_avg': u.session_duration_avg
            } for u in account.usage_metrics],
            'support_tickets': [{
                'subject': t.subject,
                'sentiment': t.sentiment,
                'is_resolved': t.is_resolved
            } for t in account.support_tickets]
        }
        score, tier, reasons, fired_rules = calculate_risk(account_dict)
        reasons_str = '; '.join(reasons) if isinstance(reasons, list) else str(reasons)
        risk = RiskScore(account_id=account.id, score=score, tier=tier, reasons=reasons_str)
        db.add(risk)

    db.commit()
    print("Large scale system seeded (100 accounts).")

    db.close()

if __name__ == "__main__":
    seed()
