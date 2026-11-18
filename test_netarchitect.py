import ipaddress
import pytest

from netarchitect import (
    L1MediaEngine,
    NetworkDesignError,
    PhysicalDistanceViolationError,
    RoutingEngine,
    SubnetExhaustionError,
    VLSMEngine,
    create_design,
    wildcard_mask,
)


def test_copper_limit_and_fibre_selection():
    assert "Cat6a" in L1MediaEngine.evaluate_media(100)["media"]
    assert "OM4" in L1MediaEngine.evaluate_media(350)["media"]
    assert "OS2" in L1MediaEngine.evaluate_media(25000)["media"]


def test_forced_copper_over_limit_is_rejected():
    with pytest.raises(PhysicalDistanceViolationError):
        L1MediaEngine.evaluate_media(150, force_copper=True)


def test_vlsm_allocations_are_valid_and_non_overlapping():
    result = VLSMEngine.allocate_subnets(
        "192.168.1.0/24", {"LAN1": 100, "LAN2": 50}
    )
    first = ipaddress.IPv4Network(result[0]["network"] + result[0]["cidr"])
    second = ipaddress.IPv4Network(result[1]["network"] + result[1]["cidr"])
    assert first.prefixlen == 25
    assert second.prefixlen == 26
    assert not first.overlaps(second)
    assert result[0]["gateway"] == "192.168.1.1"
    assert result[1]["gateway"] == "192.168.1.129"


def test_vlsm_exhaustion_is_reported():
    with pytest.raises(SubnetExhaustionError):
        VLSMEngine.allocate_subnets("192.168.1.0/24", {"HugeLAN": 300})


def test_invalid_host_count_is_rejected():
    with pytest.raises(NetworkDesignError):
        VLSMEngine.allocate_subnets("192.168.1.0/24", {"LAN": 0})


def test_invalid_distance_is_rejected():
    with pytest.raises(NetworkDesignError):
        L1MediaEngine.evaluate_media(-1)


def test_wildcard_mask_conversion():
    cases = {
        "255.255.255.252": "0.0.0.3",
        "255.255.255.0": "0.0.0.255",
        "255.255.240.0": "0.0.15.255",
        "255.255.255.255": "0.0.0.0",
    }
    for mask, expected in cases.items():
        assert wildcard_mask(mask) == expected


def test_routing_recommendations():
    assert "Single-area" in RoutingEngine.evaluate_routing(5, False)["protocol"]
    assert "eBGP" in RoutingEngine.evaluate_routing(5, True)["protocol"]


def test_design_contains_ios_config_and_subnets():
    design = create_design({
        "distance_m": 80,
        "root_cidr": "10.0.0.0/24",
        "subnets": {"STUDENTS": 100, "FACULTY": 50},
        "is_multisite": False,
    }, "TEST")
    assert len(design["subnets"]) == 2
    assert "interface Vlan10" in design["ios_configuration"]
    assert "router ospf 1" in design["ios_configuration"]
