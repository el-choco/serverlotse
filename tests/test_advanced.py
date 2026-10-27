import copy
import hashlib
import io
import json
import os
from pathlib import Path
import tempfile
import time
import unittest
from unittest.mock import Mock,patch
import admin_core as core
import advanced
import automation
import bundle_backup
import proxy_control
import sensors


class AdvancedTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.state=patch.object(core,'STATE',Path(self.tmp.name)/'state');self.state.start();core.initialize()
        core.PREVIEWS.clear();automation.HIGH_SINCE.clear();automation.LAST_CHECK.clear();automation.FAILURES.clear()

    def tearDown(self):self.state.stop();self.tmp.cleanup()

    def test_operation_registry_matches_approved_handlers(self):
        self.assertEqual(core.ADVANCED_OPS,advanced.OPS)

    def test_process_actions_protect_root_and_bind_pid_identity(self):
        pid=os.getpid()+100000;row={'pid':pid,'uid':1000,'name':'example-app','start':456}
        with patch.object(advanced.os,'pidfd_open',create=True),patch.object(advanced.signal,'pidfd_send_signal',create=True),patch.object(sensors,'processes',return_value={'rows':[row]}):
            plan=advanced.validate({'operation':'process_signal','pid':pid,'verb':'term'})
            self.assertEqual(plan['start'],456)
            row['uid']=0
            with self.assertRaises(ValueError):advanced.validate({'operation':'process_signal','pid':pid,'verb':'term'})

    def test_reused_process_is_never_signalled(self):
        plan={'operation':'process_signal','pid':12345,'uid':1000,'start':100,'verb':'term'}
        with patch.object(advanced.os,'pidfd_open',return_value=999,create=True),patch.object(advanced.os,'close') as close,patch.object(advanced.signal,'pidfd_send_signal',create=True) as send,patch.object(sensors,'processes',return_value={'rows':[{'pid':12345,'uid':1000,'start':101}]}):
            with self.assertRaises(ValueError):advanced.apply(plan)
            send.assert_not_called();close.assert_called_once_with(999)

    def test_shell_preview_never_executes_and_audit_hides_command(self):
        with patch.object(core,'command') as command:
            result=core.prepare({'operation':'shell_run','command':'printf hello | head -c 5'})
            command.assert_not_called()
        self.assertEqual(result['preview']['command'],'printf hello | head -c 5')
        self.assertNotIn('printf hello',json.dumps(core.clean({'operation':'shell_run','command':'printf hello'},audit=True)))
        with patch.object(core,'enqueue',return_value={'id':'test'}) as queue:
            with self.assertRaises(ValueError):core.execute({'nonce':result['nonce'],'confirmation':'yes'})
            queue.assert_not_called()
            core.execute({'nonce':result['nonce'],'confirmation':'AUSFUEHREN'});self.assertEqual(queue.call_count,1)

    def test_shell_apply_is_fixed_shell_with_timeout_and_masking(self):
        with patch.object(core,'command',return_value='token=my-secret-value') as command:
            result=advanced.apply({'operation':'shell_run','command':'echo example'})
        command.assert_called_once_with(['/bin/sh','-lc','echo example'],timeout=120)
        self.assertNotIn('my-secret-value',result['text'])

    def test_volume_requires_delete_keyword_and_single_use(self):
        with patch.object(sensors,'unused',return_value={'volumes':['old-data']}):
            plan=core.prepare({'operation':'volume_delete','name':'old-data'})
        self.assertEqual(plan['confirmation'],'LOESCHEN')
        with patch.object(core,'enqueue',return_value={'id':'test'}) as queue:
            with self.assertRaises(ValueError):core.execute({'nonce':plan['nonce'],'confirmation':'AUSFUEHREN'})
            queue.assert_not_called();core.execute({'nonce':plan['nonce'],'confirmation':'LOESCHEN'})
            with self.assertRaises(ValueError):core.execute({'nonce':plan['nonce'],'confirmation':'LOESCHEN'})
            self.assertEqual(queue.call_count,1)

    def test_used_volume_is_not_deletable(self):
        with patch.object(sensors,'unused',return_value={'volumes':[]}):
            with self.assertRaises(ValueError):advanced.validate({'operation':'volume_delete','name':'used-data'})
        with patch.object(core,'command',return_value='removed') as command:
            advanced.apply({'operation':'volume_delete','name':'old-data'})
        command.assert_called_once_with(['docker','volume','rm','old-data'],timeout=120)

    def test_cleanup_never_prunes_volumes_or_containers(self):
        with patch.object(core,'command',return_value='ok') as command:
            advanced.apply({'operation':'docker_clean','minimum_age_hours':168})
        self.assertEqual(len(command.call_args_list),2)
        for call in command.call_args_list:
            self.assertIn(call.args[0][1],['image','builder']);self.assertIn('until=168h',call.args[0])
            self.assertNotIn('--volumes',call.args[0]);self.assertNotIn('system',call.args[0])

    def test_firewall_preserves_ssh_and_management(self):
        with patch.object(sensors,'firewall',return_value={'backend':'ufw','text':'Status: active'}),patch.object(core,'command',return_value='port 4222\n'):
            for port in [22,23,443,18099,4222]:
                with self.assertRaises(ValueError):advanced.validate({'operation':'firewall_rule','port':port,'protocol':'tcp','verb':'close'})
        with patch.object(sensors,'firewall',return_value={'backend':'ufw','text':'Status: inactive'}):
            with self.assertRaises(ValueError):advanced.validate({'operation':'firewall_rule','port':8080,'protocol':'tcp','verb':'allow'})

    def test_firewall_prepare_only_dry_run_then_fixed_apply(self):
        def command(args,**kwargs):return 'port 22\n' if args[-1]=='-T' else 'simulated rule'
        with patch.object(sensors,'firewall',return_value={'backend':'ufw','text':'Status: active'}),patch.object(core,'command',side_effect=command) as calls:
            plan=advanced.validate({'operation':'firewall_rule','port':'8080','protocol':'tcp','verb':'allow'})
        self.assertEqual(plan['port'],8080)
        self.assertIn('--dry-run',calls.call_args.args[0])
        with patch.object(core,'command',return_value='ok') as command:
            advanced.apply(plan)
        command.assert_called_once_with(['ufw','--force','allow','8080/tcp'])

    def test_defaults_disabled_and_secret_flags_only(self):
        self.assertFalse(advanced.config()['enabled'])
        self.assertFalse(advanced.config()['janitor'])
        cfg=advanced.config(True);cfg.update(webhook_url='https://discord.com/api/webhooks/123456/secret-url',telegram_token='123456:bot-secret',telegram_chat='12345678')
        advanced.save_config(cfg);public=advanced.config();text=json.dumps(public)
        self.assertNotIn('secret-url',text);self.assertNotIn('bot-secret',text);self.assertNotIn('12345678',text)
        self.assertTrue(public['webhook_url_configured']);self.assertEqual(public['webhook_host'],'discord.com')

    def test_settings_plan_stable_including_clear_credentials(self):
        cfg=advanced.config(True);cfg['webhook_url']='https://discord.com/api/webhooks/123456/secret-url';advanced.save_config(cfg)
        plan=advanced.validate({'operation':'settings_save','settings':{'cpu':'95','clear_webhook':True}})
        self.assertEqual(advanced.validate(plan),plan)
        self.assertNotIn('secret-url',json.dumps(core.clean(plan)))
        advanced.apply(plan)
        self.assertNotIn('webhook_url',advanced.config(True));self.assertEqual(advanced.config()['cpu'],95)

    def test_changed_settings_or_notification_target_invalidates_preview(self):
        cfg=advanced.config(True);cfg['webhook_url']='https://discord.com/api/webhooks/123456/old-secret';advanced.save_config(cfg)
        settings=advanced.validate({'operation':'settings_save','settings':{'cpu':95}})
        notification=advanced.validate({'operation':'webhook_test'})
        cfg['webhook_url']='https://discord.com/api/webhooks/123456/new-secret';advanced.save_config(cfg)
        self.assertNotEqual(advanced.validate(settings),settings)
        self.assertNotEqual(advanced.validate(notification),notification)
        self.assertNotIn('old-secret',json.dumps(core.clean(notification)))

    def test_unsafe_webhook_urls_rejected(self):
        for value in ['http://discord.com/api/webhooks/a/b','file:///etc/shadow','https://u:p@discord.com/api/webhooks/a/b','https://foreign.invalid/api/webhooks/a/b']:
            with self.assertRaises(ValueError):advanced.normalize_config({'webhook_url':value,'webhook_kind':'discord'})

    def test_webhook_errors_do_not_disclose_secret_url(self):
        opener=Mock();opener.open.side_effect=ValueError('https://secret-url-example.invalid/private-token')
        cfg={**advanced.DEFAULTS,'webhook_kind':'generic','webhook_url':'https://secret-url-example.invalid/private-token'}
        with patch.object(advanced,'build_opener',return_value=opener):
            with self.assertRaises(ValueError) as result:advanced.notify('test',cfg)
        self.assertNotIn('private-token',str(result.exception));self.assertNotIn('secret-url-example',str(result.exception))

    def test_discord_disables_mentions_and_uses_bounded_request(self):
        response=Mock();response.__enter__=Mock(return_value=response);response.__exit__=Mock(return_value=False)
        opener=Mock();opener.open.return_value=response
        cfg={**advanced.DEFAULTS,'webhook_url':'https://discord.com/api/webhooks/123456/test-not-a-real-key'}
        with patch.object(advanced,'build_opener',return_value=opener):advanced.notify('test @everyone',cfg)
        request=opener.open.call_args.args[0];payload=json.loads(request.data)
        self.assertEqual(payload['allowed_mentions']['parse'],[]);self.assertEqual(opener.open.call_args.kwargs['timeout'],8)

    def test_disabled_automation_never_inspects_or_sends(self):
        with patch.object(advanced,'config',return_value=copy.deepcopy(advanced.DEFAULTS)),patch.object(core,'command') as command,patch.object(advanced,'notify') as notify:
            automation.tick(1000);command.assert_not_called();notify.assert_not_called()

    def test_main_switch_can_be_disabled_when_dependencies_are_broken(self):
        cfg=advanced.config(True);cfg.update(enabled=True,heal_containers=['a'*64],rclone_config='/missing/old.conf');advanced.save_config(cfg)
        with patch.object(core,'validate',side_effect=ValueError('docker unavailable')) as validate,patch.object(advanced,'check_rclone_config',side_effect=ValueError('missing')) as check:
            plan=advanced.validate({'operation':'settings_save','settings':{'enabled':False}})
            self.assertFalse(plan['settings']['enabled']);validate.assert_not_called();check.assert_not_called()

    def test_cpu_alert_requires_hold_and_honors_cooldown(self):
        cfg={**copy.deepcopy(advanced.DEFAULTS),'enabled':True,'notify_ram':False,'hold_seconds':60}
        latest={'time':1000,'cpu':95,'ram_percent':30}
        with patch.object(advanced,'config',return_value=cfg),patch.dict(sensors.PREVIOUS,{'latest':latest}),patch.object(advanced,'notify') as notify:
            automation.tick(1000);latest['time']=1059;automation.tick(1059);notify.assert_not_called()
            latest['time']=1060;automation.tick(1060);self.assertEqual(notify.call_count,1)
            latest['time']=1065;automation.tick(1065);self.assertEqual(notify.call_count,1)

    def test_intentional_exit_and_three_attempt_limit_skip_restart(self):
        self.assertTrue(automation.intentional_stop('a'*64,{'ExitCode':0},1000))
        cfg={**copy.deepcopy(advanced.DEFAULTS),'heal_services':['example.service']}
        advanced.state('attempts:example.service',[900,901,902])
        with patch.object(core,'command') as command,patch.object(core,'enqueue') as enqueue:
            automation.heal(cfg,1000);command.assert_not_called();enqueue.assert_not_called()

    def test_failed_service_needs_two_checks_and_is_audited(self):
        cfg={**copy.deepcopy(advanced.DEFAULTS),'heal_services':['example.service']}
        plan={'operation':'service','name':'example.service','verb':'restart'}
        with patch.object(core,'command',return_value='failed'),patch.object(core,'validate',return_value=plan),patch.object(core,'enqueue',return_value={'id':'test'}) as enqueue:
            automation.heal(cfg,1000);enqueue.assert_not_called()
            automation.heal(cfg,1060);enqueue.assert_called_once_with(plan)
        self.assertEqual(advanced.state('attempts:example.service'),[1060])
        self.assertEqual(core.audit_rows()['rows'][0]['operation'],'auto_heal')

    def test_manual_stop_suppression_blocks_all_healing(self):
        target='a'*64;advanced.state('suppressed:'+target,True)
        cfg={**copy.deepcopy(advanced.DEFAULTS),'heal_containers':[target]}
        with patch.object(core,'command') as command:automation.heal(cfg,1000);command.assert_not_called()

    def test_security_policy_is_security_only_and_no_reboot(self):
        text=advanced.update_policy_text({'enabled':True})
        self.assertIn('Automatic-Reboot "false"',text);self.assertIn('Debian-Security',text)
        self.assertIn('archive=${distro_codename}-security',text);self.assertNotIn('-updates',text)
        self.assertIn('Unattended-Upgrade "0"',advanced.update_policy_text({'enabled':False}))

    def test_backup_volume_matches_uuid_after_device_renumbering(self):
        expected={'uuid':'same-uuid','source':'/dev/sdb1','target':'/mnt/data','fstype':'ext4'}
        self.assertTrue(core.same_volume(expected,{**expected,'source':'/dev/sdc1'}))
        self.assertFalse(core.same_volume(expected,{**expected,'uuid':'system-ssd'}))
        self.assertFalse(core.same_volume(expected,{**expected,'target':'/'}))

    def test_s3_credentials_are_validated_but_not_disclosed(self):
        data={'operation':'remote_save','name':'serverlotse_test','provider':'s3','endpoint':'https://storage.googleapis.com','region':'us-east-1','access_key':'test-access-key','secret_key':'test-secret-key'}
        with patch.object(core,'local_path',return_value=Path(self.tmp.name)/'missing'),patch.object(advanced,'file_hash',return_value=None):
            plan=advanced.validate(data)
        text=json.dumps(core.clean(plan));self.assertNotIn('test-access-key',text);self.assertNotIn('test-secret-key',text)
        self.assertTrue(core.clean(plan)['secret_key_configured'])

    def test_nginx_template_has_acme_and_verified_tls_paths(self):
        plan={'domain':'example.com','upstream':'http://127.0.0.1:3000'}
        self.assertIn('location /.well-known/acme-challenge/',proxy_control.nginx_text(plan))
        tls=proxy_control.nginx_text(plan,True)
        self.assertIn('/etc/letsencrypt/live/example.com/fullchain.pem',tls)
        self.assertIn('TLSv1.2 TLSv1.3',tls);self.assertIn('return 301 https://$host$request_uri',tls)

    def test_proxy_requires_explicit_acme_consent_before_host_commands(self):
        with patch.object(core,'command') as command:
            with self.assertRaises(ValueError):advanced.validate({'operation':'proxy_apply','engine':'caddy','domain':'example.com','upstream':'http://127.0.0.1:3000','acme_consent':False})
            command.assert_not_called()

    def test_caddy_reload_failure_restores_file_and_retains_backup(self):
        root=Path(self.tmp.name);path=root/'Caddyfile';original=b'old.example { respond "old" }\n';path.write_bytes(original)
        plan={'engine':'caddy','domain':'new.example.com','upstream':'http://127.0.0.1:3000','existing_hash':advanced.file_hash(path)}
        def write(target,payload,mode=None):target.write_bytes(payload)
        def command(args,**kwargs):
            if args[:2]==['systemctl','reload']:raise ValueError('reload failed')
            return 'valid'
        with patch.object(proxy_control,'Path',side_effect=lambda value:path if value=='/etc/caddy/Caddyfile' else Path(value)),patch.object(advanced,'atomic_write',side_effect=write),patch.object(core,'command',side_effect=command):
            with self.assertRaises(ValueError):proxy_control.caddy(plan)
        self.assertEqual(path.read_bytes(),original)
        backups=list(core.STATE.glob('Caddyfile-*.bak'));self.assertEqual(len(backups),1);self.assertEqual(backups[0].read_bytes(),original)
        self.assertFalse(list(root.glob('Caddyfile.serverlotse-*')))

    def test_tool_installer_is_allowlisted_and_simulates_first(self):
        with patch.object(core,'command',return_value='package simulation') as command:
            plan=advanced.validate({'operation':'tool_install','package':'rclone'})
        command.assert_called_once_with(['apt-get','-s','install','rclone'],timeout=90)
        self.assertEqual(plan['simulation'],'package simulation')
        with patch.object(core,'command') as command:
            with self.assertRaises(ValueError):advanced.validate({'operation':'tool_install','package':'rclone;reboot'})
            command.assert_not_called()

    def test_atomic_write_preserves_existing_permissions(self):
        path=Path(self.tmp.name)/'config';path.write_bytes(b'old')
        before=path.stat().st_mode
        with patch.object(core,'local_path',return_value=path),patch.object(core,'private_destination'):
            advanced.atomic_write(path,b'new')
        self.assertEqual(path.read_bytes(),b'new');self.assertEqual(path.stat().st_mode,before)

    def test_remote_upload_failure_keeps_verified_local_gzip(self):
        import tarfile
        root=Path(self.tmp.name);name='serverlotse-'+'d'*24+'-20261025-120000-abcdef.tar';source=root/name;destination=source.with_suffix('.tar.gz');payload=b'data'
        manifest={'version':1,'files':{'data.txt':{'size':len(payload),'sha256':hashlib.sha256(payload).hexdigest()}},'skipped':0}
        with tarfile.open(source,'w') as archive:
            member=tarfile.TarInfo('files/data.txt');member.size=len(payload);archive.addfile(member,io.BytesIO(payload))
            content=json.dumps(manifest).encode();member=tarfile.TarInfo('manifest.json');member.size=len(content);archive.addfile(member,io.BytesIO(content))
        plan={'id':'d'*24,'source':str(root/'source'),'destination':str(root),'remote':'test:backups','container':'','rclone_config':''}
        with patch.object(core,'backup_paths',return_value=(root/'source',root)),patch.object(core,'backup_run',return_value={'archive':name,'skipped':0}),patch.object(core,'archive_file',return_value=destination),patch.object(core,'command',side_effect=ValueError('private remote error')):
            with self.assertRaises(ValueError) as error:bundle_backup.run(plan)
        self.assertIn('lokale Sicherung bleibt erhalten',str(error.exception));self.assertNotIn('private remote error',str(error.exception))
        self.assertTrue(destination.exists());self.assertFalse(source.exists())
        with patch.object(core,'archive_file',return_value=destination):self.assertTrue(core.verify_archive(plan,destination.name)['verified'])

    def test_compressed_backup_with_sql_roundtrip(self):
        root=Path(self.tmp.name);source=root/'source.tar';destination=root/'backup.tar.gz';dump=root/'database.sql'
        payload=b'example file';sql=b'CREATE TABLE test (id INT);';dump.write_bytes(sql)
        manifest={'version':1,'files':{'docs/test.txt':{'size':len(payload),'sha256':hashlib.sha256(payload).hexdigest()}},'skipped':0}
        with tarfile_local(source) as archive:
            entry=__import__('tarfile').TarInfo('files/docs/test.txt');entry.size=len(payload);archive.addfile(entry,io.BytesIO(payload))
            value=json.dumps(manifest).encode();entry=__import__('tarfile').TarInfo('manifest.json');entry.size=len(value);archive.addfile(entry,io.BytesIO(value))
        bundle_backup.compressed_copy(source,destination,dump,'ncdb')
        restore=root/'restore';restore.mkdir()
        with patch.object(core,'archive_file',return_value=destination):result=core.verify_archive({},destination.name,restore)
        self.assertTrue(result['verified']);self.assertEqual(result['files'],2)
        self.assertEqual((restore/'__serverlotse_database__/ncdb.sql').read_bytes(),sql)
        self.assertEqual((restore/'docs/test.txt').read_bytes(),payload)
        self.assertTrue(source.exists())


def tarfile_local(path):
    import tarfile
    return tarfile.open(path,'w')


if __name__=='__main__':unittest.main()
