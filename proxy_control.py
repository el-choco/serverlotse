from pathlib import Path
import secrets
import admin_core as core
import sensors


def apply(plan):
    return caddy(plan) if plan['engine']=='caddy' else nginx(plan)


def caddy(plan):
    import advanced
    path=Path('/etc/caddy/Caddyfile');old=path.read_bytes()
    if advanced.file_hash(path)!=plan['existing_hash']:raise ValueError('Caddy-Konfiguration verändert. Neue Vorschau erforderlich.')
    backup=core.STATE/('Caddyfile-'+secrets.token_hex(8)+'.bak');backup.write_bytes(old)
    candidate=path.with_name('Caddyfile.serverlotse-'+secrets.token_hex(8))
    try:
        advanced.atomic_write(candidate,old+b'\n# ServerLotse\n'+sensors.proxy_template(plan)['caddy'].encode(),0o600)
        core.command(['caddy','validate','--config',str(candidate),'--adapter','caddyfile'],timeout=60)
        advanced.atomic_write(path,candidate.read_bytes())
        try:core.command(['systemctl','reload','caddy.service'],timeout=60)
        except Exception:
            advanced.atomic_write(path,old)
            raise ValueError('Reload fehlgeschlagen. Vorherige Caddy-Datei wiederhergestellt; aktiven Dienst prüfen.') from None
    finally:
        if candidate.exists():candidate.unlink()
    return {'domain':plan['domain'],'backup':str(backup),'note':'Caddy geprüft und neu geladen. Zertifikatausstellung erfolgt asynchron durch Caddy. DNS, Ports und Caddy-Logs prüfen.'}


def nginx_text(plan,tls=False):
    domain=plan['domain'];upstream=plan['upstream'].rstrip('/')
    acme='    location /.well-known/acme-challenge/ { root /var/lib/serverlotse/acme; }\n'
    head=f'server {{\n    listen 80;\n    server_name {domain};\n'+acme
    proxy=f'    location / {{\n        proxy_pass {upstream};\n        proxy_set_header Host $host;\n        proxy_set_header X-Real-IP $remote_addr;\n        proxy_set_header X-Forwarded-Proto $scheme;\n        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;\n    }}\n'
    if not tls:return '# ServerLotse\n'+head+proxy+'}\n'
    return ('# ServerLotse\n'+head+'    location / { return 301 https://$host$request_uri; }\n}\n'
            +f'server {{\n    listen 443 ssl;\n    server_name {domain};\n'
            +f'    ssl_certificate /etc/letsencrypt/live/{domain}/fullchain.pem;\n'
            +f'    ssl_certificate_key /etc/letsencrypt/live/{domain}/privkey.pem;\n'
            +'    ssl_protocols TLSv1.2 TLSv1.3;\n'+proxy+'}\n')


def nginx(plan):
    import advanced
    filename='serverlotse-'+plan['domain']+'.conf'
    available=Path('/etc/nginx/sites-available')/filename;enabled=Path('/etc/nginx/sites-enabled')/filename
    if available.exists() or available.is_symlink() or enabled.exists() or enabled.is_symlink():raise ValueError('Zieldatei existiert bereits.')
    webroot=Path('/var/lib/serverlotse-acme');webroot.mkdir(mode=0o755,exist_ok=True);core.private_destination(webroot)
    created=False
    try:
        text=nginx_text(plan).replace('/var/lib/serverlotse/acme','/var/lib/serverlotse-acme')
        advanced.atomic_write(available,text.encode());created=True
        enabled.symlink_to(available)
        core.command(['nginx','-t']);core.command(['systemctl','reload','nginx.service'],timeout=60)
        core.command(['certbot','certonly','--webroot','-w',str(webroot),'-d',plan['domain'],'--cert-name',plan['domain'],
                      '--non-interactive','--agree-tos','--email',plan['email'],'--server','https://acme-v02.api.letsencrypt.org/directory'],timeout=600)
        advanced.atomic_write(available,nginx_text(plan,True).replace('/var/lib/serverlotse/acme','/var/lib/serverlotse-acme').encode())
        core.command(['nginx','-t']);core.command(['systemctl','reload','nginx.service'],timeout=60)
        renewal=Path('/etc/letsencrypt/renewal-hooks/deploy');renewal.mkdir(parents=True,mode=0o755,exist_ok=True)
        hook=renewal/'serverlotse-nginx'
        if hook.exists() and not hook.read_text().startswith('#!/bin/sh\n# ServerLotse'):raise ValueError('Zertifikat aktiv, aber fremder Renewal-Hook wird nicht überschrieben.')
        advanced.atomic_write(hook,b'#!/bin/sh\n# ServerLotse\nnginx -t && systemctl reload nginx.service\n',0o755)
        core.command(['systemctl','enable','--now','certbot.timer'])
    except Exception as exc:
        if created:
            if enabled.is_symlink() and enabled.resolve()==available:enabled.unlink()
            if available.is_file() and available.read_text().startswith('# ServerLotse'):available.unlink()
            try:core.command(['nginx','-t']);core.command(['systemctl','reload','nginx.service'],timeout=60)
            except Exception:pass
        raise ValueError('Proxy-Einrichtung fehlgeschlagen; eigene Nginx-Dateien zurückgenommen. Eventuell ausgestellte Zertifikate bleiben erhalten. '+str(exc)) from None
    return {'domain':plan['domain'],'config':str(available),'note':'Nginx-Konfiguration und öffentliches Zertifikat eingerichtet. Certbot-Timer und Renewal-Hook aktiviert. Erreichbarkeit von außen prüfen.'}
