import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import time
import unittest


PLUGIN = Path(__file__).resolve().parents[1]


class AutoFullTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="autofull test's ")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.bin = self.root / "bin"
        self.bin.mkdir()
        self.script = self.bin / "omarchy-autofull-workspace"
        shutil.copy2(PLUGIN / "bin" / self.script.name, self.script)
        self.env = dict(
            os.environ,
            XDG_CONFIG_HOME=str(self.root / "config"),
            XDG_STATE_HOME=str(self.root / "state"),
            PATH=str(self.bin) + os.pathsep + os.environ["PATH"],
            AUTOFULL_TEST_ROOT=str(self.root),
        )
        self.rule = self.root / "state/omarchy/toggles/hypr/autofull-workspace.lua"
        self.conf = self.root / "config/omarchy/autofull-workspace.conf"
        self.log = self.root / "calls.jsonl"
        mock = self.bin / "hyprctl"
        mock.write_text(f"#!{sys.executable}\n" + '''import json, os, pathlib, sys, time
root = pathlib.Path(os.environ["AUTOFULL_TEST_ROOT"])
with (root / "calls.jsonl").open("a") as log:
    log.write(json.dumps(sys.argv[1:]) + "\\n")
delay = root / "delay"
if delay.exists(): time.sleep(float(delay.read_text()))
failure = root / ("fail-" + sys.argv[1])
if failure.exists():
    failure.unlink()
    print("injected " + sys.argv[1] + " failure", file=sys.stderr)
    sys.exit(7)
print("ok")
''')
        mock.chmod(0o755)
        notification = self.bin / "omarchy-notification-send"
        notification.write_text('#!/bin/bash\nprintf "%s\\n" "$*" >> "$AUTOFULL_TEST_ROOT/notifications"\n')
        notification.chmod(0o755)

    def run_cli(self, *args, success=True):
        result = subprocess.run([str(self.script), *args], env=self.env,
                                text=True, capture_output=True, timeout=10)
        if success:
            self.assertEqual(result.returncode, 0, result.stderr)
        else:
            self.assertNotEqual(result.returncode, 0)
        return result

    def calls(self):
        return [json.loads(line) for line in self.log.read_text().splitlines()] if self.log.exists() else []

    def fail_next(self, command):
        (self.root / ("fail-" + command)).touch()

    def test_toggle_modes_and_custom_xdg_paths(self):
        self.assertEqual(self.run_cli("bar").stdout.strip(), "off:maximized")
        self.run_cli("on")
        self.assertIn("maximize = true", self.rule.read_text())
        self.run_cli("mode", "fullscreen")
        self.assertEqual(self.conf.read_text(), "mode=fullscreen\n")
        self.assertIn("fullscreen = true", self.rule.read_text())
        self.assertEqual(self.run_cli("bar").stdout.strip(), "on:fullscreen")
        self.run_cli("cycle")
        self.assertEqual(self.run_cli("mode").stdout.strip(), "maximized")
        self.run_cli("toggle")
        self.assertFalse(self.rule.exists())
        self.assertEqual(self.run_cli("status").stdout.strip(), "off")
        self.run_cli("mode", "invalid", success=False)

    def test_failed_enable_restores_off(self):
        self.fail_next("reload")
        result = self.run_cli("on", success=False)
        self.assertIn("injected reload failure", result.stderr)
        self.assertFalse(self.rule.exists())
        self.assertEqual(self.run_cli("bar").stdout.strip(), "off:maximized")
        self.assertEqual([call[0] for call in self.calls()], ["reload", "reload"])
        self.assertNotIn("AutoFull : On", (self.root / "notifications").read_text())

    def test_failed_disable_restores_enabled_rule(self):
        self.run_cli("on")
        original = self.rule.read_bytes()
        self.fail_next("reload")
        self.run_cli("off", success=False)
        self.assertEqual(self.rule.read_bytes(), original)
        self.assertEqual(self.run_cli("bar").stdout.strip(), "on:maximized")

    def test_failed_mode_restores_both_files(self):
        self.run_cli("mode", "maximized")
        self.run_cli("on")
        original = self.rule.read_bytes(), self.conf.read_bytes()
        self.fail_next("reload")
        self.run_cli("mode", "fullscreen", success=False)
        self.assertEqual((self.rule.read_bytes(), self.conf.read_bytes()), original)

    def test_failed_mode_restores_absent_config(self):
        self.run_cli("on")
        self.fail_next("reload")
        self.run_cli("mode", "fullscreen", success=False)
        self.assertFalse(self.conf.exists())
        self.assertEqual(self.run_cli("bar").stdout.strip(), "on:maximized")

    def test_manual_edit_and_noop_sync(self):
        self.run_cli("on")
        self.conf.write_text("mode=fullscreen\n")
        # Pending edits must not be misreported as an applied mode.
        self.assertEqual(self.run_cli("bar").stdout.strip(), "on:maximized")
        self.run_cli("sync")
        self.assertIn("fullscreen = true", self.rule.read_text())
        self.assertEqual(self.run_cli("bar").stdout.strip(), "on:fullscreen")
        count = len(self.calls())
        self.run_cli("sync")
        self.assertEqual(len(self.calls()), count, "No-op sync must preserve manual window overrides")

    def test_failed_sync_keeps_user_edit_and_reports_applied_mode(self):
        self.run_cli("on")
        self.conf.write_text("mode=fullscreen\n")
        self.fail_next("reload")
        self.run_cli("sync", success=False)
        self.assertEqual(self.conf.read_text(), "mode=fullscreen\n")
        self.assertEqual(self.run_cli("bar").stdout.strip(), "on:maximized")
        self.run_cli("sync")
        self.assertEqual(self.run_cli("bar").stdout.strip(), "on:fullscreen")

    def test_off_sync_does_not_activate_or_reload(self):
        self.run_cli("mode", "fullscreen")
        self.run_cli("sync")
        self.assertEqual(self.run_cli("bar").stdout.strip(), "off:fullscreen")
        self.assertEqual(self.calls(), [])

    def test_off_restore_is_noop(self):
        self.run_cli("restore")
        self.assertEqual(self.calls(), [])
        self.assertFalse(self.rule.exists())
        self.assertFalse(self.conf.exists())

    def test_restore_uses_installed_mode_without_writes_or_reload(self):
        for mode, pending in (("maximized", "fullscreen"), ("fullscreen", "maximized")):
            with self.subTest(mode=mode):
                self.run_cli("mode", mode)
                self.run_cli("on")
                self.conf.write_text("mode=" + pending + "\n")
                original = [(p.read_bytes(), p.stat().st_mtime_ns) for p in (self.rule, self.conf)]
                count = len(self.calls())
                self.run_cli("restore")
                self.assertEqual(len(self.calls()), count + 1)
                self.assertEqual(self.calls()[-1][0], "eval")
                self.assertIn("local m='" + mode + "'", self.calls()[-1][1])
                self.assertEqual([(p.read_bytes(), p.stat().st_mtime_ns) for p in (self.rule, self.conf)], original)

    def test_failed_restore_can_retry(self):
        self.run_cli("on")
        original = self.rule.read_bytes()
        self.fail_next("eval")
        self.run_cli("restore", success=False)
        self.run_cli("restore")
        self.assertEqual(self.rule.read_bytes(), original)
        self.assertEqual([call[0] for call in self.calls()], ["reload", "eval", "eval", "eval"])

    def test_dispatch_failure_does_not_claim_success(self):
        self.fail_next("eval")
        result = self.run_cli("on", success=False)
        self.assertIn("adjusting existing windows failed", result.stderr)
        self.assertIn("maximize = true", self.rule.read_text())
        self.assertNotIn("AutoFull : On", (self.root / "notifications").read_text())

    def test_concurrent_toggles_are_serialized(self):
        (self.root / "delay").write_text("0.1")
        processes = [subprocess.Popen([str(self.script), "toggle"], env=self.env,
                                      stdout=subprocess.PIPE, stderr=subprocess.PIPE)
                     for _ in range(2)]
        for process in processes:
            _, error = process.communicate(timeout=10)
            self.assertEqual(process.returncode, 0, error)
        self.assertEqual(self.run_cli("bar").stdout.strip(), "off:maximized")

    def test_probe_waits_for_failed_transaction(self):
        (self.root / "delay").write_text("0.2")
        self.fail_next("reload")
        process = subprocess.Popen([str(self.script), "on"], env=self.env,
                                   stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        try:
            self.wait_until(lambda: bool(self.calls()))
            self.assertEqual(self.run_cli("bar").stdout.strip(), "off:maximized")
        finally:
            process.communicate(timeout=10)
        self.assertNotEqual(process.returncode, 0)

    def wait_until(self, predicate, timeout=5):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if predicate(): return
            time.sleep(0.03)
        self.fail("Timed out waiting for test state")

    @unittest.skipUnless(os.environ.get("AUTOFULL_QML_TESTS") == "1", "Set AUTOFULL_QML_TESTS=1 for headless Quickshell integration")
    def test_widget_syncs_fresh_install_external_edits_and_rapid_edits(self):
        ui = self.root / "Ui"
        ui.mkdir()
        (ui / "BarWidget.qml").write_text('import QtQuick\nItem { property string moduleName; property var bar: null }\n')
        (ui / "WidgetButton.qml").write_text('import QtQuick\nItem { property var bar; property string text; property bool active; property bool dimmed; property string tooltipText; signal pressed(int button) }\n')
        (self.root / "AutoFull.qml").write_text((PLUGIN / "AutoFull.qml").read_text().replace('import qs.Ui', 'import "Ui"'))
        (self.root / "shell.qml").write_text('''import QtQuick
import Quickshell
ShellRoot {
 AutoFull { id: widget }
 Timer { interval: 50; running: true; repeat: true; onTriggered: console.log("AUDIT_STATE", widget.isOn, widget.mode) }
 Timer { interval: 30000; running: true; onTriggered: Qt.quit() }
}
''')
        qml_log = self.root / "qml.log"
        with qml_log.open("w") as output:
            process = subprocess.Popen(["quickshell", "-p", str(self.root / "shell.qml"), "--no-color"],
                                       env=dict(self.env, QT_QPA_PLATFORM="offscreen"), stdout=output, stderr=subprocess.STDOUT)
            try:
                def latest_state():
                    lines = [line for line in qml_log.read_text().splitlines() if "AUDIT_STATE" in line]
                    return lines[-1].split("AUDIT_STATE ")[-1] if lines else ""

                self.wait_until(lambda: latest_state() == "false maximized")
                self.run_cli("on")
                self.wait_until(lambda: latest_state() == "true maximized")
                self.conf.write_text("mode=fullscreen\n")
                self.wait_until(lambda: latest_state() == "true fullscreen")
                self.assertIn("fullscreen = true", self.rule.read_text())

                # A second edit arrives while the first sync is in flight.
                (self.root / "delay").write_text("0.2")
                self.conf.write_text("mode=maximized\n")
                count = len(self.calls())
                self.wait_until(lambda: len(self.calls()) > count)
                self.conf.write_text("mode=fullscreen\n")
                self.wait_until(lambda: len(self.calls()) >= count + 4)
                self.wait_until(lambda: latest_state() == "true fullscreen")
                self.assertIn("fullscreen = true", self.rule.read_text())
                (self.root / "delay").unlink()

                def recovery_event():
                    result = subprocess.run(
                        ["quickshell", "ipc", "-p", str(self.root / "shell.qml"), "call", "autofull", "restore"],
                        env=dict(self.env, QT_QPA_PLATFORM="offscreen"),
                        text=True, capture_output=True, timeout=5)
                    self.assertEqual(result.returncode, 0, result.stderr)
                    self.assertNotIn("not found", result.stdout.lower())

                count = len(self.calls())
                self.fail_next("eval")
                recovery_event()
                recovery_event()
                self.wait_until(lambda: len(self.calls()) == count + 2)
                time.sleep(1.2)
                self.assertEqual(len(self.calls()), count + 2)
                self.assertEqual([call[0] for call in self.calls()[count:]], ["eval", "eval"])

                count = len(self.calls())
                (self.root / "delay").write_text("1.2")
                recovery_event()
                self.wait_until(lambda: len(self.calls()) == count + 1)
                recovery_event()
                self.wait_until(lambda: len(self.calls()) == count + 2)
                time.sleep(1.4)
                (self.root / "delay").unlink()
                self.assertEqual(len(self.calls()), count + 2)

                self.run_cli("off")
                self.wait_until(lambda: latest_state() == "false fullscreen")
                count = len(self.calls())
                recovery_event()
                time.sleep(1.3)
                self.assertEqual(len(self.calls()), count)
                self.conf.write_text("mode=maximized\n")
                self.wait_until(lambda: latest_state() == "false maximized")
                self.assertFalse(self.rule.exists())
            finally:
                process.terminate()
                process.wait(timeout=5)
                self.assertNotIn("ERROR", qml_log.read_text(), qml_log.read_text())


if __name__ == "__main__":
    unittest.main()
