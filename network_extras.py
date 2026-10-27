import ipaddress
import json
import re
import socket
import threading
import time
from urllib.parse import urlencode,quote
from urllib.request import Request,build_opener
import xml.etree.ElementTree as ET
import admin_core as core
import advanced
import docker_tools

OPS={'lab_ddns_save','lab_ddns_update','lab_domain_proxy','lab_inode_watch'}
LOCK=threading.Lock()


def request(url,method='GET',headers=None,data=None,json_output=True):
    try:
        payload=json.dumps(data).encode() if data is not None else None
        with build_opener(advanced.NoRedirect).open(Request(url,data=payload,method=method,headers={'Content-Type':'application/json',**(headers or {})}),timeout=12) as response:
            raw=response.read(131073)
            if len(raw)>131072:raise ValueError('Provider-Antwort zu groß.')
            return json.loads(raw) if json_output and raw else (raw.decode() if raw else None)
    except Exception:raise ValueError('DDNS-Anfrage fehlgeschlagen. Anbieter, Berechtigungen und Verbindung prüfen. Zugangsdaten werden nicht protokolliert.') from None


def domain(value):
    if not isinstance(value,str) or len(value)>253 or not re.fullmatch(r'(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z]{2,63}',value.lower()):raise ValueError('Vollständigen Domainnamen angeben, ohne Protokoll oder Pfad.')
    return value.lower()


def cfg():return advanced.state('ddns_config') or {'enabled':False,'provider':'cloudflare','record_type':'A','domain':'','zone':'','record_id':'','zone_id':'','interval':15,'consent':False}


def normalize(data):
    old=cfg();result={**old,'enabled':data.get('enabled') is True,'consent':data.get('consent') is True}
    for key in ['provider','domain','zone','zone_id','record_id','record_type']:
        value=data.get(key,old.get(key,''))
        if not isinstance(value,str):raise ValueError('Ungültige DDNS-Einstellung.')
        result[key]=value.strip()
    result['interval']=int(data.get('interval',old['interval']))
    if not 5<=result['interval']<=1440:raise ValueError('Intervall muss 5 bis 1440 Minuten betragen.')
    for key in ['ddns_token','ddns_password']:
        if data.get('clear_credentials') is True:result.pop(key,None)
        value=data.get(key)
        if value:
            if not isinstance(value,str) or len(value)>1024 or any(ord(c)<32 for c in value):raise ValueError('Ungültige DDNS-Zugangsdaten.')
            result[key]=value
    result['clear_credentials']=data.get('clear_credentials') is True
    if result['provider'] not in {'cloudflare','namecheap','godaddy'}:raise ValueError('Unbekannter DDNS-Anbieter.')
    if result['record_type'] not in {'A','AAAA'}:raise ValueError('A oder AAAA auswählen.')
    if not result['enabled']:return result
    result['domain']=domain(result['domain'])
    if result['provider']=='cloudflare':
        if not all(re.fullmatch('[a-fA-F0-9]{32}',result[k]) for k in ['zone_id','record_id']):raise ValueError('Cloudflare-Zonen-ID und Record-ID müssen je 32 Hex-Zeichen haben.')
    else:
        result['zone']=domain(result['zone'])
        if result['domain']!=result['zone'] and not result['domain'].endswith('.'+result['zone']):raise ValueError('Domain gehört nicht zur angegebenen DNS-Zone.')
    if result['provider']=='namecheap' and result['record_type']!='A':raise ValueError('Namecheap Dynamic DNS unterstützt nur IPv4/A.')
    if result['enabled']:
        if not result['consent']:raise ValueError('Übermittlung an IP-Ermittler und DNS-Anbieter zuerst bestätigen.')
        key='ddns_password' if result['provider']=='namecheap' else 'ddns_token'
        if not result.get(key):raise ValueError('DDNS-Zugangsdaten fehlen.')
    return result


def public_ip(kind):
    raw=request('https://api.ipify.org' if kind=='A' else 'https://api6.ipify.org',json_output=False)
    value=ipaddress.ip_address(raw.strip())
    if value.version!=(4 if kind=='A' else 6) or not value.is_global:raise ValueError('Keine öffentliche IP-Adresse ermittelt.')
    return str(value)


def update(cfg):
    address=public_ip(cfg['record_type']);provider=cfg['provider'];name=cfg['domain'];kind=cfg['record_type']
    if provider=='cloudflare':
        url='https://api.cloudflare.com/client/v4/zones/'+cfg['zone_id']+'/dns_records/'+cfg['record_id']
        headers={'Authorization':'Bearer '+cfg['ddns_token']};row=request(url,headers=headers)
        if not row.get('success') or row.get('result',{}).get('name')!=name or row['result'].get('type')!=kind:raise ValueError('Cloudflare-Record passt nicht zur ausgewählten Domain und zum Record-Typ.')
        previous=row['result']['content']
        if previous!=address:
            answer=request(url,'PATCH',headers,{'content':address})
            if not answer.get('success'):raise ValueError('Cloudflare hat die Änderung abgelehnt.')
    elif provider=='godaddy':
        host='@' if name==cfg['zone'] else name[:-(len(cfg['zone'])+1)]
        url='https://api.godaddy.com/v1/domains/'+quote(cfg['zone'],safe='')+'/records/'+kind+'/'+quote(host,safe='')
        headers={'Authorization':'Bearer '+cfg['ddns_token']};rows=request(url,headers=headers)
        if not isinstance(rows,list) or len(rows)!=1 or rows[0].get('type')!=kind or rows[0].get('name')!=host:raise ValueError('Genau einen vorhandenen DNS-Record auswählen; Mehrfach-Records werden nicht überschrieben.')
        previous=rows[0]['data']
        if previous!=address:request(url,'PUT',headers,[{'data':address,'ttl':rows[0].get('ttl',600)}])
    else:
        host='@' if name==cfg['zone'] else name[:-(len(cfg['zone'])+1)]
        url='https://dynamicdns.park-your-domain.com/update?'+urlencode({'host':host,'domain':cfg['zone'],'password':cfg['ddns_password'],'ip':address})
        raw=request(url,json_output=False)
        try:
            root=ET.fromstring(raw)
            if root.findtext('ErrCount')!='0':raise ValueError()
        except Exception:raise ValueError('Namecheap hat die Änderung nicht bestätigt.') from None
        previous=None
    result={'time':time.time(),'domain':name,'address':address,'changed':previous!=address,'status':'ok'}
    advanced.state('ddns_last',result);return result


def proxy_candidates():
    rows=[]
    for container in docker_tools.inventory():
        if docker_tools.protected(container):continue
        for port in container.get('Ports',[]):
            if port.get('Type')!='tcp' or not port.get('PublicPort'):continue
            ip=port.get('IP','0.0.0.0')
            if ip in {'0.0.0.0','::'}:ip='127.0.0.1' if ip=='0.0.0.0' else '[::1]'
            elif ':' in ip:ip='['+ip+']'
            rows.append({'container':container['Id'],'name':','.join(container.get('Names',[])).lstrip('/'),'upstream':'http://'+ip+':'+str(port['PublicPort'])})
    return rows[:200]


def dns_answers(name):
    output=core.command(['getent','ahosts',domain(name)],timeout=10,allowed=(0,2))
    values=[]
    for line in output.splitlines():
        try:values.append(str(ipaddress.ip_address(line.split()[0])))
        except (ValueError,IndexError):continue
    return sorted(set(values))


def validate(data):
    op=data['operation'];p={'operation':op}
    if op=='lab_ddns_save':
        before=docker_tools.fingerprint(cfg())
        if data.get('before_hash',before)!=before:raise ValueError('DDNS-Einstellungen verändert. Neue Vorschau erstellen.')
        return {**p,'config':normalize(data.get('config',{})),'before_hash':before}
    if op=='lab_ddns_update':
        current=normalize({**cfg(),'enabled':True})
        if not current['consent']:raise ValueError('DDNS-Datenübermittlung zuerst freigeben.')
        if not current.get('ddns_password' if current['provider']=='namecheap' else 'ddns_token'):raise ValueError('DDNS-Zugangsdaten fehlen.')
        return {**p,'config_hash':docker_tools.fingerprint(current),'domain':current['domain']}
    if op=='lab_inode_watch':
        threshold=int(data.get('threshold',90))
        if not 50<=threshold<=99:raise ValueError('Inode-Grenze muss 50 bis 99 Prozent betragen.')
        return {**p,'enabled':data.get('enabled') is True,'threshold':threshold}
    if op=='lab_domain_proxy':
        target=next((r for r in proxy_candidates() if r['container']==data.get('container') and r['upstream']==data.get('upstream')),None)
        if not target:raise ValueError('Veröffentlichten Container-Port auswählen.')
        name=domain(data.get('domain'));expected=str(ipaddress.ip_address(data.get('expected_ip','')))
        answers=dns_answers(name)
        if expected not in answers and data.get('dns_override') is not True:raise ValueError('DNS zeigt nicht auf die angegebene öffentliche Server-IP. DNS korrigieren oder CDN-Abweichung ausdrücklich bestätigen.')
        plan=advanced.validate({'operation':'proxy_apply','engine':data.get('engine'),'domain':name,'upstream':target['upstream'],
            'email':data.get('email'),'acme_consent':data.get('acme_consent') is True})
        return {**p,'container':target['container'],'upstream':target['upstream'],'domain':name,'expected_ip':expected,'dns_override':data.get('dns_override') is True,
            'engine':data.get('engine'),'email':data.get('email'),'acme_consent':True,'proxy_plan':plan,'dns':answers}
    raise ValueError('Unbekanntes Netzwerk-Werkzeug.')


def apply(p):
    if p['operation']=='lab_ddns_save':advanced.state('ddns_config',{k:v for k,v in p['config'].items() if k!='clear_credentials'});return {'note':'DDNS gespeichert. Nur bei aktivem Zeitplan oder manueller Bestätigung werden DNS-Einträge geändert.'}
    if p['operation']=='lab_ddns_update':
        with LOCK:return update(cfg())
    if p['operation']=='lab_inode_watch':advanced.state('inode_watch',{'enabled':p['enabled'],'threshold':p['threshold']});return {'note':'Inode-Wächter gespeichert. Verwendet das bestehende Webhook-Ziel.'}
    if p['operation']=='lab_domain_proxy':
        import proxy_control
        return proxy_control.apply(p['proxy_plan'])
    raise ValueError('Unbekanntes Netzwerk-Werkzeug.')


def read(data):
    if data['view']=='lab_ddns':return {'config':advanced.public(cfg()),'last':advanced.state('ddns_last')}
    if data['view']=='lab_domain_targets':return {'rows':proxy_candidates()}
    if data['view']=='lab_dns_check':return {'addresses':dns_answers(data.get('domain'))}
    if data['view']=='lab_inode_watch':return advanced.state('inode_watch') or {'enabled':False,'threshold':90}
    if data['view']=='lab_firewall_map':
        import sensors
        return {'firewall':sensors.firewall(core),'ports':core.command(['ss','-lntup']), 'containers':proxy_candidates(),
            'note':'Regelübersicht und Listener, keine vollständige Paketsimulation. Docker-Ports können UFW umgehen; leere Regelanzeige beweist keine Sperre.'}
    raise ValueError('Unbekannte Netzwerk-Ansicht.')


def loop():
    while True:
        time.sleep(60)
        try:tick()
        except Exception:
            continue


def tick():
    current=cfg();now=time.time();last=advanced.state('ddns_attempt') or 0
    if current.get('enabled') and current.get('consent') and now-last>=current.get('interval',15)*60 and core.POWER_UNTIL<=now and core.MUTEX.acquire(False):
        try:
            with LOCK:
                advanced.state('ddns_attempt',now)
                result=update(normalize(current))
                if result['changed']:advanced.log_event('lab_ddns_update',result)
        except Exception:
            advanced.state('ddns_last',{'time':now,'status':'error','note':'DDNS-Anfrage fehlgeschlagen. Anbieter, Zugang und Internetverbindung prüfen.'})
        finally:core.MUTEX.release()
    watch=advanced.state('inode_watch') or {}
    if watch.get('enabled') and now-(advanced.state('inode_alert') or 0)>=3600:
        try:
            import expert_tools
            high=[r for r in expert_tools.inode_radar()['rows'] if r['percent'] is not None and r['percent']>=watch.get('threshold',90)]
            if high:
                advanced.notify('Inode-Warnung: '+', '.join(r['path']+' '+str(r['percent'])+' %' for r in high));advanced.state('inode_alert',now)
        except Exception:pass
