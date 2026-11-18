# NetArchitect — CIC-307 Computer Networks Mini-Project

NetArchitect is a Python command-line tool for planning small campus, metro and global WAN network scenarios. It turns a few design inputs into an explainable Layer 1 media recommendation, an IPv4 VLSM address plan, a routing recommendation and a sample Cisco IOS configuration.

## What it does

- **Physical media selection:** recommends Cat6a copper, OM4 multimode fibre or OS2 single-mode fibre from the link distance.
- **VLSM planning:** allocates the largest requested subnets first, calculates gateways, masks, broadcast addresses and address utilization, and reports address-space exhaustion.
- **Routing guidance:** suggests single-area OSPF for a small single-site design, multi-area OSPF for larger single-site designs, and OSPF/eBGP separation for multi-site designs.
- **Cisco IOS export:** creates example VLAN interfaces, gateway addresses, OSPF network statements and a sample management ACL.
- **Repeatable output:** writes a `design.json` summary and `network_config.txt` configuration file for each run.

## Setup (macOS / Linux)

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
```

## Run a built-in scenario

```bash
python -m pytest -q
python netarchitect.py --profile campus
python netarchitect.py --profile metro
python netarchitect.py --profile wan
```

Each built-in profile writes files under `exports/<profile>/` by default. To change the destination:

```bash
python netarchitect.py --profile campus --out my_exports
```

The numeric profile aliases `1`, `2` and `3` are retained for compatibility (`1=campus`, `2=metro`, `3=wan`).

## Run a custom design

Edit `custom.json` and run:

```bash
python netarchitect.py --json custom.json
```

Example input:

```json
{
  "description": "Warehouse and office network",
  "distance_m": 150,
  "root_cidr": "172.16.0.0/23",
  "subnets": {
    "Warehouse_Scanners": 200,
    "Office_Data": 100,
    "Security_Cameras": 50
  },
  "is_multisite": false
}
```

## Packet Tracer verification

The generated text file is a **Cisco IOS configuration example**, not a Packet Tracer `.pkt` topology. To verify it, create compatible switches/routers in Packet Tracer, map the generated VLAN IDs and SVI gateways to the devices, and adapt interface names and routing details to the selected device models. Then verify with commands such as:

```text
show vlan brief
show ip interface brief
show interfaces trunk
show ip route
show ip ospf neighbor
ping <destination-ip>
```

A failed ping is not automatically a VLSM failure. Check physical links, VLAN membership, trunk allowed-VLAN lists, SVI status, default gateways and routing adjacencies in that order.

## Project structure

```text
netArchitect_CN-main/
├── netarchitect.py        # planning engines, CLI and exporters
├── custom.json            # editable custom scenario
├── profile1_config.txt    # retained sample IOS output
├── profile2_config.txt    # retained sample IOS output
├── profile3_config.txt    # retained sample IOS output
├── test_netarchitect.py   # automated tests
├── requirements.txt
├── ai_audit_log.md        # validation notes and known design limitations
└── README.md
```

## Design notes and limitations

- VLSM uses the conventional two-address reservation for network and broadcast addresses; `/31` point-to-point allocation is not currently implemented.
- The routing result is a recommendation, not a complete multi-router routing design. eBGP peer ASNs and neighbor addresses must be supplied for a real deployment.
- The generated ACL is a starter example. Confirm which subnet is authorized for management before using it on a device.
- The generated VLAN numbering is illustrative. Check for conflicts with VLANs already present in the target network.
- Always review and test generated commands in a lab before applying them to production equipment.

## Development and validation

Run the automated test suite with `python -m pytest -q`. Tests cover media thresholds, forced-copper rejection, VLSM allocation and exhaustion, invalid inputs, wildcard masks, routing recommendations and configuration generation.
