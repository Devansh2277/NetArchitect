"""NetArchitect: explainable network planning and Cisco IOS configuration export."""

from __future__ import annotations

import argparse
import ipaddress
import json
import math
import re
from pathlib import Path
from typing import Any


class NetworkDesignError(ValueError):
    """Base class for invalid network design inputs."""


class PhysicalDistanceViolationError(NetworkDesignError):
    """Raised when copper is forced beyond the Ethernet channel limit."""


class SubnetExhaustionError(NetworkDesignError):
    """Raised when the requested subnets do not fit in the parent network."""


class L1MediaEngine:
    """Select a practical Ethernet medium using the link length."""

    COPPER_LIMIT_M = 100
    OM4_LIMIT_M = 400

    @classmethod
    def evaluate_media(cls, distance_m: float, force_copper: bool = False) -> dict[str, str]:
        if not isinstance(distance_m, (int, float)) or distance_m < 0:
            raise NetworkDesignError("Link distance must be a non-negative number of metres.")
        if force_copper and distance_m > cls.COPPER_LIMIT_M:
            raise PhysicalDistanceViolationError(
                f"Copper link is {distance_m:g}m; the design limit is 100m."
            )
        if distance_m <= cls.COPPER_LIMIT_M:
            return {
                "media": "Cat6a copper (10GBASE-T)",
                "rationale": f"{distance_m:g}m is within the 100m Ethernet copper channel limit.",
            }
        if distance_m <= cls.OM4_LIMIT_M:
            return {
                "media": "OM4 multimode fibre (10GBASE-SR)",
                "rationale": f"{distance_m:g}m is above the copper limit and within the 400m OM4 planning range.",
            }
        return {
            "media": "OS2 single-mode fibre (10GBASE-LR/ER)",
            "rationale": f"{distance_m:g}m exceeds the OM4 planning range; OS2 is suitable for longer links.",
        }


class VLSMEngine:
    """Allocate non-overlapping IPv4 subnets using largest-first VLSM."""

    @staticmethod
    def allocate_subnets(root_cidr: str, subnets_requested: dict[str, int]) -> list[dict[str, Any]]:
        try:
            parent = ipaddress.IPv4Network(root_cidr, strict=True)
        except (ipaddress.AddressValueError, ipaddress.NetmaskValueError, ValueError) as exc:
            raise NetworkDesignError(f"Invalid parent IPv4 network: {root_cidr}") from exc

        if not isinstance(subnets_requested, dict) or not subnets_requested:
            raise NetworkDesignError("Provide at least one subnet with a positive host requirement.")

        requests: list[tuple[str, int]] = []
        for name, hosts in subnets_requested.items():
            if not isinstance(name, str) or not name.strip():
                raise NetworkDesignError("Every subnet must have a non-empty name.")
            if isinstance(hosts, bool) or not isinstance(hosts, int) or hosts < 1:
                raise NetworkDesignError(f"Host count for {name} must be a positive integer.")
            requests.append((name, hosts))

        # Largest networks are placed first to reduce fragmentation.
        requests.sort(key=lambda item: item[1], reverse=True)
        cursor = int(parent.network_address)
        parent_end = int(parent.broadcast_address) + 1
        allocations: list[dict[str, Any]] = []

        for name, hosts in requests:
            # Traditional IPv4 LANs reserve network and broadcast addresses.
            required_addresses = hosts + 2
            host_bits = max(2, math.ceil(math.log2(required_addresses)))
            prefix = 32 - host_bits
            block_size = 1 << host_bits
            aligned_cursor = ((cursor + block_size - 1) // block_size) * block_size
            if aligned_cursor + block_size > parent_end or prefix < parent.prefixlen:
                raise SubnetExhaustionError(
                    f"The parent network {parent} has insufficient space for {name} ({hosts} hosts)."
                )

            subnet = ipaddress.IPv4Network((aligned_cursor, prefix))
            usable = subnet.num_addresses - 2
            allocations.append({
                "name": name,
                "requested_hosts": hosts,
                "network": str(subnet.network_address),
                "cidr": f"/{subnet.prefixlen}",
                "subnet_mask": str(subnet.netmask),
                "gateway": str(subnet.network_address + 1),
                "broadcast": str(subnet.broadcast_address),
                "usable_hosts": usable,
                "utilization_percent": round(hosts / usable * 100, 1),
                "rationale": (
                    f"/{subnet.prefixlen} provides {usable} usable addresses for {hosts} hosts "
                    f"({hosts / usable * 100:.1f}% planned utilization)."
                ),
            })
            cursor = int(subnet.broadcast_address) + 1

        return allocations


class RoutingEngine:
    """Recommend a routing approach based on network scale and site count."""

    @staticmethod
    def evaluate_routing(subnet_count: int, is_multisite: bool) -> dict[str, str]:
        if subnet_count < 1:
            raise NetworkDesignError("Routing recommendation needs at least one subnet.")
        if is_multisite:
            return {
                "protocol": "OSPF between sites with eBGP at external boundaries",
                "rationale": "Multiple sites are present; use OSPF for internal reachability and eBGP where separate routing domains meet.",
            }
        if subnet_count <= 50:
            return {
                "protocol": "Single-area OSPF (Area 0)",
                "rationale": f"A single site with {subnet_count} subnets can use one OSPF area for straightforward route management.",
            }
        return {
            "protocol": "Multi-area OSPF",
            "rationale": f"The design has {subnet_count} subnets; multiple OSPF areas can limit topology-change scope.",
        }


def wildcard_mask(subnet_mask: str) -> str:
    """Return the 32-bit inverse of an IPv4 subnet mask for Cisco IOS."""
    mask_int = int(ipaddress.IPv4Address(subnet_mask))
    return str(ipaddress.IPv4Address(mask_int ^ 0xFFFFFFFF))


def _vlan_id(index: int) -> int:
    # Keep generated VLAN IDs in the normal extended VLAN range's safe subset.
    return 10 + (index - 1) * 10


def build_ios_config(allocations: list[dict[str, Any]], routing: dict[str, str]) -> str:
    """Create an SVI, OSPF and management ACL example for every allocated subnet."""
    lines = [
        "! NetArchitect - generated Cisco IOS configuration",
        "! Review interface names, VLAN IDs and routing policy before deployment.",
        "configure terminal",
        "ip routing",
        "! VLAN interfaces and default gateways",
    ]
    for index, subnet in enumerate(allocations, start=1):
        vlan = _vlan_id(index)
        safe_name = re.sub(r"[^A-Za-z0-9_-]", "_", subnet["name"])[:40]
        lines.extend([
            f"vlan {vlan}",
            f" name {safe_name}",
            " exit",
            f"interface Vlan{vlan}",
            f" description {safe_name} default gateway",
            f" ip address {subnet['gateway']} {subnet['subnet_mask']}",
            " no shutdown",
            " exit",
        ])
    if routing["protocol"].startswith("Single-area OSPF") or routing["protocol"].startswith("Multi-area OSPF"):
        lines.extend(["router ospf 1", " router-id 1.1.1.1"])
        for subnet in allocations:
            lines.append(
                f" network {subnet['network']} {wildcard_mask(subnet['subnet_mask'])} area 0"
            )
        lines.extend([" exit"])
    else:
        lines.extend([
            "! Multisite design: configure OSPF process and eBGP peers per site policy.",
            "! Peer AS numbers and neighbor addresses are intentionally left as deployment inputs.",
        ])
    lines.extend([
        "! Example management ACL - replace the permitted source with the admin subnet.",
        "ip access-list standard NETARCHITECT-MGMT",
        f" permit {allocations[-1]['network']} {wildcard_mask(allocations[-1]['subnet_mask'])}",
        " deny any log",
        " exit",
        "end",
        "! end of generated example",
    ])
    return "\n".join(lines) + "\n"


PRESETS: dict[str, dict[str, Any]] = {
    "campus": {
        "description": "Campus LAN - academic, administration and shared services",
        "distance_m": 350,
        "root_cidr": "10.10.0.0/16",
        "subnets": {"STUDENTS": 500, "FACULTY": 250, "IOT": 200, "ADMIN": 100, "MANAGEMENT": 50},
        "is_multisite": False,
    },
    "metro": {
        "description": "Metro MAN - headquarters and two remote offices",
        "distance_m": 25000,
        "root_cidr": "10.20.0.0/16",
        "subnets": {"HQ_USERS": 200, "REMOTE_A": 100, "REMOTE_B": 100, "VOICE": 50, "MANAGEMENT": 30},
        "is_multisite": True,
    },
    "wan": {
        "description": "Global WAN - city IoT networks and cloud services",
        "distance_m": 500000,
        "root_cidr": "10.30.0.0/16",
        "subnets": {"CITY_A_IOT": 300, "CITY_B_IOT": 300, "CITY_C_IOT": 200, "CITY_D_IOT": 200, "CLOUD_SERVICES": 100},
        "is_multisite": True,
    },
}


def create_design(data: dict[str, Any], name: str = "Custom") -> dict[str, Any]:
    if not isinstance(data, dict):
        raise NetworkDesignError("Design input must be a JSON object.")
    try:
        distance = data["distance_m"]
        root_cidr = data["root_cidr"]
        subnet_requests = data["subnets"]
    except KeyError as exc:
        raise NetworkDesignError(f"Missing required design field: {exc.args[0]}") from exc

    allocations = VLSMEngine.allocate_subnets(root_cidr, subnet_requests)
    media = L1MediaEngine.evaluate_media(distance, data.get("force_copper", False))
    routing = RoutingEngine.evaluate_routing(len(allocations), bool(data.get("is_multisite", False)))
    return {
        "project": "NetArchitect",
        "scenario": name,
        "description": data.get("description", "Custom network design"),
        "inputs": {
            "distance_m": distance,
            "root_cidr": str(ipaddress.IPv4Network(root_cidr, strict=True)),
            "is_multisite": bool(data.get("is_multisite", False)),
        },
        "physical_layer": media,
        "routing": routing,
        "subnets": allocations,
        "ios_configuration": build_ios_config(allocations, routing),
    }


def export_design(design: dict[str, Any], output_dir: str | Path) -> tuple[Path, Path]:
    destination = Path(output_dir)
    destination.mkdir(parents=True, exist_ok=True)
    json_path = destination / "design.json"
    config_path = destination / "network_config.txt"
    json_path.write_text(json.dumps(design, indent=2) + "\n", encoding="utf-8")
    config_path.write_text(design["ios_configuration"], encoding="utf-8")
    return json_path, config_path


def print_design(design: dict[str, Any]) -> None:
    print(f"\n{'=' * 64}\nNetArchitect | {design['scenario']}\n{'=' * 64}")
    print(f"{design['description']}\n")
    print("[Layer 1 - Physical medium]")
    print(f"  {design['physical_layer']['media']}")
    print(f"  Why: {design['physical_layer']['rationale']}")
    print("\n[Layer 3 - Routing]")
    print(f"  {design['routing']['protocol']}")
    print(f"  Why: {design['routing']['rationale']}")
    print("\n[VLSM - Address plan]")
    for subnet in design["subnets"]:
        print(
            f"  {subnet['name']:<18} {subnet['network']}{subnet['cidr']:<5} "
            f"gateway {subnet['gateway']:<15} hosts {subnet['requested_hosts']}"
        )
    print("\n[IOS configuration]")
    print(design["ios_configuration"])


def load_json(path: str | Path) -> dict[str, Any]:
    try:
        with Path(path).open("r", encoding="utf-8") as file:
            return json.load(file)
    except FileNotFoundError as exc:
        raise NetworkDesignError(f"Cannot find input file: {path}") from exc
    except json.JSONDecodeError as exc:
        raise NetworkDesignError(f"Invalid JSON in {path}: {exc}") from exc


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="NetArchitect - explainable network planning and Cisco IOS export"
    )
    parser.add_argument("--profile", choices=["campus", "metro", "wan", "1", "2", "3"],
                        help="Run a built-in campus, metro or WAN scenario")
    parser.add_argument("--json", dest="json_path", help="Load a custom design JSON file")
    parser.add_argument("--out", default="exports", help="Directory for generated design files")
    args = parser.parse_args(argv)

    try:
        if args.profile:
            profile_name = {"1": "campus", "2": "metro", "3": "wan"}.get(args.profile, args.profile)
            design = create_design(PRESETS[profile_name], profile_name.upper())
            output_dir = Path(args.out) / profile_name
        elif args.json_path:
            design = create_design(load_json(args.json_path), Path(args.json_path).stem)
            output_dir = Path(args.out) / "custom"
        else:
            parser.error("Choose --profile campus|metro|wan or provide --json FILE.")

        print_design(design)
        json_file, config_file = export_design(design, output_dir)
        print(f"Saved design: {json_file}")
        print(f"Saved IOS config: {config_file}")
        return 0
    except (NetworkDesignError, OSError) as exc:
        parser.exit(2, f"NetArchitect error: {exc}\n")


if __name__ == "__main__":
    raise SystemExit(main())
