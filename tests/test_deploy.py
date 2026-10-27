import copy
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock,patch
import deploy_host as deploy


class DeploymentTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name)
        source=Path(__file__).resolve().parent.parent
        self.payload={'token':'a-local-test-token-not-a-real-key','files':{name:(source/name).read_text(encoding='utf-8') for name in deploy.FILES}}
        self.runner=Mock()
        self.reader=Mock(return_value={'version':'0.7.5','terminal':True})
        self.safe=patch.object(deploy,'safe_path',side_effect=lambda root,relative:root/relative);self.safe.start()
        self.mode=patch.object(deploy.os,'fchmod',create=True);self.mode.start()

    def tearDown(self):self.mode.stop();self.safe.stop();self.tmp.cleanup()

    def install(self):deploy.install(self.payload,self.root,self.runner,self.reader)

    def test_fresh_install_writes_fixed_files_then_starts_services(self):
        self.install()
        self.assertEqual((self.root/'etc/serverlotse/admin.token').read_text(),self.payload['token']+'\n')
        for name in deploy.PYTHON_FILES:
            self.assertEqual((self.root/'usr/local/lib/serverlotse'/name).read_text(encoding='utf-8'),self.payload['files'][name])
        self.assertEqual(self.runner.call_args_list[-1].args[0],['systemctl','restart','serverlotse-admin.service'])
        self.assertNotIn(self.payload['token'],str(self.runner.call_args_list))

    def test_identical_install_does_not_restart_active_sessions(self):
        self.install();self.runner.reset_mock()
        sock=self.root/'run/serverlotse-admin/agent.sock';sock.parent.mkdir(parents=True);sock.touch()
        self.reader.return_value={'version':'0.7.5','terminal':True,'busy':True,'terminal_sessions':1}
        self.install()
        self.runner.assert_called_once_with(['systemctl','enable','--now','serverlotse-view.service'])

    def test_changed_payload_waits_for_busy_helper(self):
        token=self.root/'etc/serverlotse/admin.token';token.parent.mkdir(parents=True);token.write_text(self.payload['token'])
        sock=self.root/'run/serverlotse-admin/agent.sock';sock.parent.mkdir(parents=True);sock.touch()
        self.reader.return_value={'busy':True,'terminal_sessions':0}
        with self.assertRaises(ValueError):self.install()
        self.runner.assert_not_called();self.assertFalse((self.root/'usr').exists())

    def test_invalid_file_list_or_token_is_rejected_before_writes(self):
        for field,value in [('token','bad'),('files',{'../../unexpected':'text'})]:
            payload=copy.deepcopy(self.payload);payload[field]=value
            with self.assertRaises(ValueError):deploy.install(payload,self.root,self.runner,self.reader)
        self.assertFalse((self.root/'etc').exists());self.runner.assert_not_called()

    def test_bad_line_endings_and_syntax_are_rejected(self):
        for text in ['print(\r\n','bad syntax ???']:
            payload=copy.deepcopy(self.payload);payload['files']['admin_agent.py']=text
            with self.assertRaises((ValueError,SyntaxError)):deploy.validate(payload)

    def test_launch_uses_fixed_nsenter_and_stdin_payload_not_shell(self):
        source=Path(deploy.__file__).read_text(encoding='utf-8')
        def read(path,**kwargs):
            return self.payload['files'][path.name] if path.parent==Path('/payload') else source
        with patch.object(Path,'read_text',read),patch.dict(os.environ,{'SERVERLOTSE_TOKEN':self.payload['token']}),patch.object(deploy.subprocess,'run') as run:
            deploy.launch()
            args=run.call_args.args[0]
            self.assertEqual(args[:3],['nsenter','--target','1'])
            self.assertIn('--root',args);self.assertIn('--pid',args)
            self.assertNotIn(self.payload['token'],str(args))
            self.assertEqual(json.loads(run.call_args.kwargs['input']),self.payload)
            self.assertFalse(run.call_args.kwargs.get('shell',False))
