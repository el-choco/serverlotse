"""No Docker, host commands, registry traffic, notifications or speedtests are run."""
import copy
import io
import json
import os
from pathlib import Path
import tarfile
import tempfile
import time
import unittest
from unittest.mock import Mock,patch
import admin_core as core
import advanced
import admin_demo
import workbench
import workbench_demo
import docker_tools as docker
import guardian
import registry_check
import backup_probe

A='a'*64;B='b'*64;IMAGE='sha256:'+'c'*64


def container():
    return {'Id':A,'Name':'/app','Image':IMAGE,'Config':{'Image':'nginx:stable-alpine','Env':['TZ=Europe/Berlin','PASSWORD=secret-test-value','CUSTOM=private-test-value'],
        'Labels':{},'ExposedPorts':{'80/tcp':{}},'Cmd':['nginx'],'Volumes':{'/data':{}}},
        'HostConfig':{'NetworkMode':'bridge','Binds':['/srv/app:/data']},
        'Mounts':[{'Type':'bind','Source':'/srv/app','Destination':'/data','RW':True,'Propagation':'rprivate'},
                  {'Type':'volume','Name':'anonymous-data','Destination':'/db','RW':True}],
        'State':{'Running':True},'NetworkSettings':{'Networks':{'bridge':{}}}}


class WorkbenchTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name)
        self.state=patch.object(core,'STATE',self.root/'state');self.state.start();core.initialize();core.PREVIEWS.clear()
        guardian.LAST.clear();guardian.CPU_PREVIOUS.clear()

    def tearDown(self):self.state.stop();self.tmp.cleanup()

    def test_registry_and_defaults_are_complete_and_inactive(self):
        self.assertEqual(core.LAB_OPS,workbench.OPS)
        cfg=guardian.config()
        for key in ['enabled','fim','certificates','http','oom','logrotate','speedtest']:self.assertFalse(cfg[key])
        self.assertEqual(core.ENV['DOCKER_HOST'],'unix:///var/run/docker.sock');self.assertNotIn('DOCKER_CONTEXT',core.ENV)

    def test_environment_masks_unknown_values_and_nested_audit_updates(self):
        visible=docker.environment(container())
        self.assertIn('Europe/Berlin',json.dumps(visible));self.assertNotIn('secret-test-value',json.dumps(visible));self.assertNotIn('private-test-value',json.dumps(visible))
        data={'operation':'lab_env','env_updates':{'PASSWORD':'new-private','CUSTOM':'also-private','OLD':None}}
        for visible in [core.clean(data),core.clean(data,audit=True),admin_demo.safe_preview(data)]:
            self.assertNotIn('new-private',json.dumps(visible));self.assertNotIn('also-private',json.dumps(visible));self.assertIn('PASSWORD',json.dumps(visible))

    def test_clone_uses_local_image_and_never_shares_writable_data_by_default(self):
        info=container();spec=docker.clone_spec(info,'copy')
        self.assertEqual(spec['Image'],IMAGE);self.assertNotIn('Mounts',spec['HostConfig']);self.assertNotIn('PortBindings',spec['HostConfig'])
        spec=docker.clone_spec(info,'copy',readonly=True)
        self.assertTrue(all(row['ReadOnly'] for row in spec['HostConfig']['Mounts']))
        self.assertEqual(info['HostConfig']['Binds'],['/srv/app:/data'])

    def test_clone_does_not_treat_a_readonly_docker_socket_as_safe(self):
        info=container();info['Mounts']=[{'Type':'bind','Source':'/var/run/docker.sock','Destination':'/var/run/docker.sock','RW':True}]
        with self.assertRaises(ValueError):docker.clone_spec(info,'copy',readonly=True)

    def test_env_replacement_preserves_binds_and_anonymous_volumes(self):
        spec=docker.clone_spec(container(),'app',env_updates={'PASSWORD':'changed','CUSTOM':None})
        self.assertIn('PASSWORD=changed',spec['Env']);self.assertFalse(any(row.startswith('CUSTOM=') for row in spec['Env']))
        self.assertEqual({row['Target'] for row in spec['HostConfig']['Mounts']},{'/data','/db'})
        self.assertEqual(next(r['Source'] for r in spec['HostConfig']['Mounts'] if r['Target']=='/db'),'anonymous-data')
        self.assertNotIn('Binds',spec['HostConfig'])

    def test_compose_and_privileged_containers_do_not_get_blind_replacements(self):
        for change in ['compose','privileged','host','container']:
            row=container()
            if change=='compose':row['Config']['Labels']={'com.docker.compose.project':'app'}
            elif change=='privileged':row['HostConfig']['Privileged']=True
            else:row['HostConfig']['NetworkMode']='host' if change=='host' else 'container:'+B
            with self.assertRaises(ValueError):docker.clone_spec(row,'copy',env_updates={'PORT':'80'})

    def test_names_and_env_values_reject_options_and_multiline_input(self):
        for value in ['--privileged','serverlotse-copy','../../app','a;sh']:
            with self.assertRaises(ValueError):docker.name(value)
        for data in [{'BAD-NAME':'value'},{'KEY':'line1\nline2'},{'KEY':'x\x00'}]:
            with self.assertRaises(ValueError):docker.updates(data)

    def test_janitor_does_not_include_own_container_or_referenced_volumes(self):
        rows=[{'Id':A,'Names':['/old'],'State':'exited','ImageID':IMAGE},{'Id':B,'Names':['/serverlotse-bootstrap-1'],'State':'exited','ImageID':'sha256:'+'e'*64}]
        def engine(method,path,body=None):
            if path.startswith('/volumes'):return {'Volumes':[{'Name':'orphan'}]}
            if path.startswith('/images'):return [{'Id':IMAGE,'RepoTags':['old:tag']},{'Id':'sha256:'+'e'*64,'RepoTags':['serverlotse:0.7.0']}]
            if path=='/networks':return [{'Id':'bridge','Name':'bridge'},{'Id':'used','Name':'custom','Labels':{}},{'Id':'unused','Name':'old-net','Labels':{}}]
            if path=='/networks/used':return {'Containers':{A:{}}}
            if path=='/networks/unused':return {'Containers':{}}
            raise AssertionError(path)
        with patch.object(docker,'inventory',return_value=rows),patch.object(docker,'api',side_effect=engine):
            plan=docker.janitor_plan()
        self.assertEqual([r['id'] for r in plan['containers']],[A]);self.assertEqual(plan['volumes'],['orphan']);self.assertEqual(plan['networks'],['unused']);self.assertEqual(len(plan['images']),1)

    def test_janitor_preserves_retained_image_parents_and_orders_unused_children_first(self):
        parent='sha256:'+'1'*64;child='sha256:'+'2'*64;free_parent='sha256:'+'3'*64;free_child='sha256:'+'4'*64
        images=[{'Id':parent,'RepoTags':['base:tag']},{'Id':child,'ParentId':parent,'RepoTags':['app:tag']},
                {'Id':free_parent,'RepoTags':['old-base:tag']},{'Id':free_child,'ParentId':free_parent,'RepoTags':['old-app:tag']}]
        def engine(method,path,body=None):
            if path.startswith('/images'):return images
            if path.startswith('/volumes'):return {'Volumes':[]}
            if path=='/networks':return []
            raise AssertionError(path)
        with patch.object(docker,'inventory',return_value=[{'Id':A,'State':'running','Names':['/app'],'ImageID':child}]),patch.object(docker,'api',side_effect=engine):plan=docker.janitor_plan()
        self.assertEqual([r['id'] for r in plan['images']],[free_child,free_parent])

    def test_janitor_requires_delete_word_and_revalidates_changed_targets(self):
        targets={'containers':[],'images':[],'volumes':['orphan'],'networks':[]}
        with patch.object(docker,'janitor_plan',return_value=targets),patch.object(core,'enqueue') as enqueue:
            preview=core.prepare({'operation':'lab_janitor'})
            self.assertEqual(preview['confirmation'],'LOESCHEN')
            with self.assertRaises(ValueError):core.execute({'nonce':preview['nonce'],'confirmation':'AUSFUEHREN'})
            enqueue.assert_not_called()
        with core.db() as db:db.execute('INSERT INTO audit VALUES(?,?,?,?,?,?)',('f'*24,time.time(),'lab_janitor','{}','queued',''))
        core.MUTEX.acquire()
        with patch.object(docker,'janitor_plan',return_value={**targets,'volumes':[]}),patch.object(workbench,'apply') as apply:
            core.worker('f'*24,{'operation':'lab_janitor','targets':targets});apply.assert_not_called()
        self.assertEqual(core.audit_detail('f'*24)['status'],'error')

    def test_janitor_deletes_exact_targets_without_force(self):
        targets={'containers':[{'id':A}],'images':[{'id':IMAGE,'tags':['old:tag']}],'volumes':['orphan'],'networks':['network-id']}
        with patch.object(docker,'api',return_value={}) as engine,patch.object(core,'command',return_value='') as command:
            docker.apply({'operation':'lab_janitor','targets':targets})
        calls=[call.args[:2] for call in engine.call_args_list]
        self.assertEqual(len(calls),4);self.assertTrue(all(method=='DELETE' and 'force' not in path for method,path in calls));self.assertIn(('DELETE','/volumes/orphan'),calls)
        self.assertEqual(command.call_args.args[0],['docker','builder','prune','--all','--force'])

    def test_failed_env_start_deletes_only_new_container_and_restores_old_name(self):
        info=container();inspections=[info,{'State':{'Running':False}},{'State':{'Running':False}}]
        def engine(method,path,body=None):return {'Id':B} if path.startswith('/containers/create') else {}
        with patch.object(docker,'inspect',side_effect=inspections),patch.object(docker,'api',side_effect=engine) as api,patch.object(docker.time,'sleep'):
            with self.assertRaises(ValueError):docker.apply({'operation':'lab_env','container':A,'was_running':True,'env_updates':{'PORT':'80'}})
        deleted=[call.args[1] for call in api.call_args_list if call.args[0]=='DELETE']
        self.assertEqual(deleted,['/containers/'+B]);self.assertTrue(any(call.args[1]=='/containers/'+A+'/rename?name=app' for call in api.call_args_list))

    def test_compose_env_override_keeps_secrets_off_argv_and_rolls_file_back(self):
        path=self.root/'override.json';old={'x-serverlotse-environment':True,'services':{'web':{'environment':{'PASSWORD':'old-secret'}}}}
        path.write_text(json.dumps(old),encoding='utf-8')
        plan={'operation':'lab_env','container':A,'compose':True,'override':str(path),'directory':str(self.root),
              'project':'app','service':'web','files':[str(self.root/'compose.yaml')],'env_updates':{'PASSWORD':'new-secret'}}
        def atomic(file,raw,mode=0o644):Path(file).write_bytes(raw)
        with patch.object(docker,'inspect',return_value=container()),patch.object(advanced,'atomic_write',side_effect=atomic),patch.object(core,'command',side_effect=ValueError('sensitive raw error')) as command:
            with self.assertRaises(ValueError) as error:docker.apply(plan)
        self.assertEqual(json.loads(path.read_text(encoding='utf-8')),old)
        self.assertNotIn('sensitive raw error',str(error.exception));self.assertNotIn('new-secret',str(command.call_args_list))

    def test_registry_refuses_credentials_and_bad_auth_realm(self):
        for value in ['https://user:pass@host/image','--evil','sha256:'+'a'*64]:
            with self.assertRaises(ValueError):registry_check.reference(value)
        self.assertEqual(registry_check.reference('nginx:stable-alpine'),('registry-1.docker.io','library/nginx','stable-alpine'))
        from urllib.error import HTTPError
        opener=Mock();opener.open.side_effect=HTTPError('https://registry-1.docker.io',401,'auth',{'WWW-Authenticate':'Bearer realm="https://evil.example/token",service="x"'},None)
        with self.assertRaises(ValueError):registry_check.fetch('registry-1.docker.io','library/nginx','latest',opener=opener)
        self.assertEqual(opener.open.call_count,1)

    def test_registry_compares_matching_platform_config_not_index_digest(self):
        index={'manifests':[{'digest':'sha256:'+'1'*64,'platform':{'os':'linux','architecture':'amd64'}},{'digest':'sha256:'+'2'*64,'platform':{'os':'linux','architecture':'arm64'}}]}
        with patch.object(docker,'api',return_value={'Id':IMAGE,'Os':'linux','Architecture':'amd64'}),patch.object(registry_check,'fetch',side_effect=[(index,None),({'config':{'digest':IMAGE}},None)]) as fetch:
            self.assertFalse(registry_check.check(container())['available']);self.assertEqual(fetch.call_args.args[2],'sha256:'+'1'*64)

    def test_registry_rejects_corrupt_content_addressed_manifest(self):
        opener=Mock();opener.open.return_value=io.BytesIO(b'{"config":{"digest":"fake"}}')
        with self.assertRaises(ValueError):registry_check.fetch('registry-1.docker.io','library/nginx','sha256:'+'1'*64,opener=opener)

    def test_fim_compares_content_permissions_and_new_or_removed_files(self):
        before={'/etc/a':{'sha256':'1','mode':420},'/etc/deleted':{'sha256':'2'}}
        after={'/etc/a':{'sha256':'1','mode':384},'/etc/new':{'sha256':'3'}}
        changes=guardian.fim_diff(before,after)
        self.assertEqual({r['change'] for r in changes},{'neu','entfernt','verändert'})

    def test_fim_hashes_only_bounded_regular_file_contents(self):
        path=self.root/'critical';path.write_bytes(b'content')
        with patch.object(guardian.os,'O_NONBLOCK',0,create=True),patch.object(core,'local_path',side_effect=lambda p:Path(p)),patch.object(core,'secure_open',side_effect=lambda p,flags:os.open(p,os.O_RDONLY)):
            snapshot=guardian.fim_snapshot([str(path)])
        import hashlib
        self.assertEqual(snapshot['files'][str(path)]['sha256'],hashlib.sha256(b'content').hexdigest());self.assertEqual(snapshot['skipped'],[])

    def test_fim_tracks_symlink_target_without_opening_its_contents(self):
        import types,stat
        path=self.root/'link';path.touch()
        info=types.SimpleNamespace(st_mode=stat.S_IFLNK|0o777,st_uid=0,st_gid=0)
        with patch.object(core,'local_path',side_effect=lambda p:Path(p)),patch.object(Path,'lstat',return_value=info),patch.object(guardian.os,'readlink',return_value='/private/target'),patch.object(core,'secure_open') as opened:
            snapshot=guardian.fim_snapshot([str(path)])
        opened.assert_not_called();self.assertIn('symlink',snapshot['files'][str(path)]);self.assertNotIn('/private/target',json.dumps(snapshot))

    def test_unknown_smart_attributes_are_not_guessed(self):
        self.assertEqual(guardian.wear_value({'nvme_smart_health_information_log':{'percentage_used':7}})['remaining'],93)
        self.assertEqual(guardian.wear_value({'nvme_smart_health_information_log':{'percentage_used':120}})['remaining'],0)
        self.assertIsNone(guardian.wear_value({'ata_smart_attributes':{'table':[{'id':177,'name':'Unknown','value':99}]}})['remaining'])
        self.assertIsNone(guardian.wear_value({'nvme_smart_health_information_log':{'percentage_used':-1}})['remaining'])

    def test_missing_certificate_tool_is_not_reported_as_no_certificates(self):
        with patch.object(guardian.shutil,'which',return_value=None),patch.object(docker,'inventory') as inventory:
            with self.assertRaisesRegex(ValueError,'openssl'):guardian.certificates()
        inventory.assert_not_called()

    def test_http_checker_reports_errors_without_following_redirects(self):
        from urllib.error import HTTPError
        opener=Mock();opener.open.side_effect=HTTPError('https://example.com',502,'gateway',{},None)
        with patch.object(guardian,'build_opener',return_value=opener):result=guardian.http_check('https://example.com')
        self.assertFalse(result['ok']);self.assertEqual(result['status'],502)
        for url in ['file:///etc/passwd','https://user:pass@example.com','https://example.com?token=private']:
            with self.assertRaises(ValueError):guardian.target_url(url)

    def test_disabled_guardian_never_sends_or_enqueues_actions(self):
        with patch.object(guardian,'cpu_snapshot',return_value=[]),patch.object(docker,'sample'),patch.object(core,'enqueue') as enqueue,patch.object(advanced,'notify') as notify,patch.object(guardian,'http_check') as http:
            guardian.tick(1000)
        enqueue.assert_not_called();notify.assert_not_called();http.assert_not_called()

    def test_guardian_can_be_disabled_after_a_tool_or_config_was_removed(self):
        current={**guardian.config(),'enabled':True,'speedtest':True,'speedtest_consent':True,
                 'fim_paths':['/etc/no-longer-present'],'rotation_configs':[{'path':'/etc/logrotate.d/removed','hash':'old'}]}
        with patch.object(guardian,'config',return_value=current),patch.object(core,'local_path',side_effect=lambda p,**kwargs:Path(p)),patch.object(guardian.shutil,'which',return_value=None),patch.object(guardian,'rotation_path') as rotation:
            cfg=guardian.normalize({'enabled':False})
        self.assertFalse(cfg['enabled']);rotation.assert_not_called()

    def test_rotation_plan_is_stable_when_logs_grow(self):
        config=self.root/'nginx';config.write_text('/var/log/nginx/*.log { compress }')
        with patch.object(guardian,'rotation_path',return_value=config),patch.object(core,'command',return_value=''),patch.object(guardian,'rotation_matches',side_effect=[[{'path':'/var/log/a','bytes':100}],[{'path':'/var/log/a','bytes':9999}]]):
            first=guardian.validate({'operation':'lab_rotate','path':str(config)});second=guardian.validate(first)
        self.assertEqual(first,second)

    def test_speedtest_requires_consent_and_filters_out_ip_and_result_url(self):
        with patch.object(guardian.shutil,'which',return_value='/usr/bin/speedtest-cli'):
            with self.assertRaises(ValueError):guardian.validate({'operation':'lab_speedtest','consent':False})
        result={'ping':10,'download':100000000,'upload':20000000,'client':{'ip':'private-ip'},'server':{'name':'test'},'share':'private-url'}
        with patch.object(guardian.shutil,'which',return_value='/usr/bin/speedtest-cli'),patch.object(core,'command',return_value=json.dumps(result)) as command:row=guardian.speedtest('community')
        self.assertEqual(row['download_mbps'],100);self.assertNotIn('private-ip',json.dumps(row));self.assertNotIn('private-url',json.dumps(row));self.assertIn('--secure',command.call_args.args[0])

    def test_invalid_speedtest_metrics_are_reported_as_failure(self):
        raw={'ping':10,'download':float('nan'),'upload':100,'server':{}}
        with patch.object(guardian.shutil,'which',return_value='/usr/bin/speedtest-cli'),patch.object(core,'command',return_value=json.dumps(raw)):
            with self.assertRaises(ValueError):guardian.speedtest('community')

    def test_cpu_peak_capture_is_independent_and_rate_limited(self):
        top=[{'pid':123,'name':'worker','cpu':300,'uid':1000}]
        with patch.object(guardian,'cpu_snapshot',return_value=top),patch.dict(guardian.sensors.PREVIOUS,{'latest':{'time':1000,'cpu':98}}):
            guardian.record_cpu(1000);guardian.record_cpu(1001)
        rows=advanced.state('cpu_peaks');self.assertEqual(len(rows),1);self.assertEqual(rows[0]['processes'],top)

    def test_sql_failure_cleans_only_own_isolated_test_container(self):
        path=self.root/'backup.tar.gz'
        with tarfile.open(path,'w:gz') as tar:
            raw=b'CREATE DATABASE app;';member=tarfile.TarInfo('files/__serverlotse_database__/app.sql');member.size=len(raw);tar.addfile(member,io.BytesIO(raw))
        cfg={'database':'app','container':A};plan={'id':'test','archive':path.name,'image':IMAGE,'database':'app'}
        def engine(method,url,body=None):return {'Id':B} if url.startswith('/containers/create') else {}
        process=Mock(returncode=1);process.wait.return_value=1
        with patch.object(core,'config',return_value=cfg),patch.object(core,'verify_archive',return_value={'verified':True}),patch.object(core,'archive_file',return_value=path),patch.object(core,'command',return_value='ready') as command,patch.object(docker,'api',side_effect=engine) as api,patch.object(docker,'inspect',return_value={'Config':{'Labels':{'serverlotse.restore-test':'true'}}}),patch.object(backup_probe.subprocess,'Popen',return_value=process):
            with self.assertRaises(ValueError):backup_probe.apply(plan)
        spec=next(call.args[2] for call in api.call_args_list if call.args[1].startswith('/containers/create'))
        self.assertTrue(spec['NetworkDisabled']);self.assertEqual(spec['HostConfig']['NetworkMode'],'none');self.assertTrue(spec['HostConfig']['ReadonlyRootfs']);self.assertNotIn('Binds',spec['HostConfig'])
        deletes=[call.args[1] for call in api.call_args_list if call.args[0]=='DELETE'];self.assertEqual(deletes,['/containers/'+B+'?force=true&v=true'])
        self.assertTrue(all(A not in call.args[0] for call in command.call_args_list))

    def test_all_demo_views_work_without_host_access(self):
        for view in ['lab_docker','lab_environment','lab_health','lab_networks','lab_ports','lab_dotenv','lab_guardian','lab_sessions','lab_certificates','lab_disks','lab_history','lab_backup_options','lab_logs','lab_summary']:
            with self.subTest(view=view):self.assertIsInstance(workbench_demo.read({'view':view}),dict)
