from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from ssh_mcp.db import Store, ValidationError


class StoreTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmpdir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.tmpdir.name) / "test.sqlite3"
        self.store = Store(self.db_path)
        self.store.create_device(
            {
                "name": "lab-router",
                "hostname": "lab-router",
                "vendor": "MikroTik",
                "model": "CCR",
            }
        )

    def tearDown(self) -> None:
        self.tmpdir.cleanup()

    def test_resolve_template(self) -> None:
        self.store.add_approved_command(
            {
                "vendor": "MikroTik",
                "intent": "iface",
                "command_template": "/interface print detail where name={interface}",
            }
        )
        result = self.store.resolve_command_template("lab-router", "iface", {"interface": "ether1"})
        self.assertEqual(result["rendered_command"], "/interface print detail where name=ether1")

    def test_proposal_lifecycle(self) -> None:
        proposal = self.store.create_proposal(
            proposal_type="show_command",
            device_name="lab-router",
            session_id=None,
            intent="test",
            mode="read",
            risk="low",
            reason="unit test",
            rendered_commands=["/system resource print"],
        )
        approved = self.store.approve_proposal(proposal["id"], approved_by="tester")
        self.assertEqual(approved["status"], "approved")
        executed = self.store.mark_proposal_executed(proposal["id"], exit_code=0, summary="ok")
        self.assertEqual(executed["status"], "executed")

    def test_missing_template_param(self) -> None:
        with self.assertRaises(ValidationError):
            self.store.resolve_command_template("lab-router", "missing", {})

    def test_seed_defaults_include_mikrotik_triage_commands(self) -> None:
        seeded = self.store.seed_defaults()
        self.assertGreaterEqual(seeded["approved_commands"], 1)

        commands = self.store.list_approved_commands(vendor="MikroTik")
        intents = {item["intent"] for item in commands}
        self.assertIn("identity_read", intents)
        self.assertIn("neighbors_read", intents)
        self.assertIn("bridge_hosts_read", intents)
        self.assertIn("mac_scan_short", intents)

    def test_seed_defaults_include_mikrotik_playbooks(self) -> None:
        self.store.seed_defaults()
        playbooks = self.store.list_playbooks(vendor="MikroTik")
        names = {item["name"] for item in playbooks}
        self.assertIn("mikrotik-topology-baseline", names)
        self.assertIn("mikrotik-customer-port-trace", names)
        self.assertIn("mikrotik-pppoe-discovery-triage", names)

    def test_diagnostics_reflect_pending_proposal(self) -> None:
        proposal = self.store.create_proposal(
            proposal_type="show_command",
            device_name="lab-router",
            session_id=None,
            intent="identity_read",
            mode="read",
            risk="low",
            reason="diag test",
            rendered_commands=["/system identity print"],
        )
        diagnostics = self.store.diagnostics()
        self.assertEqual(diagnostics["proposal_count"], 1)
        self.assertEqual(diagnostics["last_proposal_id"], proposal["id"])
        self.assertEqual(len(diagnostics["pending_proposals"]), 1)
        self.assertEqual(diagnostics["pending_proposals"][0]["id"], proposal["id"])
        fetched = self.store.get_proposal(proposal["id"])
        self.assertEqual(fetched["id"], proposal["id"])
        self.assertEqual(fetched["intent"], "identity_read")


if __name__ == "__main__":
    unittest.main()
