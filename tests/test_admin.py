import hashlib
import io
import json
import os
from pathlib import Path
import tarfile
import tempfile
import time
import types
import unittest
from unittest.mock import patch
import admin_core as core


class AdminTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.state = patch.object(core, 'STATE', Path(self.tmp.name)/'state')
        self.state.start()
        core.PREVIEWS.clear()
        core.initialize()

    def tearDown(self):
        self.state.stop(); self.tmp.cleanup()

    def test_invalid_operations_and_names_never_execute(self):
        with patch.object(core, 'command') as command:
            for value in ['a;reboot', '-root', 'ROOT', '../root', 'a\nroot', '']:
                with self.assertRaises(ValueError): core.checked_name(value)
            for op in ['shell', 'format', 'delete_user', 'container_exec', 'rm']:
                with self.assertRaises(ValueError): core.prepare({'operation':op})
            command.assert_not_called()

    def test_preview_is_readonly_secret_free_and_one_use(self):
        plan={'operation':'user_create','name':'newuser','password':'a-very-long-test-password'}
        with patch.object(core,'validate',return_value=plan), patch.object(core,'enqueue',return_value={'id':'job'}) as queue:
            preview=core.prepare(plan)
            self.assertNotIn('password',preview['preview'])
            self.assertNotIn(plan['password'],json.dumps(preview))
            queue.assert_not_called()
            with self.assertRaises(ValueError): core.execute({'nonce':preview['nonce'],'confirmation':'yes'})
            self.assertEqual(core.execute({'nonce':preview['nonce'],'confirmation':'AUSFUEHREN'}),{'id':'job'})
            with self.assertRaises(ValueError): core.execute({'nonce':preview['nonce'],'confirmation':'AUSFUEHREN'})
            self.assertEqual(queue.call_count,1)

    def test_expired_preview_cannot_execute(self):
        with patch.object(core,'validate',return_value={'operation':'group_create','name':'photos'}):
            preview=core.prepare({})
        core.PREVIEWS[preview['nonce']]['expires']=time.time()-1
        with patch.object(core,'enqueue') as queue:
            with self.assertRaises(ValueError): core.execute({'nonce':preview['nonce'],'confirmation':'AUSFUEHREN'})
            queue.assert_not_called()

    def test_changed_plan_is_rejected_and_audited(self):
        plan={'operation':'service','name':'example.service','verb':'start'}
        with core.db() as db:
            db.execute('INSERT INTO audit VALUES (?,?,?,?,?,?)',('test',time.time(),'service','{}','queued',''))
        core.MUTEX.acquire()
        with patch.object(core,'validate',return_value={**plan,'verb':'stop'}),patch.object(core,'apply_plan') as apply:
            core.worker('test',plan);apply.assert_not_called()
        row=core.audit_rows()['rows'][0]
        self.assertEqual(row['status'],'error')
        self.assertIn('verändert',row['result'])

    def test_restart_preserves_and_marks_incomplete_actions(self):
        with core.db() as db:
            db.execute('INSERT INTO audit VALUES (?,?,?,?,?,?)',('test',time.time(),'mount','{}','running',''))
        core.initialize()
        self.assertEqual(core.audit_rows()['rows'][0]['status'],'interrupted')

    def test_unmount_checks_running_containers(self):
        item={'Name':'/nextcloud','State':{'Running':True},'Mounts':[{'Source':'/mnt/daten/nextcloud'}]}
        def command(args,**kwargs): return 'id\n' if args[:3]==['docker','ps','-aq'] else json.dumps([item])
        with patch.object(core.shutil,'which',return_value='/bin/docker'),patch.object(core,'command',side_effect=command):
            with self.assertRaisesRegex(ValueError,'Container'):core.busy_mount(Path('/mnt/daten'))
            item['State']['Running']=False
            core.busy_mount(Path('/mnt/daten'))

    def test_fixed_container_arguments(self):
        ident='a'*64
        with patch.object(core,'command',return_value='done') as command:
            core.apply_plan({'operation':'container','verb':'restart','container':ident})
        self.assertEqual(command.call_args.args[0],['docker','restart','--time','30',ident])

    def test_no_forced_unmount(self):
        with patch.object(core,'command',return_value='') as command,patch.object(core,'busy_mount'):
            core.apply_plan({'operation':'unmount','path':'/mnt/photos'})
        self.assertEqual(command.call_args.args[0],['umount','--','/mnt/photos'])

    def test_updates_cannot_install_changed_package_plan(self):
        with patch.object(core,'updates',return_value={'simulation':'new'}),patch.object(core,'command') as command:
            with self.assertRaises(ValueError):core.apply_plan({'operation':'updates_install','simulation':'old'})
            command.assert_not_called()

    def test_service_access_and_own_agent_protected(self):
        for name in ['ssh.service','docker.service','systemd-networkd.service','serverlotse-admin.service']:
            with patch.object(core,'services',return_value={'rows':[{'name':name}]}),patch.object(core,'command') as command:
                with self.assertRaises(ValueError): core.validate({'operation':'service','name':name,'verb':'stop'})
                command.assert_not_called()

    def test_user_plan_is_stable_and_privileged_groups_rejected(self):
        account=types.SimpleNamespace(pw_name='alice',pw_uid=1000)
        groups=[types.SimpleNamespace(gr_name=name,gr_gid=index) for index,name in enumerate(['media','sudo','root'])]
        pwd=types.SimpleNamespace(getpwall=lambda:[account],getpwnam=lambda name:account)
        grp=types.SimpleNamespace(getgrall=lambda:groups)
        with patch.dict('sys.modules',{'pwd':pwd,'grp':grp}):
            plan=core.validate({'operation':'user_create','name':'bob','login':True,'groups':['media'],'password':'test-password-12345'})
            self.assertEqual(core.validate(plan),plan)
            edit=core.validate({'operation':'user_edit','name':'alice','login':True,'groups':[],'lock_action':'keep'})
            self.assertEqual(core.validate(edit),edit)
            with self.assertRaisesRegex(ValueError,'Administrative'):
                core.validate({'operation':'user_create','name':'bob','groups':['sudo']})
            account.pw_uid=0
            with self.assertRaisesRegex(ValueError,'Systemkonten'):
                core.validate({'operation':'user_edit','name':'alice'})

    def test_password_only_passed_on_stdin(self):
        plan={'operation':'user_create','name':'alice','shell':'/bin/bash','groups':[],'password':'test-password-12345'}
        with patch.object(core,'command',return_value='') as command:
            core.apply_plan(plan)
        calls=command.call_args_list
        self.assertNotIn(plan['password'],repr([c.args for c in calls]))
        self.assertEqual(calls[-1].args[0],['chpasswd'])
        self.assertEqual(calls[-1].kwargs['input_text'],'alice:'+plan['password']+'\n')

    def test_system_permissions_paths_rejected(self):
        for path in ['/','/etc/passwd','/usr/bin','/run']:
            with patch.object(core,'local_path',return_value=Path(path)):
                with self.assertRaisesRegex(ValueError,'Datenpfade'):
                    core.validate({'operation':'permissions','path':path,'mode':'777'})

    def test_power_reservation_blocks_mutations_and_schedule(self):
        with patch.object(core,'POWER_UNTIL',0):
            self.assertTrue(core.read({'view':'power_reserve'})['reserved'])
            with self.assertRaises(ValueError):core.enqueue({'operation':'group_create','name':'photos'})
            self.assertFalse(core.MUTEX.locked())
            with patch.object(core,'backup_configs') as backups:
                core.schedule_tick();backups.assert_not_called()
            core.read({'view':'power_release'})

    def test_busy_agent_rejects_another_change(self):
        core.MUTEX.acquire()
        try:
            with self.assertRaises(ValueError):core.enqueue({'operation':'group_create','name':'photos'})
        finally:core.MUTEX.release()

    def test_backup_archive_rejects_traversal_and_symlinks(self):
        cfg={'id':'b'*24}
        path=Path(self.tmp.name)/'bad.tar'
        for name,kind in [('files/../escape',tarfile.REGTYPE),('files/link',tarfile.SYMTYPE)]:
            with tarfile.open(path,'w') as archive:
                content=b'test'
                manifest=json.dumps({'files':{name[6:]:{'size':4,'sha256':hashlib.sha256(content).hexdigest()}}}).encode()
                member=tarfile.TarInfo('manifest.json');member.size=len(manifest);archive.addfile(member,io.BytesIO(manifest))
                member=tarfile.TarInfo(name);member.type=kind;member.size=4 if kind==tarfile.REGTYPE else 0;member.linkname='/etc/passwd';archive.addfile(member,io.BytesIO(content) if kind==tarfile.REGTYPE else None)
            with patch.object(core,'archive_file',return_value=path):
                with self.assertRaises(ValueError):core.verify_archive(cfg,path.name)
        self.assertFalse((Path(self.tmp.name)/'escape').exists())

    def test_archive_roundtrip_and_corruption_detection(self):
        path=Path(self.tmp.name)/'good.tar';content=b'hello world'
        def write(content,expected):
            with tarfile.open(path,'w') as archive:
                manifest=json.dumps({'files':{'docs/test.txt':{'size':len(content),'sha256':expected}}}).encode()
                member=tarfile.TarInfo('files/docs/test.txt');member.size=len(content);archive.addfile(member,io.BytesIO(content))
                member=tarfile.TarInfo('manifest.json');member.size=len(manifest);archive.addfile(member,io.BytesIO(manifest))
        write(content,hashlib.sha256(content).hexdigest())
        target=Path(self.tmp.name)/'restore';target.mkdir()
        with patch.object(core,'archive_file',return_value=path):
            result=core.verify_archive({},path.name,target)
            self.assertTrue(result['verified']);self.assertEqual(result['files'],1)
            self.assertEqual((target/'docs/test.txt').read_bytes(),content)
            with self.assertRaises(FileExistsError):core.verify_archive({},path.name,target)
            write(content,'0'*64)
            with self.assertRaisesRegex(ValueError,'Prüfsumme'):core.verify_archive({},path.name)

    def test_missing_archive_member_fails(self):
        path=Path(self.tmp.name)/'missing.tar'
        with tarfile.open(path,'w') as archive:
            payload=json.dumps({'files':{'missing':{'size':0,'sha256':'0'*64}}}).encode()
            member=tarfile.TarInfo('manifest.json');member.size=len(payload);archive.addfile(member,io.BytesIO(payload))
        with patch.object(core,'archive_file',return_value=path):
            with self.assertRaisesRegex(ValueError,'fehlen'):core.verify_archive({},path.name)

    def test_scheduler_records_failure_without_retry_storm(self):
        ident='c'*24;cfg={'enabled':True,'hours':24,'next_run':0,'name':'photos'}
        with core.db() as db:db.execute('INSERT INTO backups VALUES (?,?,?)',(ident,json.dumps(cfg),0))
        with patch.object(core,'validate',side_effect=ValueError('Disk offline')):
            core.schedule_tick();core.schedule_tick()
        rows=core.audit_rows()['rows'];self.assertEqual(len(rows),1);self.assertEqual(rows[0]['status'],'error')

    @unittest.skipUnless(os.name=='posix','Linux fd-based backup traversal')
    def test_real_backup_then_verify_and_restore(self):
        source=Path(self.tmp.name)/'source';dest=Path(self.tmp.name)/'backups';source.mkdir();dest.mkdir()
        (source/'folder').mkdir();(source/'folder/photo.jpg').write_bytes(b'photo'*100)
        (source/'link').symlink_to('/etc/passwd')
        cfg={'id':'d'*24,'source':str(source),'destination':str(dest)}
        with patch.object(core,'backup_paths',return_value=(source,dest)):
            result=core.backup_run(cfg)
        self.assertEqual(result['files'],1);self.assertEqual(result['skipped'],1)
        with patch.object(core,'archive_file',return_value=dest/result['archive']):
            self.assertTrue(core.verify_archive(cfg,result['archive'])['verified'])


if __name__=='__main__':unittest.main()
