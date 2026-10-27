"""Clearly labelled fixtures. No host action is available in demo mode."""
import time


def safe_preview(value):
    if isinstance(value,list):return [safe_preview(item) for item in value]
    if not isinstance(value,dict):return value
    result={}
    for key,item in value.items():
        if key=='env_updates' and isinstance(item,dict):result[key]={name:('[entfernen]' if val is None else '••••••') for name,val in item.items()}
        elif key in {'password','webhook_url','telegram_token','telegram_chat','access_key','secret_key','ddns_token','ddns_password','config_text','encoded_data','compose_document','backup'}:
            if item:result[key+'_configured']=True
        else:result[key]=safe_preview(item)
    return result


def read(data):
    view = data.get('view')
    if isinstance(view,str) and view.startswith('lab_'):
        import workbench_demo
        return workbench_demo.read(data)
    if isinstance(view,str) and view.startswith('advanced_'):
        import advanced_demo
        return advanced_demo.read(data)
    if isinstance(view,str) and view.startswith('sensor_'):
        import sensors_demo
        return sensors_demo.read(data)
    if view == 'status': return {'enabled': True, 'demo': True, 'hostname': 'demo-server', 'busy': False, 'tools': {}}
    if view == 'health': return {'hostname':'demo-server','uptime':86400,'cpus':4,'load':[.4,.6,.3], 'memory':{'MemTotal':8*1073741824,'MemAvailable':5*1073741824},'reboot_required':False,'findings':[{'code':'space','level':'warning','meaning':'Datenträger fast voll','path':'/mnt/backup','next':'Speicher untersuchen und große Ordner vergleichen.'}],'journal':'DEMO: No real journal data.'}
    if view == 'services': return {'rows':[{'name':'example.service','active':'active','sub':'running','autostart':'enabled'},{'name':'example-backup.service','active':'failed','sub':'failed','autostart':'disabled'}]}
    if view == 'service': return {'properties':'DEMO: ActiveState=active','journal':'DEMO: Example service started.'}
    if view == 'updates': return {'simulation':'DEMO: Inst example-package [1.0] (1.1)\nConf example-package (1.1)','note':'Beispieldaten – keine Verbindung zu deinem Server.'}
    if view == 'disks': return {'rows':[{'path':'/dev/sda','type':'disk','size':235000000000,'fstype':None,'label':None,'uuid':None,'mountpoints':[],'usage':[]},{'path':'/dev/sda1','type':'part','size':235000000000,'fstype':'ext4','label':'System','uuid':'demo-uuid-system','mountpoints':['/'],'usage':[{'percent':36,'free':138000000000}]},{'path':'/dev/sdb1','type':'part','size':2000000000000,'fstype':'ext4','label':'Daten','uuid':'demo-uuid-data','mountpoints':[],'usage':[]}],'mounts':[{'source':'/dev/sda1','target':'/','fstype':'ext4'}],'smart_available':True}
    if view == 'smart': return {'demo':True,'smart_status':{'passed':True},'temperature':{'current':32}}
    if view == 'containers': return {'rows':[{'ID':'a'*64,'Names':'example-web','Status':'Up 2 days'}], 'resources':[{'ID':'a'*64,'CPUPerc':'0.30%','MemUsage':'120MiB / 2GiB'}]}
    if view == 'network': return {'addresses':[{'ifname':'eth0','addr_info':[{'local':'192.0.2.10'}]}],'routes':[{'dst':'default','gateway':'192.0.2.1'}],'ports':'DEMO: tcp LISTEN 0.0.0.0:443','dns':'DEMO: nameserver 192.0.2.1'}
    if view == 'probe': return {'demo':True,'addresses':['192.0.2.10'],'reachable':True,'milliseconds':12}
    if view == 'users': return {'rows':[{'name':'root','uid':0,'gid':0,'home':'/root','shell':'/bin/bash','groups':['root'],'editable':False},{'name':'demo','uid':1000,'gid':1000,'home':'/home/demo','shell':'/bin/bash','groups':['demo'],'editable':True}], 'groups':[{'name':'demo','gid':1000},{'name':'media','gid':1001}]}
    if view == 'rights': return {'rows':[{'path':'/','mode':'755','rights':'drwxr-xr-x','owner':'root','group':'root'},{'path':data.get('path','/mnt'),'mode':'750','rights':'drwxr-x---','owner':'demo','group':'media'}],'acl':'DEMO: user::rwx\ngroup::r-x\nother::---','note':'Beispieldaten – keine Verbindung zu deinem Server.'}
    if view == 'backups': return {'rows':[{'id':'b'*24,'name':'Demo-Sicherung','source':'/mnt/daten','destination':'/mnt/backup','hours':24,'enabled':False,'next_run':time.time()+86400}]}
    if view == 'archives': return {'rows':[{'name':'serverlotse-'+'b'*24+'-20261025-120000-abcdef.tar','bytes':10000000,'modified':time.time()}]}
    if view == 'audit': return {'rows':[{'id':'c'*24,'created':time.time(),'operation':'backup_verify','parameters':'{"demo": true}', 'status':'done','result':'DEMO: no real action executed.'}]}
    if view == 'audit_detail': return {'id':'c'*24,'parameters':{'demo':True},'status':'done','result':'DEMO: no real action executed.'}
    raise ValueError('Unbekannte Verwaltungsansicht.')
