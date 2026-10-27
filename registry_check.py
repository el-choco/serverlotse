"""Passive public OCI/Docker manifest comparison. No pull, login or credential export."""
import hashlib
import json
import re
from urllib.error import HTTPError
from urllib.parse import urlencode,urlsplit,quote
from urllib.request import Request,build_opener,HTTPRedirectHandler
import docker_tools

ACCEPT='application/vnd.oci.image.index.v1+json, application/vnd.docker.distribution.manifest.list.v2+json, application/vnd.oci.image.manifest.v1+json, application/vnd.docker.distribution.manifest.v2+json'


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self,*args):return None


def reference(value):
    if not isinstance(value,str) or not re.fullmatch(r'[a-zA-Z0-9][a-zA-Z0-9._:/@-]{0,300}',value) or value.startswith('sha256:'):
        raise ValueError('Image hat keine prüfbare Registry-Referenz.')
    first,slash,tail=value.partition('/')
    if slash and ('.' in first or ':' in first or first=='localhost'):host=first;repo=tail
    else:host='registry-1.docker.io';repo=value if slash else 'library/'+value
    if host in {'docker.io','index.docker.io'}:host='registry-1.docker.io'
    if host.startswith(('localhost','127.')) or ':' in host:raise ValueError('Nur öffentliche HTTPS-Registries ohne Sonderport prüfen.')
    if '@' in repo:repo,ref=repo.split('@',1)
    elif ':' in repo:repo,ref=repo.rsplit(':',1)
    else:ref='latest'
    if not re.fullmatch(r'[a-z0-9]+(?:[._/-][a-z0-9]+)*',repo) or not re.fullmatch(r'[A-Za-z0-9_.:-]{1,150}',ref):
        raise ValueError('Ungültige Image-Referenz.')
    return host,repo,ref


def bounded(response,limit=5_000_000):
    raw=response.read(limit+1)
    if len(raw)>limit:raise ValueError('Registry-Antwort zu groß.')
    return raw


def fetch(host,repo,ref,token=None,opener=None):
    opener=opener or build_opener(NoRedirect)
    url='https://'+host+'/v2/'+repo+'/manifests/'+quote(ref,safe=':')
    headers={'Accept':ACCEPT}
    if token:headers['Authorization']='Bearer '+token
    try:
        with opener.open(Request(url,headers=headers),timeout=12) as response:raw=bounded(response)
    except HTTPError as error:
        code=error.code;challenge=error.headers.get('WWW-Authenticate','');error.close()
        if code!=401 or token:raise ValueError('Registry nicht öffentlich erreichbar, Zugriff begrenzt oder Anmeldung erforderlich.') from None
        if not challenge.lower().startswith('bearer '):raise ValueError('Private Registry: keine Zugangsdaten werden automatisch übertragen.')
        values=dict(re.findall(r'(\w+)="([^"]+)"',challenge));realm=urlsplit(values.get('realm',''))
        permitted={host,'auth.docker.io'} if host=='registry-1.docker.io' else {host}
        if realm.scheme!='https' or realm.hostname not in permitted or realm.username or realm.password or realm.port not in {None,443} or realm.query or realm.fragment:
            raise ValueError('Registry verweist auf einen nicht freigegebenen Anmeldedienst.')
        authurl=realm.geturl()+'?'+urlencode({'service':values.get('service',host),'scope':'repository:'+repo+':pull'})
        with opener.open(Request(authurl),timeout=12) as response:auth=json.loads(bounded(response,100000))
        access=auth.get('token') or auth.get('access_token')
        if not isinstance(access,str) or len(access)>20000:raise ValueError('Registry-Token fehlt.')
        return fetch(host,repo,ref,access,opener)
    except OSError:raise ValueError('Registry zurzeit nicht erreichbar.') from None
    if ref.startswith('sha256:') and 'sha256:'+hashlib.sha256(raw).hexdigest()!=ref:
        raise ValueError('Registry-Prüfsumme stimmt nicht.')
    return json.loads(raw),token


def check(info):
    host,repo,ref=reference(info['Config']['Image'])
    local=docker_tools.api('GET','/images/'+quote(info['Image'],safe='')+'/json')
    manifest,token=fetch(host,repo,ref)
    if 'manifests' in manifest:
        matches=[item for item in manifest['manifests'] if item.get('platform',{}).get('os')==local.get('Os')
                 and item.get('platform',{}).get('architecture')==local.get('Architecture')
                 and (not local.get('Variant') or item.get('platform',{}).get('variant')==local['Variant'])]
        if len(matches)!=1:raise ValueError('Image-Plattform nicht eindeutig in der Registry gefunden.')
        digest=matches[0].get('digest','')
        if not re.fullmatch(r'sha256:[a-f0-9]{64}',digest):raise ValueError('Unbekannter Manifest-Digest.')
        manifest,_=fetch(host,repo,digest,token)
    remote=manifest.get('config',{}).get('digest','')
    if not re.fullmatch(r'sha256:[a-f0-9]{64}',remote):raise ValueError('Registry liefert keinen vergleichbaren Image-Digest.')
    return {'available':remote!=local['Id'],'pinned':'@sha256:' in info['Config']['Image'],
            'image':info['Config']['Image'],'local':local['Id'],'remote':remote,
            'note':'Passiver Vergleich der passenden Plattform. Kein Image heruntergeladen oder Container aktualisiert. Private Registries werden nicht automatisch angemeldet.'}
