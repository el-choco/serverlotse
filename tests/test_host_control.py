import unittest
from unittest.mock import patch
import host_control


class HostControlTests(unittest.TestCase):
    def setUp(self):
        host_control.PENDING.clear()
        self.enabled=patch.object(host_control,"ENABLED",True);self.enabled.start()

    def tearDown(self):
        self.enabled.stop()

    def test_disabled_and_invalid_actions_never_call_bus(self):
        with patch.object(host_control,"dbus") as bus:
            with self.assertRaises(ValueError):host_control.prepare("shell")
            with patch.object(host_control,"ENABLED",False):
                with self.assertRaises(ValueError):host_control.prepare("reboot")
            bus.assert_not_called()

    def test_prepare_only_checks_capabilities(self):
        with patch.object(host_control,"dbus",return_value='string "yes"') as bus:
            challenge=host_control.prepare("reboot")
            self.assertEqual(challenge["confirmation"],"REBOOT")
            self.assertEqual([call.args[0] for call in bus.call_args_list],["CanReboot","CanPowerOff"])

    def test_wrong_confirmation_and_replay_blocked(self):
        with patch.object(host_control,"dbus",return_value='string "yes"') as bus:
            challenge=host_control.prepare("reboot")
            with self.assertRaises(ValueError):host_control.execute({"action":"reboot","nonce":challenge["nonce"],"confirmation":"yes"})
            result=host_control.execute({"action":"reboot","nonce":challenge["nonce"],"confirmation":"REBOOT"})
            self.assertTrue(result["accepted"])
            self.assertEqual(bus.call_args.args[0],"ScheduleShutdown")
            self.assertEqual(bus.call_args.args[1],"string:reboot")
            with self.assertRaises(ValueError):host_control.execute({"action":"reboot","nonce":challenge["nonce"],"confirmation":"REBOOT"})

    def test_shutdown_expired_or_wrong_action(self):
        with patch.object(host_control,"dbus",return_value='string "yes"') as bus:
            challenge=host_control.prepare("shutdown")
            with self.assertRaises(ValueError):host_control.execute({"action":"reboot","nonce":challenge["nonce"],"confirmation":"REBOOT"})
            challenge=host_control.prepare("shutdown")
            host_control.PENDING[challenge["nonce"]]["expires"]=0
            with self.assertRaises(ValueError):host_control.execute({"action":"shutdown","nonce":challenge["nonce"],"confirmation":"SHUTDOWN"})
            self.assertFalse(any(call.args[0]=="ScheduleShutdown" for call in bus.call_args_list))

    def test_bus_uses_fixed_arguments_without_shell(self):
        with patch.object(host_control.subprocess,"run") as run:
            run.return_value.returncode=0;run.return_value.stdout='string "yes"'
            host_control.dbus("CanReboot")
            command=run.call_args.args[0]
            self.assertEqual(command[-1],"org.freedesktop.login1.Manager.CanReboot")
            self.assertNotIn("shell",run.call_args.kwargs)

    def test_relay_requires_exact_shared_key(self):
        handler=object.__new__(host_control.Control)
        with patch.object(host_control,"KEY","test-shared-relay-key"):
            handler.headers={};self.assertFalse(handler.allowed())
            handler.headers={"Authorization":"Bearer wrong"};self.assertFalse(handler.allowed())
            handler.headers={"Authorization":"Bearer test-shared-relay-key"};self.assertTrue(handler.allowed())
