# 📊 ANTA Report <a id="anta-report"></a>

**Table of Contents:**

- [ANTA Report](#anta-report)
  - [Test Results Summary](#test-results-summary)
    - [Summary Totals](#summary-totals)
    - [Summary Totals Device Under Test](#summary-totals-device-under-test)
    - [Summary Totals Per Category](#summary-totals-per-category)
  - [Test Results](#test-results)

## 📉 Test Results Summary <a id="test-results-summary"></a>

### 🔢 Summary Totals <a id="summary-totals"></a>

| Total Tests | ✅&nbsp;Success | ⏭️&nbsp;Skipped | ❌&nbsp;Failure | ❗&nbsp;Error |
| :- | :- | :- | :- | :- |
| 130 | 82 | 12 | 32 | 0 |

### 🔌 Summary Totals Device Under Test <a id="summary-totals-device-under-test"></a>

| Device | Total Tests | ✅&nbsp;Success | ⏭️&nbsp;Skipped | ❌&nbsp;Failure | ❗&nbsp;Error | Categories Skipped | Categories Failed |
| :- | :- | :- | :- | :- | :- | :- | :- |
| **dc1-leaf1** | 24 | 14 | 3 | 6 | 0 | MLAG, VXLAN | BGP, Connectivity, Interfaces, Routing |
| **dc1-leaf2** | 24 | 14 | 3 | 6 | 0 | MLAG, VXLAN | BGP, Connectivity, Interfaces, Routing |
| **dc1-leaf3** | 24 | 14 | 3 | 6 | 0 | MLAG, VXLAN | BGP, Connectivity, Interfaces, Routing |
| **dc1-leaf4** | 24 | 14 | 3 | 6 | 0 | MLAG, VXLAN | BGP, Connectivity, Interfaces, Routing |
| **dc1-spine1** | 17 | 13 | 0 | 4 | 0 | - | BGP, Connectivity, Interfaces |
| **dc1-spine2** | 17 | 13 | 0 | 4 | 0 | - | BGP, Connectivity, Interfaces |

### 🗂️ Summary Totals Per Category <a id="summary-totals-per-category"></a>

| Test Category | Total Tests | ✅&nbsp;Success | ⏭️&nbsp;Skipped | ❌&nbsp;Failure | ❗&nbsp;Error |
| :- | :- | :- | :- | :- | :- |
| **BGP** | 6 | 0 | 0 | 6 | 0 |
| **Configuration** | 6 | 6 | 0 | 0 | 0 |
| **Connectivity** | 22 | 6 | 0 | 16 | 0 |
| **Interfaces** | 32 | 22 | 0 | 6 | 0 |
| **MLAG** | 8 | 0 | 8 | 0 | 0 |
| **Routing** | 10 | 6 | 0 | 4 | 0 |
| **STP** | 6 | 6 | 0 | 0 | 0 |
| **System** | 36 | 36 | 0 | 0 | 0 |
| **VXLAN** | 4 | 0 | 4 | 0 | 0 |

## 🧪 Test Results <a id="test-results"></a>

| Device | Categories | Test | Description | Result | Messages |
| :- | :- | :- | :- | :- | :- |
| dc1-leaf1 | BGP | VerifyBGPPeerSession | Verifies the session state of BGP peers. | ❌&nbsp;Failure | 'show bgp neighbors vrf all' failed on dc1-leaf1: BGP inactive |
| dc1-leaf1 | Connectivity | VerifyReachability | Verifies VTEP fabric-wide underlay reachability. | ❌&nbsp;Failure | Destination 10.99.1.2 (dc1-leaf2) from 10.99.1.1 in VRF default - Error when executing ping: 'ping: bind: Cannot assign requested address'<br>Destination 10.99.1.3 (dc1-leaf3) from 10.99.1.1 in VRF default - Error when executing ping: 'ping: bind: Cannot assign requested address'<br>Destination 10.99.1.4 (dc1-leaf4) from 10.99.1.1 in VRF default - Error when executing ping: 'ping: bind: Cannot assign requested address'<br>Destination 10.99.1.129 (dc1-spine1) from 10.99.1.1 in VRF default - Error when executing ping: 'ping: bind: Cannot assign requested address'<br>Destination 10.99.1.130 (dc1-spine2) from 10.99.1.1 in VRF default - Error when executing ping: 'ping: bind: Cannot assign requested address' |
| dc1-leaf1 | Connectivity | VerifyReachability | Verifies point-to-point reachability between Ethernet interfaces. | ❌&nbsp;Failure | Destination 10.101.0.0 (dc1-spine1_Ethernet1/1) from 10.101.0.1 in VRF default - Error when executing ping: 'ping: bind: Cannot assign requested address'<br>Destination 10.101.0.2 (dc1-spine2_Ethernet1/1) from 10.101.0.3 in VRF default - Error when executing ping: 'ping: bind: Cannot assign requested address' |
| dc1-leaf1 | Connectivity | VerifyReachability | Verifies reachability to BGP neighbors. | ❌&nbsp;Failure | 'ping vrf default 10.99.1.129 source Loopback0 size 100 repeat 1' failed on dc1-leaf1: No source interface Loopback0<br>'ping vrf default 10.99.1.130 source Loopback0 size 100 repeat 1' failed on dc1-leaf1: No source interface Loopback0<br>'ping vrf BLUE 10.101.254.1 size 100 repeat 1' failed on dc1-leaf1: VRF 'BLUE' is not active<br>'ping vrf GREEN 10.101.254.1 size 100 repeat 1' failed on dc1-leaf1: VRF 'GREEN' is not active |
| dc1-leaf1 | Interfaces | VerifyInterfacesStatus | Verifies the operational states of specified interfaces to ensure they match expected configurations. | ❌&nbsp;Failure | Interface: Loopback0 - Not configured<br>Interface: Loopback1 - Not configured<br>Interface: Port-Channel511 - Not configured<br>Interface: Vlan100 - Not configured<br>Interface: Vlan200 - Not configured<br>Interface: Vlan3500 - Not configured<br>Interface: Vlan3501 - Not configured<br>Interface: Vlan4093 - Not configured<br>Interface: Vlan4094 - Not configured<br>Interface: Vxlan1 - Not configured |
| dc1-leaf1 | Routing | VerifyIPv4RoutePresencePerVRF | Verifies that the provided IPv4 prefixes are present in the routing table. | ❌&nbsp;Failure | Prefix: 10.99.1.1/32 VRF: default - Route not found<br>Prefix: 10.99.1.2/32 VRF: default - Route not found<br>Prefix: 10.99.1.3/32 VRF: default - Route not found<br>Prefix: 10.99.1.4/32 VRF: default - Route not found<br>Prefix: 10.99.1.129/32 VRF: default - Route not found<br>Prefix: 10.99.1.130/32 VRF: default - Route not found<br>Prefix: 10.101.1.1/32 VRF: default - Route not found<br>Prefix: 10.101.1.3/32 VRF: default - Route not found |
| dc1-leaf2 | BGP | VerifyBGPPeerSession | Verifies the session state of BGP peers. | ❌&nbsp;Failure | 'show bgp neighbors vrf all' failed on dc1-leaf2: BGP inactive |
| dc1-leaf2 | Connectivity | VerifyReachability | Verifies VTEP fabric-wide underlay reachability. | ❌&nbsp;Failure | Destination 10.99.1.1 (dc1-leaf1) from 10.99.1.2 in VRF default - Error when executing ping: 'ping: bind: Cannot assign requested address'<br>Destination 10.99.1.3 (dc1-leaf3) from 10.99.1.2 in VRF default - Error when executing ping: 'ping: bind: Cannot assign requested address'<br>Destination 10.99.1.4 (dc1-leaf4) from 10.99.1.2 in VRF default - Error when executing ping: 'ping: bind: Cannot assign requested address'<br>Destination 10.99.1.129 (dc1-spine1) from 10.99.1.2 in VRF default - Error when executing ping: 'ping: bind: Cannot assign requested address'<br>Destination 10.99.1.130 (dc1-spine2) from 10.99.1.2 in VRF default - Error when executing ping: 'ping: bind: Cannot assign requested address' |
| dc1-leaf2 | Connectivity | VerifyReachability | Verifies point-to-point reachability between Ethernet interfaces. | ❌&nbsp;Failure | Destination 10.101.0.4 (dc1-spine1_Ethernet1/2) from 10.101.0.5 in VRF default - Error when executing ping: 'ping: bind: Cannot assign requested address'<br>Destination 10.101.0.6 (dc1-spine2_Ethernet1/2) from 10.101.0.7 in VRF default - Error when executing ping: 'ping: bind: Cannot assign requested address' |
| dc1-leaf2 | Connectivity | VerifyReachability | Verifies reachability to BGP neighbors. | ❌&nbsp;Failure | 'ping vrf default 10.99.1.129 source Loopback0 size 100 repeat 1' failed on dc1-leaf2: No source interface Loopback0<br>'ping vrf default 10.99.1.130 source Loopback0 size 100 repeat 1' failed on dc1-leaf2: No source interface Loopback0<br>'ping vrf BLUE 10.101.254.0 size 100 repeat 1' failed on dc1-leaf2: VRF 'BLUE' is not active<br>'ping vrf GREEN 10.101.254.0 size 100 repeat 1' failed on dc1-leaf2: VRF 'GREEN' is not active |
| dc1-leaf2 | Interfaces | VerifyInterfacesStatus | Verifies the operational states of specified interfaces to ensure they match expected configurations. | ❌&nbsp;Failure | Interface: Loopback0 - Not configured<br>Interface: Loopback1 - Not configured<br>Interface: Port-Channel511 - Not configured<br>Interface: Vlan100 - Not configured<br>Interface: Vlan200 - Not configured<br>Interface: Vlan3500 - Not configured<br>Interface: Vlan3501 - Not configured<br>Interface: Vlan4093 - Not configured<br>Interface: Vlan4094 - Not configured<br>Interface: Vxlan1 - Not configured |
| dc1-leaf2 | Routing | VerifyIPv4RoutePresencePerVRF | Verifies that the provided IPv4 prefixes are present in the routing table. | ❌&nbsp;Failure | Prefix: 10.99.1.1/32 VRF: default - Route not found<br>Prefix: 10.99.1.2/32 VRF: default - Route not found<br>Prefix: 10.99.1.3/32 VRF: default - Route not found<br>Prefix: 10.99.1.4/32 VRF: default - Route not found<br>Prefix: 10.99.1.129/32 VRF: default - Route not found<br>Prefix: 10.99.1.130/32 VRF: default - Route not found<br>Prefix: 10.101.1.1/32 VRF: default - Route not found<br>Prefix: 10.101.1.3/32 VRF: default - Route not found |
| dc1-leaf3 | BGP | VerifyBGPPeerSession | Verifies the session state of BGP peers. | ❌&nbsp;Failure | 'show bgp neighbors vrf all' failed on dc1-leaf3: BGP inactive |
| dc1-leaf3 | Connectivity | VerifyReachability | Verifies VTEP fabric-wide underlay reachability. | ❌&nbsp;Failure | Destination 10.99.1.1 (dc1-leaf1) from 10.99.1.3 in VRF default - Error when executing ping: 'ping: bind: Cannot assign requested address'<br>Destination 10.99.1.2 (dc1-leaf2) from 10.99.1.3 in VRF default - Error when executing ping: 'ping: bind: Cannot assign requested address'<br>Destination 10.99.1.4 (dc1-leaf4) from 10.99.1.3 in VRF default - Error when executing ping: 'ping: bind: Cannot assign requested address'<br>Destination 10.99.1.129 (dc1-spine1) from 10.99.1.3 in VRF default - Error when executing ping: 'ping: bind: Cannot assign requested address'<br>Destination 10.99.1.130 (dc1-spine2) from 10.99.1.3 in VRF default - Error when executing ping: 'ping: bind: Cannot assign requested address' |
| dc1-leaf3 | Connectivity | VerifyReachability | Verifies point-to-point reachability between Ethernet interfaces. | ❌&nbsp;Failure | Destination 10.101.0.8 (dc1-spine1_Ethernet1/3) from 10.101.0.9 in VRF default - Error when executing ping: 'ping: bind: Cannot assign requested address'<br>Destination 10.101.0.10 (dc1-spine2_Ethernet1/3) from 10.101.0.11 in VRF default - Error when executing ping: 'ping: bind: Cannot assign requested address' |
| dc1-leaf3 | Connectivity | VerifyReachability | Verifies reachability to BGP neighbors. | ❌&nbsp;Failure | 'ping vrf default 10.99.1.129 source Loopback0 size 100 repeat 1' failed on dc1-leaf3: No source interface Loopback0<br>'ping vrf default 10.99.1.130 source Loopback0 size 100 repeat 1' failed on dc1-leaf3: No source interface Loopback0<br>'ping vrf BLUE 10.101.254.1 size 100 repeat 1' failed on dc1-leaf3: VRF 'BLUE' is not active<br>'ping vrf GREEN 10.101.254.1 size 100 repeat 1' failed on dc1-leaf3: VRF 'GREEN' is not active |
| dc1-leaf3 | Interfaces | VerifyInterfacesStatus | Verifies the operational states of specified interfaces to ensure they match expected configurations. | ❌&nbsp;Failure | Interface: Loopback0 - Not configured<br>Interface: Loopback1 - Not configured<br>Interface: Port-Channel511 - Not configured<br>Interface: Vlan100 - Not configured<br>Interface: Vlan200 - Not configured<br>Interface: Vlan3500 - Not configured<br>Interface: Vlan3501 - Not configured<br>Interface: Vlan4093 - Not configured<br>Interface: Vlan4094 - Not configured<br>Interface: Vxlan1 - Not configured |
| dc1-leaf3 | Routing | VerifyIPv4RoutePresencePerVRF | Verifies that the provided IPv4 prefixes are present in the routing table. | ❌&nbsp;Failure | Prefix: 10.99.1.1/32 VRF: default - Route not found<br>Prefix: 10.99.1.2/32 VRF: default - Route not found<br>Prefix: 10.99.1.3/32 VRF: default - Route not found<br>Prefix: 10.99.1.4/32 VRF: default - Route not found<br>Prefix: 10.99.1.129/32 VRF: default - Route not found<br>Prefix: 10.99.1.130/32 VRF: default - Route not found<br>Prefix: 10.101.1.1/32 VRF: default - Route not found<br>Prefix: 10.101.1.3/32 VRF: default - Route not found |
| dc1-leaf4 | BGP | VerifyBGPPeerSession | Verifies the session state of BGP peers. | ❌&nbsp;Failure | 'show bgp neighbors vrf all' failed on dc1-leaf4: BGP inactive |
| dc1-leaf4 | Connectivity | VerifyReachability | Verifies VTEP fabric-wide underlay reachability. | ❌&nbsp;Failure | Destination 10.99.1.1 (dc1-leaf1) from 10.99.1.4 in VRF default - Error when executing ping: 'ping: bind: Cannot assign requested address'<br>Destination 10.99.1.2 (dc1-leaf2) from 10.99.1.4 in VRF default - Error when executing ping: 'ping: bind: Cannot assign requested address'<br>Destination 10.99.1.3 (dc1-leaf3) from 10.99.1.4 in VRF default - Error when executing ping: 'ping: bind: Cannot assign requested address'<br>Destination 10.99.1.129 (dc1-spine1) from 10.99.1.4 in VRF default - Error when executing ping: 'ping: bind: Cannot assign requested address'<br>Destination 10.99.1.130 (dc1-spine2) from 10.99.1.4 in VRF default - Error when executing ping: 'ping: bind: Cannot assign requested address' |
| dc1-leaf4 | Connectivity | VerifyReachability | Verifies point-to-point reachability between Ethernet interfaces. | ❌&nbsp;Failure | Destination 10.101.0.12 (dc1-spine1_Ethernet1/4) from 10.101.0.13 in VRF default - Error when executing ping: 'ping: bind: Cannot assign requested address'<br>Destination 10.101.0.14 (dc1-spine2_Ethernet1/4) from 10.101.0.15 in VRF default - Error when executing ping: 'ping: bind: Cannot assign requested address' |
| dc1-leaf4 | Connectivity | VerifyReachability | Verifies reachability to BGP neighbors. | ❌&nbsp;Failure | 'ping vrf default 10.99.1.129 source Loopback0 size 100 repeat 1' failed on dc1-leaf4: No source interface Loopback0<br>'ping vrf default 10.99.1.130 source Loopback0 size 100 repeat 1' failed on dc1-leaf4: No source interface Loopback0<br>'ping vrf BLUE 10.101.254.0 size 100 repeat 1' failed on dc1-leaf4: VRF 'BLUE' is not active<br>'ping vrf GREEN 10.101.254.0 size 100 repeat 1' failed on dc1-leaf4: VRF 'GREEN' is not active |
| dc1-leaf4 | Interfaces | VerifyInterfacesStatus | Verifies the operational states of specified interfaces to ensure they match expected configurations. | ❌&nbsp;Failure | Interface: Loopback0 - Not configured<br>Interface: Loopback1 - Not configured<br>Interface: Port-Channel511 - Not configured<br>Interface: Vlan100 - Not configured<br>Interface: Vlan200 - Not configured<br>Interface: Vlan3500 - Not configured<br>Interface: Vlan3501 - Not configured<br>Interface: Vlan4093 - Not configured<br>Interface: Vlan4094 - Not configured<br>Interface: Vxlan1 - Not configured |
| dc1-leaf4 | Routing | VerifyIPv4RoutePresencePerVRF | Verifies that the provided IPv4 prefixes are present in the routing table. | ❌&nbsp;Failure | Prefix: 10.99.1.1/32 VRF: default - Route not found<br>Prefix: 10.99.1.2/32 VRF: default - Route not found<br>Prefix: 10.99.1.3/32 VRF: default - Route not found<br>Prefix: 10.99.1.4/32 VRF: default - Route not found<br>Prefix: 10.99.1.129/32 VRF: default - Route not found<br>Prefix: 10.99.1.130/32 VRF: default - Route not found<br>Prefix: 10.101.1.1/32 VRF: default - Route not found<br>Prefix: 10.101.1.3/32 VRF: default - Route not found |
| dc1-spine1 | BGP | VerifyBGPPeerSession | Verifies the session state of BGP peers. | ❌&nbsp;Failure | 'show bgp neighbors vrf all' failed on dc1-spine1: BGP inactive |
| dc1-spine1 | Connectivity | VerifyReachability | Verifies point-to-point reachability between Ethernet interfaces. | ❌&nbsp;Failure | Destination 10.101.0.1 (dc1-leaf1_Ethernet49/1) from 10.101.0.0 in VRF default - Error when executing ping: 'ping: bind: Cannot assign requested address'<br>Destination 10.101.0.5 (dc1-leaf2_Ethernet49/1) from 10.101.0.4 in VRF default - Error when executing ping: 'ping: bind: Cannot assign requested address'<br>Destination 10.101.0.9 (dc1-leaf3_Ethernet49/1) from 10.101.0.8 in VRF default - Error when executing ping: 'ping: bind: Cannot assign requested address'<br>Destination 10.101.0.13 (dc1-leaf4_Ethernet49/1) from 10.101.0.12 in VRF default - Error when executing ping: 'ping: bind: Cannot assign requested address' |
| dc1-spine1 | Connectivity | VerifyReachability | Verifies reachability to BGP neighbors. | ❌&nbsp;Failure | 'ping vrf default 10.99.1.1 source Loopback0 size 100 repeat 1' failed on dc1-spine1: No source interface Loopback0<br>'ping vrf default 10.99.1.2 source Loopback0 size 100 repeat 1' failed on dc1-spine1: No source interface Loopback0<br>'ping vrf default 10.99.1.3 source Loopback0 size 100 repeat 1' failed on dc1-spine1: No source interface Loopback0<br>'ping vrf default 10.99.1.4 source Loopback0 size 100 repeat 1' failed on dc1-spine1: No source interface Loopback0 |
| dc1-spine1 | Interfaces | VerifyInterfacesStatus | Verifies the operational states of specified interfaces to ensure they match expected configurations. | ❌&nbsp;Failure | Interface: Loopback0 - Not configured |
| dc1-spine2 | BGP | VerifyBGPPeerSession | Verifies the session state of BGP peers. | ❌&nbsp;Failure | 'show bgp neighbors vrf all' failed on dc1-spine2: BGP inactive |
| dc1-spine2 | Connectivity | VerifyReachability | Verifies point-to-point reachability between Ethernet interfaces. | ❌&nbsp;Failure | Destination 10.101.0.3 (dc1-leaf1_Ethernet50/1) from 10.101.0.2 in VRF default - Error when executing ping: 'ping: bind: Cannot assign requested address'<br>Destination 10.101.0.7 (dc1-leaf2_Ethernet50/1) from 10.101.0.6 in VRF default - Error when executing ping: 'ping: bind: Cannot assign requested address'<br>Destination 10.101.0.11 (dc1-leaf3_Ethernet50/1) from 10.101.0.10 in VRF default - Error when executing ping: 'ping: bind: Cannot assign requested address'<br>Destination 10.101.0.15 (dc1-leaf4_Ethernet50/1) from 10.101.0.14 in VRF default - Error when executing ping: 'ping: bind: Cannot assign requested address' |
| dc1-spine2 | Connectivity | VerifyReachability | Verifies reachability to BGP neighbors. | ❌&nbsp;Failure | 'ping vrf default 10.99.1.1 source Loopback0 size 100 repeat 1' failed on dc1-spine2: No source interface Loopback0<br>'ping vrf default 10.99.1.2 source Loopback0 size 100 repeat 1' failed on dc1-spine2: No source interface Loopback0<br>'ping vrf default 10.99.1.3 source Loopback0 size 100 repeat 1' failed on dc1-spine2: No source interface Loopback0<br>'ping vrf default 10.99.1.4 source Loopback0 size 100 repeat 1' failed on dc1-spine2: No source interface Loopback0 |
| dc1-spine2 | Interfaces | VerifyInterfacesStatus | Verifies the operational states of specified interfaces to ensure they match expected configurations. | ❌&nbsp;Failure | Interface: Loopback0 - Not configured |
| dc1-leaf1 | MLAG | VerifyMlagConfigSanity | Verifies there are no MLAG config-sanity inconsistencies. | ⏭️&nbsp;Skipped | MLAG is disabled |
| dc1-leaf1 | MLAG | VerifyMlagStatus | Verifies the health status of the MLAG configuration. | ⏭️&nbsp;Skipped | MLAG is disabled |
| dc1-leaf1 | VXLAN | VerifyVxlanConfigSanity | Verifies there are no VXLAN config-sanity inconsistencies. | ⏭️&nbsp;Skipped | VXLAN is not configured |
| dc1-leaf2 | MLAG | VerifyMlagConfigSanity | Verifies there are no MLAG config-sanity inconsistencies. | ⏭️&nbsp;Skipped | MLAG is disabled |
| dc1-leaf2 | MLAG | VerifyMlagStatus | Verifies the health status of the MLAG configuration. | ⏭️&nbsp;Skipped | MLAG is disabled |
| dc1-leaf2 | VXLAN | VerifyVxlanConfigSanity | Verifies there are no VXLAN config-sanity inconsistencies. | ⏭️&nbsp;Skipped | VXLAN is not configured |
| dc1-leaf3 | MLAG | VerifyMlagConfigSanity | Verifies there are no MLAG config-sanity inconsistencies. | ⏭️&nbsp;Skipped | MLAG is disabled |
| dc1-leaf3 | MLAG | VerifyMlagStatus | Verifies the health status of the MLAG configuration. | ⏭️&nbsp;Skipped | MLAG is disabled |
| dc1-leaf3 | VXLAN | VerifyVxlanConfigSanity | Verifies there are no VXLAN config-sanity inconsistencies. | ⏭️&nbsp;Skipped | VXLAN is not configured |
| dc1-leaf4 | MLAG | VerifyMlagConfigSanity | Verifies there are no MLAG config-sanity inconsistencies. | ⏭️&nbsp;Skipped | MLAG is disabled |
| dc1-leaf4 | MLAG | VerifyMlagStatus | Verifies the health status of the MLAG configuration. | ⏭️&nbsp;Skipped | MLAG is disabled |
| dc1-leaf4 | VXLAN | VerifyVxlanConfigSanity | Verifies there are no VXLAN config-sanity inconsistencies. | ⏭️&nbsp;Skipped | VXLAN is not configured |
| dc1-leaf1 | Configuration | VerifyZeroTouch | Verifies ZeroTouch is disabled. | ✅&nbsp;Success | - |
| dc1-leaf1 | Connectivity | VerifyLLDPNeighbors | Verifies the connection status of the specified LLDP (Link Layer Discovery Protocol) neighbors. | ✅&nbsp;Success | - |
| dc1-leaf1 | Interfaces | VerifyIllegalLACP | Verifies there are no illegal LACP packets in port channels. | ✅&nbsp;Success | - |
| dc1-leaf1 | Interfaces | VerifyInterfaceErrDisabled | Verifies there are no interfaces in the errdisabled state. | ✅&nbsp;Success | - |
| dc1-leaf1 | Interfaces | VerifyInterfaceErrors | Verifies that the interfaces error counters are equal to zero. | ✅&nbsp;Success | - |
| dc1-leaf1 | Interfaces | VerifyInterfaceUtilization | Verifies that the utilization of interfaces is below a certain threshold. | ✅&nbsp;Success | - |
| dc1-leaf1 | Routing | VerifyRoutingProtocolModel | Verifies the configured routing protocol model. | ✅&nbsp;Success | - |
| dc1-leaf1 | STP | VerifySTPCounters | Verifies there is no errors in STP BPDU packets. | ✅&nbsp;Success | - |
| dc1-leaf1 | System | VerifyAgentLogs | Verifies there are no agent crash reports. | ✅&nbsp;Success | - |
| dc1-leaf1 | System | VerifyCoredump | Verifies there are no core dump files. | ✅&nbsp;Success | - |
| dc1-leaf1 | System | VerifyFileSystemUtilization | Verifies that no partition is utilizing more than 75% of its disk space. | ✅&nbsp;Success | - |
| dc1-leaf1 | System | VerifyMaintenance | Verifies that the device is not currently under or entering maintenance. | ✅&nbsp;Success | - |
| dc1-leaf1 | System | VerifyMemoryUtilization | Verifies whether the memory utilization is below 75%. | ✅&nbsp;Success | - |
| dc1-leaf1 | System | VerifyReloadCause | Verifies the last reload cause of the device. | ✅&nbsp;Success | - |
| dc1-leaf2 | Configuration | VerifyZeroTouch | Verifies ZeroTouch is disabled. | ✅&nbsp;Success | - |
| dc1-leaf2 | Connectivity | VerifyLLDPNeighbors | Verifies the connection status of the specified LLDP (Link Layer Discovery Protocol) neighbors. | ✅&nbsp;Success | - |
| dc1-leaf2 | Interfaces | VerifyIllegalLACP | Verifies there are no illegal LACP packets in port channels. | ✅&nbsp;Success | - |
| dc1-leaf2 | Interfaces | VerifyInterfaceErrDisabled | Verifies there are no interfaces in the errdisabled state. | ✅&nbsp;Success | - |
| dc1-leaf2 | Interfaces | VerifyInterfaceErrors | Verifies that the interfaces error counters are equal to zero. | ✅&nbsp;Success | - |
| dc1-leaf2 | Interfaces | VerifyInterfaceUtilization | Verifies that the utilization of interfaces is below a certain threshold. | ✅&nbsp;Success | - |
| dc1-leaf2 | Routing | VerifyRoutingProtocolModel | Verifies the configured routing protocol model. | ✅&nbsp;Success | - |
| dc1-leaf2 | STP | VerifySTPCounters | Verifies there is no errors in STP BPDU packets. | ✅&nbsp;Success | - |
| dc1-leaf2 | System | VerifyAgentLogs | Verifies there are no agent crash reports. | ✅&nbsp;Success | - |
| dc1-leaf2 | System | VerifyCoredump | Verifies there are no core dump files. | ✅&nbsp;Success | - |
| dc1-leaf2 | System | VerifyFileSystemUtilization | Verifies that no partition is utilizing more than 75% of its disk space. | ✅&nbsp;Success | - |
| dc1-leaf2 | System | VerifyMaintenance | Verifies that the device is not currently under or entering maintenance. | ✅&nbsp;Success | - |
| dc1-leaf2 | System | VerifyMemoryUtilization | Verifies whether the memory utilization is below 75%. | ✅&nbsp;Success | - |
| dc1-leaf2 | System | VerifyReloadCause | Verifies the last reload cause of the device. | ✅&nbsp;Success | - |
| dc1-leaf3 | Configuration | VerifyZeroTouch | Verifies ZeroTouch is disabled. | ✅&nbsp;Success | - |
| dc1-leaf3 | Connectivity | VerifyLLDPNeighbors | Verifies the connection status of the specified LLDP (Link Layer Discovery Protocol) neighbors. | ✅&nbsp;Success | - |
| dc1-leaf3 | Interfaces | VerifyIllegalLACP | Verifies there are no illegal LACP packets in port channels. | ✅&nbsp;Success | - |
| dc1-leaf3 | Interfaces | VerifyInterfaceErrDisabled | Verifies there are no interfaces in the errdisabled state. | ✅&nbsp;Success | - |
| dc1-leaf3 | Interfaces | VerifyInterfaceErrors | Verifies that the interfaces error counters are equal to zero. | ✅&nbsp;Success | - |
| dc1-leaf3 | Interfaces | VerifyInterfaceUtilization | Verifies that the utilization of interfaces is below a certain threshold. | ✅&nbsp;Success | - |
| dc1-leaf3 | Routing | VerifyRoutingProtocolModel | Verifies the configured routing protocol model. | ✅&nbsp;Success | - |
| dc1-leaf3 | STP | VerifySTPCounters | Verifies there is no errors in STP BPDU packets. | ✅&nbsp;Success | - |
| dc1-leaf3 | System | VerifyAgentLogs | Verifies there are no agent crash reports. | ✅&nbsp;Success | - |
| dc1-leaf3 | System | VerifyCoredump | Verifies there are no core dump files. | ✅&nbsp;Success | - |
| dc1-leaf3 | System | VerifyFileSystemUtilization | Verifies that no partition is utilizing more than 75% of its disk space. | ✅&nbsp;Success | - |
| dc1-leaf3 | System | VerifyMaintenance | Verifies that the device is not currently under or entering maintenance. | ✅&nbsp;Success | - |
| dc1-leaf3 | System | VerifyMemoryUtilization | Verifies whether the memory utilization is below 75%. | ✅&nbsp;Success | - |
| dc1-leaf3 | System | VerifyReloadCause | Verifies the last reload cause of the device. | ✅&nbsp;Success | - |
| dc1-leaf4 | Configuration | VerifyZeroTouch | Verifies ZeroTouch is disabled. | ✅&nbsp;Success | - |
| dc1-leaf4 | Connectivity | VerifyLLDPNeighbors | Verifies the connection status of the specified LLDP (Link Layer Discovery Protocol) neighbors. | ✅&nbsp;Success | - |
| dc1-leaf4 | Interfaces | VerifyIllegalLACP | Verifies there are no illegal LACP packets in port channels. | ✅&nbsp;Success | - |
| dc1-leaf4 | Interfaces | VerifyInterfaceErrDisabled | Verifies there are no interfaces in the errdisabled state. | ✅&nbsp;Success | - |
| dc1-leaf4 | Interfaces | VerifyInterfaceErrors | Verifies that the interfaces error counters are equal to zero. | ✅&nbsp;Success | - |
| dc1-leaf4 | Interfaces | VerifyInterfaceUtilization | Verifies that the utilization of interfaces is below a certain threshold. | ✅&nbsp;Success | - |
| dc1-leaf4 | Routing | VerifyRoutingProtocolModel | Verifies the configured routing protocol model. | ✅&nbsp;Success | - |
| dc1-leaf4 | STP | VerifySTPCounters | Verifies there is no errors in STP BPDU packets. | ✅&nbsp;Success | - |
| dc1-leaf4 | System | VerifyAgentLogs | Verifies there are no agent crash reports. | ✅&nbsp;Success | - |
| dc1-leaf4 | System | VerifyCoredump | Verifies there are no core dump files. | ✅&nbsp;Success | - |
| dc1-leaf4 | System | VerifyFileSystemUtilization | Verifies that no partition is utilizing more than 75% of its disk space. | ✅&nbsp;Success | - |
| dc1-leaf4 | System | VerifyMaintenance | Verifies that the device is not currently under or entering maintenance. | ✅&nbsp;Success | - |
| dc1-leaf4 | System | VerifyMemoryUtilization | Verifies whether the memory utilization is below 75%. | ✅&nbsp;Success | - |
| dc1-leaf4 | System | VerifyReloadCause | Verifies the last reload cause of the device. | ✅&nbsp;Success | - |
| dc1-spine1 | Configuration | VerifyZeroTouch | Verifies ZeroTouch is disabled. | ✅&nbsp;Success | - |
| dc1-spine1 | Connectivity | VerifyLLDPNeighbors | Verifies the connection status of the specified LLDP (Link Layer Discovery Protocol) neighbors. | ✅&nbsp;Success | - |
| dc1-spine1 | Interfaces | VerifyInterfaceErrDisabled | Verifies there are no interfaces in the errdisabled state. | ✅&nbsp;Success | - |
| dc1-spine1 | Interfaces | VerifyInterfaceErrors | Verifies that the interfaces error counters are equal to zero. | ✅&nbsp;Success | - |
| dc1-spine1 | Interfaces | VerifyInterfaceUtilization | Verifies that the utilization of interfaces is below a certain threshold. | ✅&nbsp;Success | - |
| dc1-spine1 | Routing | VerifyRoutingProtocolModel | Verifies the configured routing protocol model. | ✅&nbsp;Success | - |
| dc1-spine1 | STP | VerifySTPCounters | Verifies there is no errors in STP BPDU packets. | ✅&nbsp;Success | - |
| dc1-spine1 | System | VerifyAgentLogs | Verifies there are no agent crash reports. | ✅&nbsp;Success | - |
| dc1-spine1 | System | VerifyCoredump | Verifies there are no core dump files. | ✅&nbsp;Success | - |
| dc1-spine1 | System | VerifyFileSystemUtilization | Verifies that no partition is utilizing more than 75% of its disk space. | ✅&nbsp;Success | - |
| dc1-spine1 | System | VerifyMaintenance | Verifies that the device is not currently under or entering maintenance. | ✅&nbsp;Success | - |
| dc1-spine1 | System | VerifyMemoryUtilization | Verifies whether the memory utilization is below 75%. | ✅&nbsp;Success | - |
| dc1-spine1 | System | VerifyReloadCause | Verifies the last reload cause of the device. | ✅&nbsp;Success | - |
| dc1-spine2 | Configuration | VerifyZeroTouch | Verifies ZeroTouch is disabled. | ✅&nbsp;Success | - |
| dc1-spine2 | Connectivity | VerifyLLDPNeighbors | Verifies the connection status of the specified LLDP (Link Layer Discovery Protocol) neighbors. | ✅&nbsp;Success | - |
| dc1-spine2 | Interfaces | VerifyInterfaceErrDisabled | Verifies there are no interfaces in the errdisabled state. | ✅&nbsp;Success | - |
| dc1-spine2 | Interfaces | VerifyInterfaceErrors | Verifies that the interfaces error counters are equal to zero. | ✅&nbsp;Success | - |
| dc1-spine2 | Interfaces | VerifyInterfaceUtilization | Verifies that the utilization of interfaces is below a certain threshold. | ✅&nbsp;Success | - |
| dc1-spine2 | Routing | VerifyRoutingProtocolModel | Verifies the configured routing protocol model. | ✅&nbsp;Success | - |
| dc1-spine2 | STP | VerifySTPCounters | Verifies there is no errors in STP BPDU packets. | ✅&nbsp;Success | - |
| dc1-spine2 | System | VerifyAgentLogs | Verifies there are no agent crash reports. | ✅&nbsp;Success | - |
| dc1-spine2 | System | VerifyCoredump | Verifies there are no core dump files. | ✅&nbsp;Success | - |
| dc1-spine2 | System | VerifyFileSystemUtilization | Verifies that no partition is utilizing more than 75% of its disk space. | ✅&nbsp;Success | - |
| dc1-spine2 | System | VerifyMaintenance | Verifies that the device is not currently under or entering maintenance. | ✅&nbsp;Success | - |
| dc1-spine2 | System | VerifyMemoryUtilization | Verifies whether the memory utilization is below 75%. | ✅&nbsp;Success | - |
| dc1-spine2 | System | VerifyReloadCause | Verifies the last reload cause of the device. | ✅&nbsp;Success | - |
| dc1-leaf1 | Interfaces | VerifyPortChannels | Verifies there are no inactive ports in port channels. | Unset | - |
| dc1-leaf2 | Interfaces | VerifyPortChannels | Verifies there are no inactive ports in port channels. | Unset | - |
| dc1-leaf3 | Interfaces | VerifyPortChannels | Verifies there are no inactive ports in port channels. | Unset | - |
| dc1-leaf4 | Interfaces | VerifyPortChannels | Verifies there are no inactive ports in port channels. | Unset | - |
