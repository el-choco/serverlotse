import base64
import json
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest.mock import Mock, patch
import admin_core as core
import terminal_host as terminal


class TerminalTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.state=patch.object(core,'STATE',Path(self.tmp.name));self.state.start();core.initialize()
        self.platform=patch.object(terminal.sys,'platform','linux');self.platform.start()
        self.root=patch.object(terminal.os,'geteuid',return_value=0,create=True);self.root.start()
        terminal.SESSIONS.clear();terminal.PREVIEWS.clear()
        self.owner='a'*64
        self.session=Mock(owner=self.owner,ident='session',born=time.monotonic(),active=time.monotonic(),seen=time.monotonic(),closed=False,
                          lock=threading.RLock(),buffer=bytearray(b'\x1b[31mhello'),offset=0,master=42)

    def tearDown(self):
        terminal.SESSIONS.clear();terminal.PREVIEWS.clear()
        self.root.stop();self.platform.stop();self.state.stop();self.tmp.cleanup()

    def request(self,action,**data):return terminal.request({'owner':self.owner,'action':action,**data})

    def test_open_requires_bound_single_use_confirmation(self):
        with patch.object(terminal,'Session',return_value=self.session) as session:
            nonce=self.request('prepare')['nonce']
            with self.assertRaises(ValueError):self.request('start',nonce=nonce,confirmation='wrong')
            session.assert_not_called()
            nonce=self.request('prepare')['nonce']
            with self.assertRaises(ValueError):terminal.request({'owner':'b'*64,'action':'start','nonce':nonce,'confirmation':'ROOT'})
            nonce=self.request('prepare')['nonce']
            self.assertEqual(self.request('start',nonce=nonce,confirmation='ROOT')['id'],'session')
            with self.assertRaises(ValueError):self.request('start',nonce=nonce,confirmation='ROOT')
            self.assertEqual(session.call_count,1)
            rows=core.audit_rows()
            self.assertNotIn('hello',json.dumps(rows));self.assertIn('terminal',json.dumps(rows))

    def test_expired_nonce_cannot_open(self):
        nonce=self.request('prepare')['nonce']
        with patch.object(terminal.time,'monotonic',return_value=time.monotonic()+70),patch.object(terminal,'Session') as session:
            with self.assertRaises(ValueError):self.request('start',nonce=nonce,confirmation='ROOT')
            session.assert_not_called()

    def test_owner_cannot_read_another_browser(self):
        terminal.SESSIONS['session']=self.session
        with self.assertRaises(ValueError):terminal.request({'owner':'b'*64,'action':'poll','id':'session'})
        result=self.request('poll',id='session',cursor=0)
        self.assertEqual(base64.b64decode(result['data']),b'\x1b[31mhello')
        self.assertEqual(result['cursor'],len(self.session.buffer))

    def test_output_gap_and_invalid_future_cursor(self):
        self.session.offset=100;terminal.SESSIONS['session']=self.session
        result=self.request('poll',id='session',cursor=0)
        self.assertTrue(result['lost'])
        with self.assertRaises(ValueError):self.request('poll',id='session',cursor=9999)

    def test_input_is_literal_bounded_and_partial_write_acknowledged(self):
        terminal.SESSIONS['session']=self.session
        raw=b'printf test\r\x03\x1b[A'
        with patch.object(terminal.os,'write',return_value=3) as write:
            result=self.request('input',id='session',data=base64.b64encode(raw).decode())
            self.assertEqual(result['written'],3);write.assert_called_once_with(42,raw)
            with self.assertRaises(ValueError):self.request('input',id='session',data=base64.b64encode(b'x'*4097).decode())
            with self.assertRaises(ValueError):self.request('input',id='session',data='***')

    def test_resize_and_close(self):
        terminal.SESSIONS['session']=self.session
        self.request('resize',id='session',cols=120,rows=40);self.session.resize.assert_called_once_with(120,40)
        with self.assertRaises(ValueError):self.request('resize',id='session',cols=10000,rows=40)
        self.request('close',id='session');self.session.close.assert_called_once();self.assertFalse(terminal.SESSIONS)

    def test_disconnection_and_idle_reap(self):
        terminal.SESSIONS['session']=self.session
        self.session.seen=time.monotonic()-61
        terminal.reap();self.session.close.assert_called_once();self.assertFalse(terminal.SESSIONS)

    def test_poll_does_not_extend_input_idle_deadline(self):
        terminal.SESSIONS['session']=self.session
        old=self.session.active
        self.request('poll',id='session');self.assertEqual(self.session.active,old)
        self.session.active=time.monotonic()-901
        terminal.reap();self.assertFalse(terminal.SESSIONS)
