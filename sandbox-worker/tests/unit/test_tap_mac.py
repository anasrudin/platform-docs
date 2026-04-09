"""Unit tests for TAP device naming and deterministic MAC generation."""

from __future__ import annotations

import re


from runtime.firecracker import make_mac_address, make_tap_name


class TestMakeTapName:
    def test_format(self):
        name = make_tap_name("node-abc123", "vm-xyz789")
        assert name == "tap-node-vm-x"

    def test_uses_first_4_chars_of_each(self):
        name = make_tap_name("AABBCC", "DDEE")
        # lowercased first 4 of each
        assert name == "tap-aabb-ddee"

    def test_max_15_chars(self):
        name = make_tap_name("a" * 20, "b" * 20)
        assert len(name) <= 15

    def test_exactly_14_chars_for_4_char_ids(self):
        # "tap-" (4) + "abcd" (4) + "-" (1) + "efgh" (4) = 13?
        # tap- = 4, node[:4] = 4, - = 1, vm[:4] = 4 → 13 chars
        name = make_tap_name("abcdef", "efghij")
        assert len(name) == 13

    def test_short_ids_not_padded(self):
        name = make_tap_name("ab", "cd")
        assert name == "tap-ab-cd"

    def test_lowercased(self):
        name = make_tap_name("NODEID", "VMIDXX")
        assert name == name.lower()

    def test_starts_with_tap(self):
        name = make_tap_name("node1234", "vm123456")
        assert name.startswith("tap-")

    def test_different_node_ids_give_different_names(self):
        # IDs must differ within the first 4 chars
        n1 = make_tap_name("aaaa", "vm00")
        n2 = make_tap_name("bbbb", "vm00")
        assert n1 != n2

    def test_different_vm_ids_give_different_names(self):
        n1 = make_tap_name("node", "vm01")
        n2 = make_tap_name("node", "vm02")
        assert n1 != n2


class TestMakeMacAddress:
    _MAC_RE = re.compile(r"^([0-9A-F]{2}:){5}[0-9A-F]{2}$")

    def test_format_is_colon_separated_hex(self):
        mac = make_mac_address("node-1", "vm-1")
        assert self._MAC_RE.match(mac), f"Invalid MAC: {mac}"

    def test_starts_with_06_00(self):
        mac = make_mac_address("node-1", "vm-1")
        assert mac.startswith("06:00:")

    def test_deterministic_same_inputs(self):
        mac1 = make_mac_address("node-abc", "vm-xyz")
        mac2 = make_mac_address("node-abc", "vm-xyz")
        assert mac1 == mac2

    def test_different_vm_ids_give_different_macs(self):
        mac1 = make_mac_address("node-1", "vm-001")
        mac2 = make_mac_address("node-1", "vm-002")
        assert mac1 != mac2

    def test_different_node_ids_give_different_macs(self):
        mac1 = make_mac_address("node-A", "vm-1")
        mac2 = make_mac_address("node-B", "vm-1")
        assert mac1 != mac2

    def test_six_octets(self):
        mac = make_mac_address("n", "v")
        parts = mac.split(":")
        assert len(parts) == 6

    def test_each_octet_is_two_uppercase_hex_chars(self):
        mac = make_mac_address("hello", "world")
        for octet in mac.split(":"):
            assert len(octet) == 2
            assert all(c in "0123456789ABCDEF" for c in octet)

    def test_known_value_node_and_vm_bytes(self):
        """Verify byte mapping: sha256(node)[0:2] and sha256(vm)[0:2]."""
        import hashlib

        node_id = "n1"
        vm_id = "v1"
        nh = hashlib.sha256(node_id.encode()).digest()
        vh = hashlib.sha256(vm_id.encode()).digest()
        expected = f"06:00:{nh[0]:02X}:{nh[1]:02X}:{vh[0]:02X}:{vh[1]:02X}"
        assert make_mac_address(node_id, vm_id) == expected
