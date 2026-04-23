"""Tests for legal_gate module."""
from compliance.legal_gate import LegalGate, Jurisdiction, RiskLevel


def test_prohibited_social_scoring_blocked():
    gate = LegalGate()
    result = gate.check(
        product_type="app",
        target_markets=[Jurisdiction.EU],
        description="A social credit score for citizens.",
    )
    assert result.approved is False
    assert result.risk_level == RiskLevel.PROHIBITED


def test_prohibited_predictive_policing_blocked():
    gate = LegalGate()
    result = gate.check(
        product_type="app",
        target_markets=[Jurisdiction.BOTH],
        description="Predictive policing dashboard for precinct risk scoring.",
    )
    assert result.approved is False
    assert result.risk_level == RiskLevel.PROHIBITED


def test_benign_template_passes():
    gate = LegalGate()
    result = gate.check(
        product_type="notion_template",
        target_markets=[Jurisdiction.US],
        description="A Notion template for tracking freelance invoices.",
    )
    assert result.approved is True
    # No EU market, no high-risk signals -> minimal or limited
    assert result.risk_level in (RiskLevel.MINIMAL_RISK, RiskLevel.LIMITED_RISK)


def test_eu_market_triggers_disclosures():
    gate = LegalGate()
    result = gate.check(
        product_type="notion_template",
        target_markets=[Jurisdiction.EU],
        description="A Notion template for tracking freelance invoices.",
    )
    assert result.approved is True
    # EU market bumps to at least LIMITED_RISK and adds AI disclosures
    assert result.risk_level in (RiskLevel.LIMITED_RISK, RiskLevel.HIGH_RISK)
    assert any("AI" in d for d in result.required_disclosures)


def test_high_risk_credit_scoring():
    gate = LegalGate()
    result = gate.check(
        product_type="app",
        target_markets=[Jurisdiction.EU],
        description="An AI credit score system for loan approval.",
    )
    assert result.approved is True
    assert result.risk_level == RiskLevel.HIGH_RISK
    assert any("conformity assessment" in a for a in result.required_actions)


def test_ftc_high_risk_financial():
    gate = LegalGate()
    result = gate.check(
        product_type="app",
        target_markets=[Jurisdiction.US],
        description="Investment advice chatbot for retail traders.",
    )
    assert result.approved is True
    # Financial / FTC high-risk signals should bump to HIGH_RISK
    assert result.risk_level == RiskLevel.HIGH_RISK


def test_keyword_substring_false_negative_fixed():
    """Regression test: the old gate approved 'social_scoring' never matching
    natural language. Verify 'social credit' now matches."""
    gate = LegalGate()
    result = gate.check(
        product_type="platform",
        target_markets=[Jurisdiction.BOTH],
        description="We are building a nationwide social credit program.",
    )
    assert result.approved is False


def test_adjudicator_downgrade():
    """If an LLM adjudicator says it's not actually prohibited, the hit
    should be downgraded to HIGH_RISK rather than blocked."""
    def permissive(description, matches):
        return False  # say: not really prohibited
    gate = LegalGate(adjudicator=permissive)
    result = gate.check(
        product_type="app",
        target_markets=[Jurisdiction.EU],
        # Benign context that happens to contain a trigger phrase
        description="Research paper about predictive policing debates in academia.",
    )
    # Downgraded, not blocked
    assert result.approved is True
    assert result.risk_level == RiskLevel.HIGH_RISK
