# Manual / Integration Test Log

Manual, end-to-end tests run against a live network topology, as opposed to
the mocked unit tests covered by [`test-plan.md`](test-plan.md). These
exercise real reachability checks and the dashboard's live-update behavior,
which the unit suite deliberately does not (see `test-plan.md` §2,
"Out of scope").

## MT-01 — Live reachability status and auto-refresh (GNS3)

| Field | Value |
|---|---|
| Date | 2026-08-25 |
| Tester | mgaltherr |
| Environment | GNS3 topology (see below) |
| Related automated coverage | `test_reachability.py`, `test_dashboard.py` |

**Objective**

Verify that NOA correctly reports device reachability for real (non-mocked)
hosts, and that the dashboard's online/offline status updates automatically
in the browser as reachability changes, without a manual page refresh.

**Topology**

- L2 switch, with all nodes connected to it:
  - Ubuntu Cloud node
  - Ubuntu Desktop node
  - 2x vPCS nodes
  - NAT node (provides external/upstream connectivity)

**Steps**

1. Build the topology above in GNS3 and start all nodes.
2. Leave the two vPCS nodes powered off / not yet pingable.
3. Start NOA with the two vPCS IP addresses added to the monitored
   inventory.
4. Observe the NOA dashboard status for both vPCS devices.
5. Power on / bring up the vPCS nodes so they become pingable.
6. Without refreshing the browser, continue observing the NOA dashboard.

**Expected Result**

- At step 4, both vPCS devices show as **offline** in the dashboard.
- At step 6, both vPCS devices transition to **online** in the dashboard
  on their own, driven by NOA's polling, with no manual page refresh.

**Actual Result**

- Both vPCS devices showed **offline** while down, matching expectation.
- After bringing the vPCS nodes up, both devices showed **online** in the
  dashboard automatically, with no page refresh required.

**Verdict:** Pass
