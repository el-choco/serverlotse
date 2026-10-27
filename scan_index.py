"""Disposable disk-backed metadata index for large read-only scans."""
import os
from pathlib import Path
import shutil
import sqlite3
import tempfile
import weakref


def cleanup(connection, temporary):
    try:connection.close()
    finally:temporary.cleanup()


class FileIndex:
    def __init__(self):
        base=os.getenv('SCAN_CACHE_DIR') or None
        if base:Path(base).mkdir(mode=0o700,parents=True,exist_ok=True)
        self.temporary=tempfile.TemporaryDirectory(prefix='scan-',dir=base)
        self.connection=sqlite3.connect(str(Path(self.temporary.name)/'index.sqlite'),check_same_thread=False)
        self.finalizer=weakref.finalize(self,cleanup,self.connection,self.temporary)
        db=self.connection
        db.executescript('''PRAGMA journal_mode=OFF; PRAGMA cache_size=-4096; PRAGMA temp_store=FILE;
            CREATE TABLE files(name TEXT PRIMARY KEY,size INTEGER,blocks INTEGER,dev TEXT,ino TEXT,ext TEXT,first_inode INTEGER);
            CREATE TABLE inodes(dev TEXT,ino TEXT,PRIMARY KEY(dev,ino)) WITHOUT ROWID;
            CREATE TABLE pending(id INTEGER PRIMARY KEY,path TEXT);
        ''')
        self.count=0

    def close(self):self.finalizer()
    def __len__(self):return self.count
    def __bool__(self):return bool(self.count)

    def check_space(self,indexing=False):
        reserve=64*1024**2
        if indexing:reserve+=2*(Path(self.temporary.name)/'index.sqlite').stat().st_size
        if shutil.disk_usage(self.temporary.name).free<reserve:
            raise ValueError('Nicht genug freier Platz für den temporären Scanindex. Index wird entfernt; Quelldateien bleiben unverändert.')

    def add(self,name,info):
        dev,ino=str(info.st_dev),str(info.st_ino)
        first=self.connection.execute('INSERT OR IGNORE INTO inodes VALUES(?,?)',(dev,ino)).rowcount
        self.connection.execute('INSERT INTO files VALUES(?,?,?,?,?,?,?)',
            (name,info.st_size,getattr(info,'st_blocks',None),dev,ino,Path(name).suffix.lower() or 'Ohne Endung',first))
        self.count+=1
        if self.count%5000==0:
            self.connection.commit()
            self.check_space()

    def finish(self):
        self.connection.commit()
        self.check_space(indexing=True)
        self.connection.execute('CREATE INDEX file_size ON files(size,first_inode)')

    def items(self,unique=False):
        query='SELECT name,size,blocks,dev,ino FROM files'+(' WHERE first_inode=1' if unique else '')
        for name,size,blocks,dev,ino in self.connection.execute(query):yield name,(size,blocks,int(dev),int(ino))

    def values(self):
        for _,value in self.items():yield value

    def types(self):
        return [{'name':name,'bytes':size,'count':count} for name,size,count in self.connection.execute(
            'SELECT ext,SUM(size),COUNT(*) FROM files GROUP BY ext ORDER BY SUM(size) DESC LIMIT 1000')]

    def duplicates(self,root,digest,checkpoint):
        db=self.connection;errors=0;hashed=0
        db.execute('CREATE TABLE hashes(sha TEXT,name TEXT,size INTEGER)')
        sizes=db.execute('SELECT size FROM files WHERE first_inode=1 AND size>0 GROUP BY size HAVING COUNT(*)>1')
        for size, in sizes:
            for name, in db.execute('SELECT name FROM files WHERE first_inode=1 AND size=?',(size,)):
                checkpoint('Inhalt prüfen: '+name)
                try:sha=digest(root/name)
                except InterruptedError:raise
                except OSError:errors+=1;continue
                db.execute('INSERT INTO hashes VALUES(?,?,?)',(sha,name,size))
                hashed+=1
                if hashed%5000==0:self.check_space()
        db.commit();self.check_space(indexing=True);db.execute('CREATE INDEX hash_group ON hashes(sha,size)')
        rows=[]
        for sha,size,count in db.execute('SELECT sha,size,COUNT(*) FROM hashes GROUP BY sha,size HAVING COUNT(*)>1 ORDER BY size*(COUNT(*)-1) DESC LIMIT 200'):
            names=[row[0] for row in db.execute('SELECT name FROM hashes WHERE sha=? AND size=? ORDER BY name LIMIT 100',(sha,size))]
            rows.append({'name':'\n'.join(names),'count':count,'bytes':size*(count-1)})
        return rows,errors
