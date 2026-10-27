import base64
import contextlib
import json
from pathlib import Path
import tempfile
import time
import unittest
from unittest.mock import patch,Mock
import admin_core as core
import advanced
import expert_tools as host
import network_extras as net
import docker_extras as extra
import docker_tools as docker
import workbench_demo
import deploy_host


class ExpertTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name)
        self.state=patch.object(core,'STATE',self.root/'state');self.state.start();core.initialize()
        self.writer=patch.object(advanced,'atomic_write',side_effect=lambda path,data,mode:path.write_bytes(data));self.writer.start()
    def tearDown(self):self.writer.stop();self.state.stop();self.tmp.cleanup()

    def test_all_expert_modules_in_bootstrap(self):
        for name in ['expert_tools.py','network_extras.py','docker_extras.py']:self.assertIn(name,deploy_host.PYTHON_FILES)

    def test_secrets_never_in_preview_or_audit(self):
        raw={'ddns_token':'secret-one','ddns_password':'secret-two','config_text':'secret-three','encoded_data':'secret-four','compose_document':{'secret':'secret-five'},'services':[{'env_updates':{'ANY':'secret-six'}}]}
        for result in [advanced.public(raw),advanced.public(raw,True),core.clean(raw,audit=True)]:
            self.assertNotIn('secret-',json.dumps(result))

    def test_cron_daily_weekday_and_macro(self):
        self.assertEqual(host.describe_cron(['0','3','*','*','2']),'Jeden Dienstag um 03:00')
        self.assertEqual(host.describe_cron(['*/5','*','*','*','*']),'Alle 5 Minuten')
        self.assertEqual(host.describe_cron(['@reboot']),'Beim Systemstart')

    def test_analyzer_never_executes_command(self):
        with patch.object(core,'command') as command:
            for text in ['rm -rf /tmp/example; touch /tmp/other','$(id)','rm /tmp/example | sh','echo test']:
                self.assertFalse(host.analyze_command(text)['supported'])
            answer=host.analyze_command('chmod -R 750 relative-dir')
            self.assertTrue(answer['recursive']);self.assertEqual(answer['value'],'750');command.assert_not_called()

    def test_panic_has_only_own_tables_and_explicit_addresses(self):
        rules=host.panic_rules(['192.0.2.10','2001:db8::1','192.0.2.10'])
        self.assertIn('table inet serverlotse_panic',rules);self.assertIn('table bridge serverlotse_panic',rules)
        self.assertNotIn('flush',rules);self.assertIn('policy drop',rules);self.assertIn('192.0.2.10',rules)
        for bad in [[],['192.0.2.10;flush ruleset'],['example.com']]:
            with self.assertRaises(ValueError):host.panic_rules(bad)

    def test_panic_requires_timer_before_firewall(self):
        plan={'operation':'lab_panic','rules':'fixture','seconds':60};events=[]
        with patch.object(host,'ticket_lock',contextlib.nullcontext),patch.object(host,'arm',side_effect=lambda *a:events.append('timer')),patch.object(core,'command',side_effect=lambda *a,**kw:events.append('firewall')):
            host.apply(plan)
        self.assertEqual(events,['timer','firewall'])

    def test_timer_failure_does_not_apply_firewall(self):
        with patch.object(host,'ticket_lock',contextlib.nullcontext),patch.object(host,'arm',side_effect=ValueError('timer unavailable')),patch.object(core,'command') as command:
            with self.assertRaises(ValueError):host.apply({'operation':'lab_panic','rules':'fixture','seconds':60})
            command.assert_not_called()

    def test_config_rejects_stale_editor(self):
        path=self.root/'nginx.conf';path.write_text('original')
        with patch.object(host,'config_path',return_value=path):
            with self.assertRaises(ValueError):host.validate({'operation':'lab_config_write','kind':'nginx','config_text':'new','before_hash':'stale'})
            plan=host.validate({'operation':'lab_config_write','kind':'nginx','config_text':'new','before_hash':host.hash_bytes(b'original')})
            self.assertEqual(host.validate(plan),plan)

    def test_config_apply_arms_timer_and_retains_private_backup(self):
        path=self.root/'nginx.conf';path.write_text('original')
        plan={'operation':'lab_config_write','kind':'nginx','config_text':'new','before_hash':host.hash_bytes(b'original'),'after_hash':host.hash_bytes(b'new'),'seconds':30}
        with patch.object(host,'ticket_lock',contextlib.nullcontext),patch.object(host,'config_path',return_value=path),patch.object(core,'command') as command:
            result=host.apply(plan)
        self.assertEqual(command.call_args_list[0].args[0][0],'systemd-run')
        ticket=host.ticket(result['id']);self.assertEqual(ticket['status'],'pending');self.assertEqual(base64.b64decode(ticket['backup']),b'original')
        self.assertEqual(path.read_text(),'new')

    def test_config_failed_validation_restores_original_immediately(self):
        path=self.root/'nginx.conf';path.write_text('original');failed=False
        def run(args,**kwargs):
            nonlocal failed
            if args==['nginx','-t'] and not failed:failed=True;raise ValueError('fixture invalid')
            return ''
        plan={'operation':'lab_config_write','kind':'nginx','config_text':'new','before_hash':host.hash_bytes(b'original'),'after_hash':host.hash_bytes(b'new'),'seconds':30}
        with patch.object(host,'ticket_lock',contextlib.nullcontext),patch.object(host,'config_path',return_value=path),patch.object(core,'command',side_effect=run):
            with self.assertRaises(ValueError):host.apply(plan)
        self.assertEqual(path.read_text(),'original');self.assertEqual(host.pending()[0]['status'],'reverted')

    def test_rollback_restores_exact_original(self):
        path=self.root/'nginx.conf';path.write_text('new');ident='a'*24
        host.save_ticket({'id':ident,'kind':'nginx','status':'pending','expires':time.time()+30,'backup':base64.b64encode(b'original').decode(),'mode':0o600,'after_hash':host.hash_bytes(b'new')})
        with patch.object(host,'ticket_lock',contextlib.nullcontext),patch.object(host,'config_path',return_value=path),patch.object(core,'command'):
            result=host.rollback(ident)
        self.assertEqual(result['status'],'reverted');self.assertEqual(path.read_text(),'original')

    def test_rollback_conflict_does_not_overwrite_later_edit(self):
        path=self.root/'nginx.conf';path.write_text('someone-else');ident='b'*24
        host.save_ticket({'id':ident,'kind':'nginx','status':'pending','expires':time.time()+30,'backup':base64.b64encode(b'original').decode(),'mode':0o600,'after_hash':host.hash_bytes(b'new')})
        with patch.object(host,'ticket_lock',contextlib.nullcontext),patch.object(host,'config_path',return_value=path),patch.object(core,'command') as command:
            self.assertEqual(host.rollback(ident)['status'],'conflict');command.assert_not_called()
        self.assertEqual(path.read_text(),'someone-else')

    def test_expired_config_cannot_be_kept(self):
        ident='c'*24;host.save_ticket({'id':ident,'kind':'nginx','status':'pending','expires':time.time()-1})
        with patch.object(host,'ticket_lock',contextlib.nullcontext):
            with self.assertRaises(ValueError):host.rollback(ident,True)

    def test_ticket_ids_cannot_traverse(self):
        for ident in ['../passwd','a'*23,'a'*24+'/']:
            with self.assertRaises(ValueError):host.ticket_path(ident)

    def test_apt_protects_access_kernel_and_essential_packages(self):
        with patch.object(core,'command',side_effect=['Remv linux-image-example [1]\nPurg openssh-server [2]\nRemv example [3]','example\tyes\trequired']):
            self.assertEqual(host.apt_cleanup()['blocked'],['example','linux-image-example','openssh-server'])

    def test_apt_changed_plan_never_executes(self):
        with patch.object(host,'apt_cleanup',return_value={'packages':['new'],'blocked':[]}),patch.object(core,'command') as command:
            with self.assertRaises(ValueError):host.apply({'operation':'lab_apt_clean','packages':['old']})
            command.assert_not_called()

    def config(self):
        return {'enabled':False,'consent':True,'provider':'cloudflare','domain':'app.example.com','zone':'','zone_id':'a'*32,'record_id':'b'*32,'record_type':'A','interval':15,'ddns_token':'secret-token'}

    def test_ddns_off_by_default_and_secrets_masked(self):
        self.assertFalse(net.cfg()['enabled']);advanced.state('ddns_config',self.config())
        self.assertNotIn('secret-token',json.dumps(net.read({'view':'lab_ddns'})))

    def test_ddns_clear_and_plan_revalidation(self):
        advanced.state('ddns_config',self.config())
        plan=net.validate({'operation':'lab_ddns_save','config':{'enabled':False,'clear_credentials':True}})
        self.assertEqual(net.validate(plan),plan);net.apply(plan);self.assertNotIn('ddns_token',net.cfg())

    def test_ddns_stale_save_rejected(self):
        plan=net.validate({'operation':'lab_ddns_save','config':{'enabled':False}})
        advanced.state('ddns_config',self.config())
        with self.assertRaises(ValueError):net.validate(plan)

    def test_ddns_disabled_config_can_always_be_stopped(self):
        advanced.state('ddns_config',{**self.config(),'enabled':True,'zone_id':'bad'})
        self.assertFalse(net.normalize({'enabled':False})['enabled'])
        with self.assertRaises(ValueError):net.normalize({'enabled':True,'consent':False})

    def test_cloudflare_exact_existing_record_and_partial_update(self):
        current=self.config()
        with patch.object(net,'public_ip',return_value='198.51.100.7'),patch.object(net,'request',side_effect=[{'success':True,'result':{'name':'app.example.com','type':'A','content':'198.51.100.6'}},{'success':True}]) as request:
            self.assertTrue(net.update(current)['changed']);self.assertEqual(request.call_args.args[1],'PATCH');self.assertEqual(request.call_args.args[3],{'content':'198.51.100.7'})

    def test_cloudflare_wrong_record_not_changed(self):
        with patch.object(net,'public_ip',return_value='198.51.100.7'),patch.object(net,'request',return_value={'success':True,'result':{'name':'other.example.com','type':'A'}}) as request:
            with self.assertRaises(ValueError):net.update(self.config())
            self.assertEqual(request.call_count,1)

    def test_godaddy_multiple_records_not_replaced(self):
        current={**self.config(),'provider':'godaddy','zone':'example.com'}
        with patch.object(net,'public_ip',return_value='198.51.100.7'),patch.object(net,'request',return_value=[{},{}]) as request:
            with self.assertRaises(ValueError):net.update(current)
            self.assertEqual(request.call_count,1)

    def test_namecheap_rejects_error_response(self):
        current={**self.config(),'provider':'namecheap','zone':'example.com','ddns_password':'private'}
        with patch.object(net,'public_ip',return_value='198.51.100.7'),patch.object(net,'request',return_value='<interface-response><ErrCount>1</ErrCount></interface-response>'):
            with self.assertRaises(ValueError):net.update(current)

    def test_network_request_errors_do_not_leak_secret_url(self):
        with patch.object(net,'build_opener',side_effect=RuntimeError('https://private?password=secret')):
            with self.assertRaises(ValueError) as result:net.request('https://private?password=secret')
        self.assertNotIn('secret',str(result.exception))

    def test_ddns_tick_skips_during_host_action(self):
        advanced.state('ddns_config',{**self.config(),'enabled':True})
        with patch.object(core,'POWER_UNTIL',time.time()+30),patch.object(net,'update') as update:net.tick();update.assert_not_called()

    def test_volume_paths_and_sensitive_names_rejected(self):
        for path in ['/etc/passwd','../data','folder/../../outside','a\\b']:
            with self.assertRaises(ValueError):extra.relative(path)
        for name in ['.env','state.sqlite','dump.sql','docker.sock','PG_VERSION']:
            with self.assertRaises(ValueError):extra.writable_name(name)
        self.assertEqual(extra.relative('folder/config.txt'),['folder','config.txt'])

    def test_trivy_scan_isolated_and_checks_exit_status(self):
        ident='d'*64;calls=[]
        def command(args,**kwargs):
            calls.append(args)
            if args[1:3]==['image','save']:Path(args[args.index('--output')+1]).write_bytes(b'fixture-image')
            if args[1]=='create':
                mount=next(value for value in args if value.startswith('type=bind,source=') and value.endswith(',target=/out'))
                folder=Path(mount.split('source=',1)[1].rsplit(',target=',1)[0]);(folder/'report.json').write_text('{"Results":[]}')
                return ident
            return ''
        with patch.object(core,'command',side_effect=command),patch.object(docker,'api',return_value={'State':{'Running':False,'ExitCode':0}}) as api:
            result=extra.scan({'image':'sha256:'+'e'*64})
        create=next(c for c in calls if c[1]=='create');self.assertIn('--read-only',create);self.assertIn('ALL',create)
        self.assertNotIn('/var/run/docker.sock',' '.join(create));self.assertEqual(result['counts']['HIGH'],0)
        self.assertEqual(api.call_args.args[0],'DELETE');self.assertIn(ident,api.call_args.args[1])
        self.assertEqual(list(core.STATE.glob('trivy-*')),[])

    def test_builder_preserves_literal_values_and_is_idempotent(self):
        data={'name':'example','directory':str(self.root),'services':[{'name':'web','image':'nginx:stable-alpine','env_updates':{'CUSTOM':'a$b"c'}}]}
        with patch.object(core,'local_path',side_effect=lambda x,**kw:Path(x)),patch.object(core,'private_destination'),patch.object(docker,'inventory',return_value=[]):
            plan=extra.builder(data);self.assertEqual(extra.validate(plan),plan)
        self.assertEqual(plan['compose_document']['services']['web']['environment']['CUSTOM'],'a$$b"c')

    def test_builder_rejects_unsafe_image_and_mount_syntax(self):
        base={'name':'example','directory':str(self.root)}
        with patch.object(core,'local_path',side_effect=lambda x,**kw:Path(x)),patch.object(core,'private_destination'),patch.object(docker,'inventory',return_value=[]):
            for service in [{'name':'web','image':'image; touch /tmp/file'},{'name':'web','image':'nginx','volume_target':'/data:${SECRET}'}]:
                with self.assertRaises(ValueError):extra.builder({**base,'services':[service]})

    def test_all_new_demo_views_are_pure_fixtures(self):
        views=['lab_memory','lab_inodes','lab_inode_watch','lab_cron','lab_orphans','lab_analyze','lab_undo','lab_native_config','lab_apt_cleanup','lab_ddns','lab_domain_targets','lab_dns_check','lab_firewall_map','lab_volumes','lab_volume_files','lab_builder_load','lab_trivy_result']
        with patch.object(core,'command') as command,patch.object(net,'request') as request,patch.object(docker,'api') as api:
            for view in views:self.assertIsInstance(workbench_demo.read({'view':view}),dict)
            command.assert_not_called();request.assert_not_called();api.assert_not_called()

    def cron_paths(self):
        cron,units,scripts=self.root/'cron.d',self.root/'system',self.root/'jobs';cron.mkdir();units.mkdir()
        users=Mock();users.getpwnam=Mock(side_effect=lambda name:None if name in {'root','www-data'} else (_ for _ in ()).throw(KeyError(name)))
        return [patch.object(host,'CRON_DIR',cron),patch.object(host,'UNIT_DIR',units),patch.object(host,'JOB_SCRIPTS',scripts),patch.dict('sys.modules',{'pwd':users})]

    def test_cron_schedule_validation_and_systemd_calendar(self):
        self.assertEqual(host.on_calendar(host.cron_schedule('30 2 * * *')),'*-*-* 02:30:00')
        self.assertEqual(host.on_calendar(host.cron_schedule('*/15 * * * 1-5')),'Mon..Fri *-*-* *:0/15:00')
        self.assertEqual(host.on_calendar(host.cron_schedule('0 */2 */3 * *')),'*-*-1/3 0/2:00:00')
        self.assertIsNone(host.on_calendar(['@reboot']))
        for bad in ['61 * * * *','* * *','5/2 * * * *','0 3 * * * echo','a b c d e','5-1 * * * *']:
            with self.assertRaises(ValueError):host.cron_schedule(bad)
        with self.assertRaises(ValueError):host.on_calendar(host.cron_schedule('0 3 1 * 1'))

    def test_cron_job_create_list_and_remove(self):
        with contextlib.ExitStack() as stack:
            for item in self.cron_paths():stack.enter_context(item)
            plan=host.validate({'operation':'lab_cron_create','name':'nacht','kind':'cron','command':'date +%F >> /tmp/x','user':'www-data','schedule':'0 3 * * 0'})
            host.apply(plan);text=(host.CRON_DIR/'serverlotse-job-nacht').read_text()
            self.assertIn('0 3 * * 0 www-data date +\\%F >> /tmp/x',text)
            self.assertEqual(host.managed_jobs()[0]['command'],'date +%F >> /tmp/x')
            with self.assertRaises(ValueError):host.validate({**plan,'operation':'lab_cron_create','kind':'systemd'})
            for data in [{'name':'Bad Name'},{'command':'a\nb'},{'user':'ghost'},{'kind':'shell'}]:
                with self.assertRaises(ValueError):host.validate({'operation':'lab_cron_create','name':'neu','kind':'cron','command':'true','schedule':'@daily',**data})
            with self.assertRaises(ValueError):host.validate({'operation':'lab_cron_remove','name':'fremd'})
            host.apply(host.validate({'operation':'lab_cron_remove','name':'nacht'}))
            self.assertEqual(host.managed_jobs(),[])

    def test_systemd_job_writes_units_and_rolls_back(self):
        with contextlib.ExitStack() as stack:
            for item in self.cron_paths():stack.enter_context(item)
            command=stack.enter_context(patch.object(core,'command',return_value=''))
            plan=host.validate({'operation':'lab_cron_create','name':'backup','kind':'systemd','command':'/usr/local/bin/b.sh','schedule':'30 2 * * *','run_now':True})
            self.assertEqual(plan['calendar'],'*-*-* 02:30:00');host.apply(plan)
            timer=(host.UNIT_DIR/'serverlotse-job-backup.timer').read_text();service=(host.UNIT_DIR/'serverlotse-job-backup.service').read_text()
            self.assertIn('OnCalendar=*-*-* 02:30:00',timer);self.assertIn('User=root',service);self.assertIn('/usr/local/bin/b.sh',(host.JOB_SCRIPTS/'backup.sh').read_text())
            calls=[c.args[0] for c in command.call_args_list]
            self.assertIn(['systemctl','enable','--now','serverlotse-job-backup.timer'],calls);self.assertIn(['systemctl','start','--no-block','serverlotse-job-backup.service'],calls)
            self.assertEqual(host.managed_jobs()[0]['kind'],'systemd')
            command.side_effect=lambda args,**kw:(_ for _ in ()).throw(ValueError('fail')) if args[:2]==['systemctl','enable'] else ''
            with self.assertRaises(ValueError):host.apply(host.validate({'operation':'lab_cron_create','name':'kaputt','kind':'systemd','command':'true','schedule':'@daily'}))
            self.assertFalse((host.UNIT_DIR/'serverlotse-job-kaputt.timer').exists())

    def test_cron_operations_are_registered(self):
        for op in ['lab_cron_create','lab_cron_remove']:self.assertIn(op,core.LAB_OPS)
