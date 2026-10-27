import unittest
from unittest.mock import patch, Mock
from pathlib import Path
import sensors
import sensors_demo
import admin_core
import admin_demo


class SensorTests(unittest.TestCase):
    def test_cpu_math_excludes_duplicate_guest_fields(self):
        parsed=sensors.cpu_values('cpu 10 2 3 70 5 2 1 7 100 200\ncpu0 3 0 2 10 1 0 0 0\nintr 99')
        self.assertEqual(parsed['cpu'],(100,75))
        self.assertEqual(sensors.cpu_percent((100,75),(200,100)),75)
        self.assertIsNone(sensors.cpu_percent((100,75),(100,75)))

    def test_process_comm_with_parentheses_and_spaces(self):
        fields=['S']+['0']*22
        fields[11]='100';fields[12]='20';fields[19]='12345';fields[21]='10'
        row=sensors.parse_process('42 (name with ) brackets) '+' '.join(fields),42,1000,4096)
        self.assertEqual(row['name'],'name with ) brackets')
        self.assertEqual(row['ticks'],120);self.assertEqual(row['rss'],40960);self.assertEqual(row['start'],12345)

    def test_console_cannot_take_free_commands(self):
        core=Mock()
        for command in ['rm -rf /','sh','uptime;reboot','docker system prune -f','cat /etc/shadow',[],None]:
            with self.assertRaises(ValueError):sensors.read(core,{'view':'sensor_console','command':command})
        core.command.assert_not_called()

    def test_console_uses_literal_argv_and_masks_secrets(self):
        core=Mock();core.command.return_value='token=secret-example\nBearer abcdefg'
        result=sensors.read(core,{'view':'sensor_console','command':'uptime','args':[';reboot']})
        core.command.assert_called_once_with(['uptime'],timeout=20)
        self.assertNotIn('secret-example',result['text']);self.assertNotIn('abcdefg',result['text'])

    def test_unrecognized_log_path_never_opened(self):
        core=Mock()
        with self.assertRaises(ValueError):sensors.log_tail(core,{'log':'/etc/shadow'})
        core.local_path.assert_not_called();core.command.assert_not_called()

    def test_log_filter_is_literal_and_redacted(self):
        core=Mock();core.command.return_value='nginx: token=mysecret\nother: ok\nnginx: error'
        result=sensors.log_tail(core,{'log':'journal','filter':'nginx'})
        self.assertNotIn('mysecret',result['text']);self.assertNotIn('other',result['text']);self.assertIn('error',result['text'])

    def test_fail2ban_rejects_options_and_shell_text(self):
        core=Mock()
        for jail in ['--help','sshd;reboot','../x','a b']:
            with self.assertRaises(ValueError):sensors.fail2ban(core,{'jail':jail})
        core.command.assert_not_called()

    def test_fail2ban_jail_list_and_status(self):
        core=Mock();core.command.return_value='Status\n`- Jail list: sshd, nginx-http-auth'
        self.assertEqual(sensors.fail2ban(core,{})['jails'],['sshd','nginx-http-auth'])
        sensors.fail2ban(core,{'jail':'sshd'})
        self.assertEqual(core.command.call_args.args[0],['fail2ban-client','status','sshd'])

    def test_ssh_reads_effective_values(self):
        core=Mock();core.command.return_value='permitrootlogin prohibit-password\npasswordauthentication no\npubkeyauthentication yes\nport 22\n'
        with patch.object(sensors.shutil,'which',return_value='/usr/sbin/sshd'):
            data=sensors.ssh(core)
        self.assertTrue(data['rows'][0]['attention']);self.assertFalse(data['rows'][1]['attention'])
        core.command.assert_called_once_with(['/usr/sbin/sshd','-T'],timeout=15)

    def test_docker_inventory_is_readonly(self):
        core=Mock();core.command.side_effect=['volume-a\n','sha256:abc\nsha256:abc\n','space']
        result=sensors.unused(core)
        self.assertEqual(result['volumes'],['volume-a']);self.assertEqual(result['images'],['sha256:abc'])
        for call in core.command.call_args_list:
            self.assertNotIn('prune',call.args[0]);self.assertNotIn('rm',call.args[0])

    def test_history_is_bounded_and_preserves_unknowns(self):
        saved=list(sensors.HISTORY)
        try:
            sensors.HISTORY.clear()
            for index in range(1000):sensors.HISTORY.append({'time':index,'cpu':None})
            data=sensors.read(Mock(),{'view':'sensor_live'})
            self.assertEqual(len(data['rows']),720);self.assertIsNone(data['rows'][0]['cpu'])
        finally:sensors.HISTORY.clear();sensors.HISTORY.extend(saved)

    def test_capabilities_and_unknown_view(self):
        with patch.object(sensors.shutil,'which',return_value=None):
            data=sensors.read(Mock(),{'view':'sensor_capabilities'})
            self.assertFalse(any(data['tools'].values()))
        with self.assertRaises(ValueError):sensors.read(Mock(),{'view':'arbitrary'})

    def test_sensor_routes_remain_readonly_with_approved_advanced_operations(self):
        core=Mock()
        for operation in admin_core.ADVANCED_OPS:
            with self.assertRaises(ValueError):sensors.read(core,{'view':operation})
        core.command.assert_not_called()

    def test_services_include_start_times_without_state_changes(self):
        outputs=['demo.service enabled enabled\nother.service disabled enabled\n',
                 'demo.service loaded active running Demo\nother.service loaded inactive dead Other\n',
                 'Id=demo.service\nActiveEnterTimestamp=Sun 2026-10-25 10:00:00 UTC\n\nId=other.service\nActiveEnterTimestamp=\n']
        with patch.object(admin_core,'command',side_effect=outputs) as command:
            data=admin_core.services()
        self.assertEqual(data['rows'][0]['started'],'Sun 2026-10-25 10:00:00 UTC')
        self.assertEqual(data['rows'][1]['started'],'')
        self.assertIn('--',command.call_args.args[0])

    def test_proxy_templates_reject_injection_and_secrets(self):
        for domain,upstream in [('a.com;reboot','http://127.0.0.1:3000'),('example.com','http://a:3000; rm'),('example.com','http://user:secret@host:3000'),('example.com','http://localhost:3000/path'),('example.com','http://localhost:99999')]:
            with self.assertRaises(ValueError):sensors.proxy_template({'domain':domain,'upstream':upstream})
        data=sensors.proxy_template({'domain':'example.com','upstream':'http://127.0.0.1:3000'})
        self.assertIn('reverse_proxy http://127.0.0.1:3000',data['caddy'])
        self.assertIn('https://acme-v02.api.letsencrypt.org/directory',data['caddy'])
        self.assertIn('proxy_pass http://127.0.0.1:3000',data['nginx'])

    def test_all_demo_views_are_fixtures(self):
        for view in sensors.VIEWS:
            data=admin_demo.read({'view':view,'command':'uptime'})
            self.assertIsInstance(data,dict)
        self.assertTrue(admin_demo.read({'view':'sensor_live'})['rows'])


if __name__=='__main__':unittest.main()
