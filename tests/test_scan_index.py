"""Large scans use temporary SQLite data, never real server data."""
import json
import os
from pathlib import Path
import stat
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch
import server
import toolkit
from scan_index import FileIndex


class ScanIndexTests(unittest.TestCase):
    def setUp(self):self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name)
    def tearDown(self):self.tmp.cleanup()

    def test_index_roundtrip_large_inodes_and_cleanup(self):
        index=FileIndex();folder=Path(index.temporary.name)
        try:
            info=SimpleNamespace(st_dev=2,st_ino=2**64-1,st_size=3,st_blocks=8)
            index.add('a.txt',info);index.add('hardlink.txt',info);index.finish()
            self.assertEqual(len(index),2);self.assertEqual(len(list(index.items(unique=True))),1)
            self.assertEqual(list(index.items())[0][1],(3,8,2,2**64-1))
            self.assertEqual(index.types(),[{'name':'.txt','bytes':6,'count':2}])
        finally:index.close()
        self.assertFalse(folder.exists())

    def test_more_than_250000_entries_without_in_memory_dictionary(self):
        source=self.root/'source';source.mkdir();device=source.stat().st_dev;old_stat=os.stat;old_scan=os.scandir;count=250005
        def info(number):return SimpleNamespace(st_mode=stat.S_IFREG|0o600,st_dev=device,st_ino=number+1,st_size=number,st_blocks=1)
        class Entry:
            def __init__(self,number):self.number=number;self.path=str(source/('f'+str(number)+'.txt'))
            def stat(self,**kwargs):return info(self.number)
        class Listing:
            def __enter__(self):return (Entry(n) for n in range(count))
            def __exit__(self,*args):return False
        def fake_scan(path):return Listing() if str(path)==str(source) else old_scan(path)
        def fake_stat(path,*args,**kwargs):
            text=str(path)
            if text.startswith(str(source)+os.sep+'f'):return info(int(Path(text).stem[1:]))
            return old_stat(path,*args,**kwargs)
        with patch.object(os,'scandir',new=fake_scan),patch.object(os,'stat',new=fake_stat):
            index,errors,skipped=server.inventory(source)
        try:
            self.assertNotIsInstance(index,dict);self.assertEqual(len(index),count);self.assertEqual((errors,skipped),(0,0))
            self.assertEqual(index.types()[0]['count'],count)
            with patch.object(server,'resolve_path',return_value=source),patch.object(server,'inventory',return_value=(index,0,0)):
                result=toolkit.files_tool(server,{'action':'largest','view':'host','path':'/'})
            self.assertEqual(len(result['rows']),200);self.assertEqual(result['rows'][0]['bytes'],count-1)
        finally:index.close()

    def test_duplicate_grouping_is_disk_backed_and_hardlinks_count_once(self):
        index=FileIndex()
        try:
            for n,content,ino in [('a','abc',1),('b','abc',2),('alias','abc',1),('different','xyz',3)]:
                (self.root/n).write_text(content);index.add(n,SimpleNamespace(st_dev=1,st_ino=ino,st_size=3,st_blocks=1))
            index.finish();rows,errors=index.duplicates(self.root,server.digest,lambda *args:None)
            self.assertEqual(errors,0);self.assertEqual(len(rows),1);self.assertEqual(rows[0]['count'],2);self.assertEqual(rows[0]['bytes'],3)
        finally:index.close()

    def test_failed_scan_cleans_its_private_index(self):
        actual=FileIndex();folder=Path(actual.temporary.name)
        old=os.scandir
        def fail_source(path):
            if str(path)==str(self.root):raise ValueError('fixture')
            return old(path)
        with patch.object(server,'FileIndex',return_value=actual),patch.object(os,'scandir',new=fail_source):
            with self.assertRaises(ValueError):server.inventory(self.root)
        self.assertFalse(folder.exists())

    def test_low_cache_space_is_an_explicit_error(self):
        index=FileIndex()
        try:
            with patch('scan_index.shutil.disk_usage',return_value=SimpleNamespace(free=0)):
                with self.assertRaisesRegex(ValueError,'Scanindex'):index.finish()
        finally:index.close()

    def test_main_compose_keeps_readonly_host_and_only_read_search_capability(self):
        # The real Compose parser is additionally checked during release validation.
        text=(Path(__file__).parents[1]/'compose.yaml').read_text(encoding='utf-8')
        main=text.split('\n  serverlotse:\n',1)[1].split('\n  docker-reader:',1)[0]
        self.assertIn('user: "0:0"',main);self.assertIn('- DAC_READ_SEARCH',main)
        self.assertNotIn('privileged: true',main);self.assertIn('cap_drop:',main)
        self.assertGreaterEqual(main.count('read_only: true'),4)
        self.assertIn('scan-cache:/var/cache/serverlotse',main)
