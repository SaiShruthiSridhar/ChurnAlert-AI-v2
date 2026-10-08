from database import SessionLocal
from models import Account, RuleWeight
import datetime


def run_feedback_loop(fired_rules=None):
    """
    Adjusts rule weights based on churn outcomes.

    If fired_rules is provided (list of rule names that fired for a churned account),
    only those specific rules have their weights raised by 5% (capped at 2.0).

    If fired_rules is None or empty, no weights are adjusted
    (prevents global weight drift from unlinked calls).
    """
    db = SessionLocal()

    successful = db.query(Account).filter(Account.was_successful == True).count()
    failed = db.query(Account).filter(Account.was_successful == False).count()

    if fired_rules:
        # Only boost weights for the rules that actually fired on a churned account
        for rule_name in fired_rules:
            w = db.query(RuleWeight).filter(RuleWeight.rule_name == rule_name).first()
            if w:
                w.weight = min(2.0, round(w.weight * 1.05, 4))
                w.last_adjusted = datetime.datetime.utcnow()
        try:
            from rules_engine import invalidate_rules_cache
            invalidate_rules_cache()
        except Exception:
            pass
        print(f"[Feedback Loop] Boosted weights for {len(fired_rules)} fired rules: {fired_rules}")
    else:
        print("[Feedback Loop] No fired_rules provided — skipping weight adjustment.")

    print(f"[Feedback Loop] Outcomes so far: {successful} successes, {failed} failures.")
    db.close()


if __name__ == "__main__":
    run_feedback_loop()
