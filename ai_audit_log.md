# NetArchitect — AI Assistance and Validation Notes

**Course:** CIC-307 Computer Networks Mini-Project  
**Project area:** network planning, IPv4 addressing and Cisco IOS configuration examples

This log records technical checks that should be understood and verified by the project team. AI-generated suggestions are treated as drafts; the tests and Packet Tracer lab checks are the validation steps.

## 1. IPv4 wildcard-mask conversion

**Risk:** Python integers are not limited to 32 bits. Applying the `~` operator directly to an IPv4 mask can produce a negative integer that cannot be represented as an IPv4 address.

**Implementation used:** `wildcard_mask()` converts the mask to an integer and XORs it with `0xFFFFFFFF`, limiting the inversion to 32 bits.

**Validation:** automated tests cover `/30`, `/24`, `/20` and `/32` masks.

## 2. VLSM allocation and address-space boundaries

**Risk:** allocating requested networks without sorting or checking the parent prefix can create overlapping ranges or run beyond the supplied address block.

**Implementation used:** requests are sorted from largest to smallest. Each block is aligned to its required size and checked against the end of the parent network before it is added to the plan.

**Validation:** tests check expected prefixes and gateways, non-overlap and parent-network exhaustion. Invalid host counts are rejected.

## 3. Copper distance constraint

**Risk:** selecting copper for a link longer than the 100m Ethernet channel limit can lead to unreliable connectivity.

**Implementation used:** Cat6a is recommended up to 100m; OM4 is selected above 100m through 400m; OS2 is selected for longer distances. An explicit forced-copper request above 100m raises an error.

**Validation:** tests cover all three media ranges and the forced-copper error.

## 4. Configuration export and deployment caution

**Risk:** a generated configuration may not match the exact Packet Tracer device model, existing VLAN plan, interface naming or routing policy.

**Implementation used:** exports include a review warning, VLAN/SVI examples, OSPF network statements for single-site OSPF designs and a clearly marked starter management ACL. Multi-site eBGP peer details are left as deployment inputs rather than fabricated.

**Validation still required:** load the commands into compatible Packet Tracer devices, check VLANs and trunks, confirm SVI state, inspect routing tables and OSPF neighbors, and test end-to-end pings. The exported text is not itself a `.pkt` topology.

## 5. Known limitations

- `/31` point-to-point subnet allocation is not supported; the allocator reserves network and broadcast addresses.
- Multi-site routing is a recommendation only; actual eBGP peers and AS numbers must be designed separately.
- The management ACL is a sample and must be reviewed against the intended administrator subnet.
- VLAN IDs and device interface names must be checked against the target topology.

## 6. Reproducible test command

```bash
python -m pytest -q
```
