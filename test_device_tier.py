"""Tests for device_tier classification."""
from platform_tier.device_tier import DeviceProfile, DeviceTier, TIER_ORDER, ALL_CAPABILITIES


def test_profile_classifies_host():
    # Can't assert a specific tier without mocking — just that one is returned
    profile = DeviceProfile()
    assert profile.tier in TIER_ORDER


def test_capabilities_match_tier():
    profile = DeviceProfile()
    caps = profile.capabilities()
    host_rank = TIER_ORDER.index(profile.tier)

    for cap in caps:
        needed_rank = TIER_ORDER.index(cap.required_tier)
        if host_rank >= needed_rank:
            assert cap.enabled, f"{cap.name} should be enabled at {profile.tier.value}"
        else:
            assert not cap.enabled, f"{cap.name} should be disabled at {profile.tier.value}"


def test_summary_has_all_fields():
    profile = DeviceProfile()
    s = profile.summary()
    for field in ("tier", "os", "arch", "ram_gb", "cpu_count",
                  "has_docker", "has_gpu", "is_headless", "capabilities"):
        assert field in s


def test_phone_tier_still_runs_core():
    # Find the capabilities that should work at PHONE tier
    phone_caps = [name for name, tier in ALL_CAPABILITIES if tier == DeviceTier.PHONE]
    # Core money + gating must always be available
    for required in ("api_routing", "ledger", "compliance_gate",
                     "tax_module", "human_loop"):
        assert required in phone_caps, f"{required} must run on PHONE tier"


def test_workstation_implies_standard():
    # If workstation-required caps exist, standard-required caps must also exist in the list
    workstation_caps = [name for name, tier in ALL_CAPABILITIES
                        if tier == DeviceTier.WORKSTATION]
    standard_caps = [name for name, tier in ALL_CAPABILITIES
                     if tier == DeviceTier.STANDARD]
    assert len(workstation_caps) > 0
    assert len(standard_caps) > 0
