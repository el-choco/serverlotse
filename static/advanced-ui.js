/* User-approved administration. Installation never enables automation by itself. */
(() => {
  const definitions=[
    ['shell-advanced','Root-Konsole','System','Interaktives Terminal direkt auf deinem Linux-Host.'],
    ['clean-advanced','Docker aufräumen','Docker','Alte Images und Cache bereinigen oder ein unbenutztes Volume gezielt löschen.'],
    ['firewall-advanced','Firewall-Regeln','Sicherheit','Einfache UFW-Portfreigaben hinzufügen und entfernen.'],
    ['automation-advanced','Automatik und Meldungen','Automatik','Grenzwerte, Webhooks, Auto-Heiler und nächtliche Docker-Pflege konfigurieren.'],
    ['healing-advanced','Auto-Heiler-Status','Automatik','Wiederanlaufversuche und gesperrte Ziele nachvollziehen.'],
    ['updates-advanced','Update-Zeitplan','System','Sicherheitsupdates nachts installieren lassen, ohne automatische Reboots.'],
    ['bundle-advanced','Datenbank- und Remote-Backup','Backups','Komprimierte Dateisicherung mit optionalem SQL-Export und SFTP-/S3-Upload.'],
    ['remote-advanced','Remote-Profile','Backups','SFTP-Schlüsselzugang oder S3-Zugang für Sicherungsuploads einrichten.'],
    ['proxy-advanced','Proxy einrichten','Netzwerk','Native Caddy- oder Nginx-Konfiguration mit öffentlichem Zertifikat einrichten.']
  ];
  const help={
    'shell-advanced':'Vollwertiges Root-Terminal auf dem Host, ohne SSH-Key. Eine Bestätigung öffnet die Sitzung; danach werden Eingaben sofort ausgeführt. Unterstützt nano, htop und DietPi-Menüs. Sitzung schließen beendet die Shell. Befehle und Ausgabe werden nicht von ServerLotse protokolliert.',
    'clean-advanced':'Automatische Pflege entfernt keine Volumes, Container oder Netzwerke. Ein Volume ohne Containerreferenz kann trotzdem wichtige Dateien enthalten. Die einzelne Volume-Löschung ist endgültig und verlangt LOESCHEN. Images und Cache sind rekonstruierbar, spätere Builds können jedoch länger dauern.',
    'firewall-advanced':'UFW muss bereits aktiv sein. ServerLotse aktiviert keine Firewall über eine Fernverbindung. Schließen entfernt eine einfache allow-Regel und ist keine Garantie für eine vollständige Sperre. Andere Regeln, NAT und veröffentlichte Docker-Ports können weiter Zugriff erlauben. SSH- und Verwaltungsports sind geschützt.',
    'automation-advanced':'Der Hauptschalter aktiviert nur die gewählten Funktionen. CPU/RAM müssen den Grenzwert für die eingestellte Dauer überschreiten. Benachrichtigungen haben eine Sendepause. Auto-Heiler prüfen gewählte Ziele ungefähr jede Minute und starten erst nach zwei Fehlerprüfungen neu, maximal dreimal pro Stunde. Pausierte oder bewusst gestoppte Container werden nicht blind gestartet.',
    'healing-advanced':'Ein manueller Stopp in ServerLotse pausiert den Auto-Heiler für dieses Ziel. Erkennbare Docker-Stop-Ereignisse werden ebenfalls berücksichtigt. Eine Sperre bleibt bis zum Zurücksetzen bestehen. Nach drei Versuchen pro Stunde wartet der Auto-Heiler; externe Anwendungen kennt er nicht vollständig.',
    'updates-advanced':'Benötigt unattended-upgrades auf Debian, DietPi oder Ubuntu. Es werden Sicherheitsquellen gewählt und automatische Reboots abgeschaltet. Paketupdates können Dienste trotzdem neu starten. Die Uhrzeit gilt in der Zeitzone des Hosts. Vorhandene abweichende APT-Konfigurationen müssen geprüft werden.',
    'bundle-advanced':'Die Dateiablage wird wie bisher mit Inhaltsmanifest gesichert und als .tar.gz komprimiert. Optional kommt ein MySQL-/MariaDB-Export aus einem gewählten Container dazu. Das Passwort wird aus dessen vorhandener Passwort-Umgebungsvariable gelesen. Dateisicherung und SQL-Export sind kein gemeinsamer atomarer Snapshot. Remote-Uploads löschen keine Zieldateien.',
    'remote-advanced':'Profile werden getrennt unter /etc/serverlotse/remotes.conf gespeichert, nur für root lesbar. Bestehende rclone-Mounts und Syncs werden nicht verändert. SFTP benötigt einen vorhandenen privaten Schlüssel und bekannte Hostschlüssel; S3 benötigt Zugangsschlüssel. Profile werden nicht überschrieben. Erst ein Backup baut eine Verbindung auf.',
    'proxy-advanced':'Nur der native Proxy auf diesem Host wird konfiguriert. Nginx Proxy Manager wird nicht verändert. Domain und öffentliche Ports 80/443 müssen zu diesem Proxy zeigen. Caddy, beziehungsweise Nginx und Certbot, müssen schon installiert sein. Neue Domains werden an die Zertifizierungsstelle übermittelt und öffentlich protokolliert. Bestehende Domains werden nicht überschrieben.'
  };
  const nav=document.querySelector('nav'),pages=new Map(),pending=new Set();
  const read=data=>api('admin/read',data),change=data=>window.ServerLotseAdmin.preview(data);
  function button(text,callback,style='secondary'){const b=el('button',text,style);b.type='button';b.onclick=async()=>{b.disabled=true;try{await callback();}catch(error){message(error.message);}finally{b.disabled=false;}};return b;}
  function input(label,value='',type='text'){const wrap=el('label',label),node=el(type==='textarea'?'textarea':'input');if(type!=='textarea')node.type=type;else node.rows=4;node.setAttribute('aria-label',t(label));node.value=value;node.autocomplete=type==='password'?'new-password':'off';wrap.append(node);return {wrap,node};}
  function select(label,options,value){const wrap=el('label',label),node=el('select');node.setAttribute('aria-label',t(label));for(const [key,text]of options){const o=rawEl('option',text);o.value=key;node.append(o);}if(value!==undefined)node.value=value;wrap.append(node);return {wrap,node};}
  function check(label,value=false){const wrap=el('label',undefined,'admin-check'),node=el('input');node.type='checkbox';node.checked=value;wrap.append(node,el('span',label));return {wrap,node};}
  function form(items){const box=el('div',undefined,'panel'),fields=el('div',undefined,'fields');fields.append(...items.map(i=>i.wrap));box.append(fields);return box;}
  function pre(value){return rawEl('pre',typeof value==='string'?value:JSON.stringify(value,null,2));}
  function actions(...items){const node=el('div',undefined,'result-actions');node.append(...items);return node;}
  function group(name){let parent=[...nav.querySelectorAll('.nav-category')].find(n=>I18N.original(n.querySelector('summary').textContent)===I18N.original(name));if(!parent){parent=el('details',undefined,'nav-category');parent.dataset.pages='';parent.append(el('summary',name));nav.insertBefore(parent,nav.querySelector('[data-page="history"]'));}return parent;}
  for(const [id,name,category,description]of definitions){
    const section=el('section',undefined,'page advanced-page');section.id=id;section.hidden=true;section.append(el('span',category,'eyebrow'),el('h1',name),el('p',description));
    const helpBox=el('details',undefined,'admin-help');helpBox.append(el('summary','Was bedeutet das?'),el('p',help[id]));const status=el('p','Noch nicht geladen.','hint');status.setAttribute('role','status');const body=el('div');section.append(helpBox,status,body);document.querySelector('footer').before(section);pages.set(id,{section,status,body});
    const item=el('button',name);item.dataset.page=id;item.onclick=()=>open(id);const parent=group(category);parent.dataset.pages+=','+id;parent.append(item);
    let dashboard=[...$('overview').querySelectorAll('.dashboard-category')].find(n=>I18N.original(n.querySelector('summary').textContent)===I18N.original(category));if(!dashboard){dashboard=el('details',undefined,'dashboard-category');dashboard.append(el('summary',category),el('div',undefined,'tools'));$('overview').querySelector('.explanation').before(dashboard);}
    const card=el('button',undefined,'tool');card.append(el('h3',name),el('p',description),el('strong','Werkzeug öffnen →'));card.onclick=()=>open(id);dashboard.querySelector('.tools').append(card);
  }
  let folderId=0;
  function folder(label,value='/mnt'){
    const item=input(label,value),id='advanced-folder-'+(++folderId);item.node.id=id;const view=el('input');view.type='hidden';view.value='host';view.id=id+'-view';item.wrap.append(view);
    item.initialize=()=>{const form=el('form');item.wrap.before(form);form.append(item.wrap);installFolderPicker(id,view.id);form.replaceWith(item.wrap);item.node.dispatchEvent(new Event('input'));};return item;
  }
  async function open(id){page(id);await load(id);}
  async function load(id){
    if(pending.has(id))return;pending.add(id);const {body,status}=pages.get(id);status.textContent=t('Prüfung läuft …');
    try{
      const capability=await api('admin/status');if(!capability.enabled)throw Error(capability.note);if(!capability.demo&&!capability.advanced)throw Error(t('Host-Helfer nicht bereit. docker compose up -d --build starten und die host-bootstrap-Logs prüfen.'));
      body.replaceChildren();status.textContent=capability.demo?t('Beispieldaten – keine Verbindung zu deinem Server.'):t('Stand: {time}',{time:new Date().toLocaleTimeString(I18N.locale)});
      if(id==='shell-advanced'){
        if(!capability.demo&&!capability.terminal)throw Error(t('Host-Helfer nicht bereit. docker compose up -d --build starten und die host-bootstrap-Logs prüfen.'));
        window.ServerLotseTerminal.render(body,capability.demo);
      }
      if(id==='clean-advanced')await renderClean(body);
      if(id==='firewall-advanced')await renderFirewall(body);
      if(id==='automation-advanced')await renderAutomation(body);
      if(id==='healing-advanced')await renderHealing(body);
      if(id==='updates-advanced')await renderUpdates(body);
      if(id==='bundle-advanced')await renderBundle(body);
    if(id==='remote-advanced')await renderRemote(body);
      if(id==='proxy-advanced')renderProxy(body);
    }catch(error){status.textContent=error.message;status.classList.add('warning-text');}
    finally{pending.delete(id);}
  }
  async function renderClean(body){
    const data=await read({view:'sensor_unused'});body.append(el('p',data.note,'warning-text'),pre(data.text),button('Images und Cache vorschauen',()=>change({operation:'docker_clean'})));
    const volume=select('Einzelnes Volume',data.volumes.map(name=>[name,name]));const block=form([volume]);const remove=button('Volume-Löschung vorschauen',()=>change({operation:'volume_delete',name:volume.node.value}),'danger');remove.disabled=!data.volumes.length;block.append(el('p','Endgültige Löschung verlangt LOESCHEN. Die Automatik löscht niemals Volumes.','warning-text'),remove);body.append(block);
  }
  async function renderFirewall(body){
    const data=await read({view:'sensor_firewall'});body.append(pre(data.text),el('p',data.note||''));
    const port=input('Port','8080','number'),protocol=select('Protokoll',[['tcp','TCP'],['udp','UDP']]),verb=select('Aktion',[['allow',t('Freigeben')],['close',t('Einfache Freigabe entfernen')]]),block=form([port,protocol,verb]);
    block.append(button('Regel vorschauen',()=>change({operation:'firewall_rule',port:port.node.value,protocol:protocol.node.value,verb:verb.node.value}),'primary'));body.append(block);
  }
  async function renderAutomation(body){
    const cfg=await read({view:'advanced_settings'}),enabled=check('Automatik-Hauptschalter',cfg.enabled),cpu=check('CPU-Warnungen senden',cfg.notify_cpu),ram=check('RAM-Warnungen senden',cfg.notify_ram),ssh=check('SSH-Angriffsradar aktivieren',cfg.notify_ssh),cpuLimit=input('CPU-Grenzwert (%)',cfg.cpu,'number'),ramLimit=input('RAM-Grenzwert (%)',cfg.ram,'number'),hold=input('Mindestdauer (Sekunden)',cfg.hold_seconds,'number'),cooldown=input('Sendepause (Minuten)',cfg.cooldown_minutes,'number'),failures=input('SSH-Fehler pro Minute',cfg.ssh_failures,'number'),janitor=check('Nächtliche Images-/Cache-Pflege',cfg.janitor),hour=input('Stunde der Docker-Pflege',cfg.janitor_hour,'number');
    const kind=select('Benachrichtigungsziel',[['discord','Discord'],['telegram','Telegram'],['generic','HTTPS Webhook']],cfg.webhook_kind),url=input('Webhook-Adresse (leer = unverändert)','','password'),token=input('Telegram-Bot-Token (leer = unverändert)','','password'),chat=input('Telegram-Chat-ID (leer = unverändert)','','password'),clear=check('Hinterlegte Benachrichtigungsdaten löschen'),rclone=input('rclone-Konfigurationsdatei (optional)',cfg.rclone_config);
    const block=form([enabled,cpu,ram,ssh,cpuLimit,ramLimit,hold,cooldown,failures,janitor,hour,kind,url,token,chat,clear,rclone]);
    const showProvider=()=>{const telegram=kind.node.value==='telegram';url.wrap.hidden=telegram;token.wrap.hidden=chat.wrap.hidden=!telegram;};kind.node.onchange=showProvider;showProvider();
    block.append(el('p',(cfg.webhook_url_configured||cfg.telegram_token_configured)?'Benachrichtigungsdaten sind hinterlegt. Geheimnisse werden nicht angezeigt.':'Noch kein Benachrichtigungsziel hinterlegt.','hint'));
    block.append(el('p','Sicherungspläne und APT-Update-Zeitplan werden separat verwaltet.','hint'));
    const selectedContainers=new Set(cfg.heal_containers),selectedServices=new Set(cfg.heal_services),targets=el('div');
    let containers=[],services=[];
    try{containers=(await read({view:'containers'})).rows;}catch(error){block.append(el('p',error.message,'warning-text'));}
    try{services=(await read({view:'services'})).rows;}catch(error){block.append(el('p',error.message,'warning-text'));}
    const c=select('Container für Auto-Heiler',containers.map(row=>[row.ID,row.Names])),s=select('Dienst für Auto-Heiler',services.map(row=>[row.name,row.name]));
    const draw=()=>{targets.replaceChildren();for(const [set,type]of [[selectedContainers,'container'],[selectedServices,'service']])for(const value of set){const name=type==='container'?(containers.find(row=>row.ID===value)?.Names||value):value;targets.append(actions(rawEl('span',name),button('Entfernen',()=>{set.delete(value);draw();})));}};draw();
    block.append(el('h2','Auto-Heiler-Ziele'),fieldsLocal(c,s),actions(button('Container hinzufügen',()=>{if(c.node.value)selectedContainers.add(c.node.value);draw();}),button('Dienst hinzufügen',()=>{if(s.node.value)selectedServices.add(s.node.value);draw();})),targets);
    block.append(actions(button('Einstellungen vorschauen',async()=>{
      const settings={enabled:enabled.node.checked,notify_cpu:cpu.node.checked,notify_ram:ram.node.checked,notify_ssh:ssh.node.checked,cpu:cpuLimit.node.value,ram:ramLimit.node.value,hold_seconds:hold.node.value,cooldown_minutes:cooldown.node.value,ssh_failures:failures.node.value,janitor:janitor.node.checked,janitor_hour:hour.node.value,webhook_kind:kind.node.value,webhook_url:url.node.value,telegram_token:token.node.value,telegram_chat:chat.node.value,clear_webhook:clear.node.checked,rclone_config:rclone.node.value,heal_containers:[...selectedContainers],heal_services:[...selectedServices]};
      url.node.value=token.node.value=chat.node.value='';await change({operation:'settings_save',settings});
    },'primary'),button('Testnachricht vorschauen',()=>change({operation:'webhook_test'}))));body.append(block);
  }
  function fieldsLocal(...items){const node=el('div',undefined,'fields');node.append(...items.map(item=>item.wrap));return node;}
  async function renderHealing(body){
    const data=await read({view:'advanced_heal'});if(!data.rows.length)body.append(el('p','Noch keine Auto-Heiler-Ziele konfiguriert.'));
    for(const row of data.rows){const block=el('article',undefined,'panel');block.append(rawEl('h2',row.name||row.target),el('p',row.suppressed?'Nach manuellem Stopp pausiert.':'Keine manuelle Sperre.'),rawEl('p',row.attempts.map(value=>new Date(value*1000).toLocaleString(I18N.locale)).join('\n')),button('Sperre und Zähler zurücksetzen',()=>change({operation:'heal_resume',target:row.target})));body.append(block);}
    body.append(button('↻ Aktualisieren',()=>load('healing-advanced')));
  }
  async function renderUpdates(body){
    const data=await read({view:'advanced_updates'});body.append(pre(data.timers),pre(data.policy||t('Noch keine ServerLotse-Richtlinie vorhanden.')));
    const enabled=check('Nächtliche Sicherheitsupdates aktivieren',data.enabled),hour=input('Stunde (Host-Zeitzone)',data.hour??3,'number'),minute=input('Minute',data.minute??0,'number'),block=form([enabled,hour,minute]);
    if(!data.installed)block.append(el('p','unattended-upgrades fehlt. Auf dem Host installieren; danach diese Seite aktualisieren.','warning-text'),button('unattended-upgrades installieren',()=>change({operation:'tool_install',package:'unattended-upgrades'})));
    block.append(button('Update-Zeitplan vorschauen',()=>change({operation:'update_policy',enabled:enabled.node.checked,hour:hour.node.value,minute:minute.node.value}),'primary'));body.append(block);
  }
  async function renderBundle(body){
    const name=input('Sicherungsname'),source=folder('Quellordner'),destination=folder('Sicherungsziel'),hours=input('Intervall in Stunden','24','number'),enabled=check('Zeitplan aktivieren');
    let containers=[],remotes=[];
    try{containers=(await read({view:'containers'})).rows;}catch(error){body.append(el('p',error.message));}
    try{remotes=(await read({view:'advanced_remotes'})).remotes;}catch(error){body.append(el('p',error.message,'hint'));}
    const container=select('Datenbankcontainer (optional)',[['',t('Kein Datenbankexport')],...containers.map(row=>[row.ID,row.Names])]),database=input('MySQL-/MariaDB-Datenbank (optional)'),user=input('Datenbankbenutzer','root'),remote=select('Remote-Profil (optional)',[['',t('Nur lokal')],...remotes.map(name=>[name,name])]),path=input('Remote-Bucket/Ordner','backups');
    const block=form([name,source,destination,hours,enabled,container,database,user,remote,path]);
    block.append(el('p','SQL-Passwort stammt aus dem gewählten Container. Dateisicherung und SQL sind kein gemeinsamer atomarer Snapshot. Für große Datenbestände wird vorübergehend Platz für TAR und .tar.gz benötigt.','warning-text'),button('Sicherung und Upload vorschauen',()=>change({operation:'bundle_run',name:name.node.value,source:source.node.value,destination:destination.node.value,hours:hours.node.value,enabled:enabled.node.checked,container:container.node.value,database:database.node.value,db_user:user.node.value,remote:remote.node.value?remote.node.value+path.node.value:''}),'primary'));
    body.append(block);source.initialize();destination.initialize();
    body.append(button('Sicherungspläne und Archive öffnen',()=>{const item=nav.querySelector('[data-page="backups-admin"]');if(item)item.click();}));
  }
  async function renderRemote(body){
    const tools=await read({view:'advanced_tools'});
    if(!tools.tools.rclone)body.append(el('p','Für Uploads fehlt rclone auf dem Host.','warning-text'),button('rclone installieren',()=>change({operation:'tool_install',package:'rclone'})));
    const name=input('Remote-Name','serverlotse_backup'),provider=select('Protokoll',[['sftp',t('SFTP (SSH-Schlüssel)')],['s3',t('S3 (AWS oder kompatibel)')]]),host=input('SFTP-Hostname'),user=input('SFTP-Benutzer','backup'),port=input('SFTP-Port','22','number'),key=input('Privater SSH-Schlüssel auf dem Host','/root/.ssh/id_ed25519'),known=input('known_hosts-Datei auf dem Host','/root/.ssh/known_hosts'),endpoint=input('S3-Endpunkt (leer = AWS)'),region=input('S3-Region','us-east-1'),access=input('S3-Zugriffsschlüssel','','password'),secret=input('S3-Geheimschlüssel','','password');
    const block=form([name,provider,host,user,port,key,known,endpoint,region,access,secret]);
    const toggle=()=>{const sftp=provider.node.value==='sftp';for(const item of [host,user,port,key,known])item.wrap.hidden=!sftp;for(const item of [endpoint,region,access,secret])item.wrap.hidden=sftp;};provider.node.onchange=toggle;toggle();
    block.append(button('Remote-Profil vorschauen',async()=>{const data={operation:'remote_save',name:name.node.value,provider:provider.node.value,host:host.node.value,user:user.node.value,port:port.node.value,key_file:key.node.value,known_hosts_file:known.node.value,endpoint:endpoint.node.value,region:region.node.value,access_key:access.node.value,secret_key:secret.node.value};access.node.value=secret.node.value='';await change(data);},'primary'));body.append(block);
  }
  function renderProxy(body){
    const engine=select('Nativer Proxy',[['caddy','Caddy'],['nginx','Nginx + Certbot']]),domain=input('Domain','example.com'),upstream=input('Zieldienst','http://127.0.0.1:3000'),email=input('E-Mail für Zertifikatskonto','','email'),consent=check('ACME-Bedingungen und öffentliche Protokollierung der Domain akzeptieren'),block=form([engine,domain,upstream,email,consent]);
    const terms=el('a','Zertifikatsbedingungen lesen');terms.href='https://letsencrypt.org/repository/';terms.target='_blank';terms.rel='noopener noreferrer';
    const proxyActions=el('div',undefined,'result-actions');proxyActions.append(terms,button('Proxy-Einrichtung vorschauen',()=>change({operation:'proxy_apply',engine:engine.node.value,domain:domain.node.value,upstream:upstream.node.value,email:email.node.value,acme_consent:consent.node.checked}),'primary'));block.append(el('p','Bestehenden Nginx Proxy Manager weiterhin in dessen Oberfläche verwalten. Diese Funktion benötigt einen nativen Proxy und passende DNS-/Portweiterleitungen.','warning-text'),proxyActions);body.append(block);
  }
  document.addEventListener('languagechange',()=>{for(const [id]of definitions)if(!pages.get(id).section.hidden)load(id);});
})();
