/* Fixed host operations only. Previews never execute changes. */
(() => {
  const sections = [
    ['health-admin','Systemzustand','System','Last, Arbeitsspeicher, Speicherwarnungen und geführte Fehlerdiagnose.'],
    ['services-admin','Dienste und Autostart','System','Dienste prüfen, starten, stoppen und den Autostart ändern.'],
    ['updates-admin','Updates','System','Paketlisten aktualisieren, Änderungen vorab prüfen und Updates installieren.'],
    ['disks-admin','Laufwerke','Speicher','Alle Laufwerke sehen, Zustand prüfen und Datenplatten ein- oder aushängen.'],
    ['containers-admin','Container verwalten','Docker','Container steuern und ihre Ressourcennutzung prüfen.'],
    ['backups-admin','Sicherungen','Backups','Dateisicherungen planen, Inhalte prüfen und separat wiederherstellen.'],
    ['network-admin','Netzwerk','Netzwerk','Adressen, Ports, DNS und Erreichbarkeit vom Server aus prüfen.'],
    ['users-admin','Benutzer und Gruppen','Benutzer und Rechte','Normale Benutzer und Gruppen erstellen und bearbeiten.'],
    ['rights-admin','Dateirechte','Benutzer und Rechte','Eigentümer, Gruppen, Zugriffsrechte und ACLs verstehen und gezielt ändern.'],
    ['audit-admin','Aktionsprotokoll','Verwaltung','Ausgeführte Änderungen und geplante Sicherungen dauerhaft nachvollziehen.']
  ];
  const help = {
    'health-admin':'Die Last beschreibt wartende oder arbeitende Prozesse. Vergleiche sie mit der Zahl der CPU-Kerne. Freier Speicher allein reicht nicht: auch Dateieinträge (Inodes) können knapp werden.',
    'services-admin':'Aktiv bedeutet: läuft jetzt. Autostart bedeutet: startet beim Booten. Ein gestoppter Dienst kann weiterhin für den nächsten Boot aktiviert sein. Zugangsdienste sind gegen Unterbrechungen geschützt.',
    'updates-admin':'Paketlisten sind das Inhaltsverzeichnis verfügbarer Updates. Die Vorschau installiert nichts. Vor Updates eine Sicherung anlegen. Derzeit werden Debian, DietPi und Ubuntu mit APT unterstützt.',
    'disks-admin':'Mount verbindet ein Dateisystem mit einem Ordner. Der gewählte Name wird /mnt/name. Nicht formatierte Platten werden angezeigt, aber nicht formatiert. USB-Adapter unterstützen SMART nicht immer.',
    'containers-admin':'Start startet einen vorhandenen Container. Stop beendet ihn, Restart startet ihn neu. Daten und Images werden nicht gelöscht. Eigene ServerLotse-Container sind geschützt.',
    'backups-admin':'Eine Dateisicherung ist kein Datenbank-Snapshot. Datenbanken vorher stoppen oder separat exportieren. Backups auf derselben Platte schützen nicht vor Plattenausfall. Zeitpläne laufen im Host-Helfer auch ohne geöffneten Browser.',
    'network-admin':'Ein offener Port ist ein lauschender Dienst. Ein erfolgreicher TCP-Test bestätigt nur die Verbindung vom Server zum Ziel, nicht die Funktion einer ganzen Anwendung oder einen Zugriff aus dem Internet.',
    'users-admin':'Systemkonten bleiben geschützt. Zusätzliche Gruppen werden ergänzt, nicht entfernt. Administrative Gruppen werden hier nicht vergeben. Eine Passwortsperre sperrt keine bestehenden SSH-Schlüssel.',
    'rights-admin':'r bedeutet lesen, w schreiben, x ausführen beziehungsweise Ordner betreten. Die drei Ziffern gelten für Eigentümer, Gruppe und andere. 750 erlaubt dem Eigentümer alles, der Gruppe Lesen und Betreten, anderen nichts.',
    'audit-admin':'Der Verlauf bleibt beim Containerneustart erhalten. Passwörter werden weder in Vorschau noch Protokoll gespeichert. Unterbrochene Aktionen werden gekennzeichnet und müssen vor einem erneuten Versuch geprüft werden.'
  };
  const navigation=document.querySelector('nav'), groups=new Map();
  for(const group of navigation.querySelectorAll('.nav-category'))groups.set(I18N.original(group.querySelector('summary').textContent),group);
  function groupFor(name){
    if(groups.has(name))return groups.get(name);
    const group=el('details',undefined,'nav-category');group.dataset.pages='';group.append(el('summary',name));navigation.insertBefore(group,navigation.querySelector('[data-page="history"]'));groups.set(name,group);return group;
  }
  const panels=new Map(), states=new Map();
  for(const [id,name,category,description]of sections){
    const section=el('section',undefined,'page');section.id=id;section.hidden=true;
    section.append(el('span',category,'eyebrow'),el('h1',name),el('p',description));
    const explain=el('details',undefined,'admin-help');explain.append(el('summary','Was bedeutet das?'),el('p',help[id]));
    const state=el('p','Host-Verwaltung wird geprüft …','hint');state.setAttribute('role','status');states.set(id,state);
    const body=el('div');panels.set(id,body);section.append(explain,state,body);document.querySelector('footer').before(section);
    const button=el('button',name);button.dataset.page=id;button.onclick=()=>{page(id);load(id);};
    const group=groupFor(category);group.dataset.pages=[group.dataset.pages,id].filter(Boolean).join(',');group.append(button);
  }
  // Move existing tools to the relevant new categories.
  for(const [id,category]of [['storage','Speicher'],['mounts','Speicher'],['docker','Docker'],['copy_plan','Dateiverwaltung']]){
    const button=navigation.querySelector('[data-page="'+id+'"]');if(button){for(const group of groups.values())group.dataset.pages=group.dataset.pages.split(',').filter(x=>x!==id).join(',');const group=groupFor(category);group.append(button);group.dataset.pages+=','+id;}
  }
  const dashboardGroups=new Map([...document.querySelectorAll('.dashboard-category')].map(group=>[I18N.original(group.querySelector('summary').textContent),group]));
  for(const [id,name,category,description]of sections){
    let group=dashboardGroups.get(category);
    if(!group){group=el('details',undefined,'dashboard-category');group.append(el('summary',category),el('div',undefined,'tools'));$('overview').querySelector('.explanation').before(group);dashboardGroups.set(category,group);}
    const card=el('button',undefined,'tool');card.append(el('h3',name),el('p',description),el('strong','Werkzeug öffnen →'));card.onclick=()=>{page(id);load(id);};group.querySelector('.tools').append(card);
  }
  const version=document.querySelector('.sidebar-bottom small');I18N.bind(version,'VERSION 0.7.4 · WERKZEUGKISTE');
  const explanation=document.querySelector('.explanation p');I18N.bind(explanation,'Diagnose und Verwaltung an einem Ort. Änderungen werden vorab angezeigt und dauerhaft protokolliert.');
  const overviewPanel=el('section',undefined,'panel admin-overview');overviewPanel.append(el('h2','Systemzustand und Diagnose'));
  const statusOverview=el('p','Host-Verwaltung wird geprüft …');overviewPanel.append(statusOverview);
  const overviewActions=el('div',undefined,'result-actions');
  for(const id of ['health-admin','backups-admin','audit-admin']){const button=el('button',sections.find(s=>s[0]===id)[1],'secondary');button.onclick=()=>{page(id);load(id);};overviewActions.append(button);}
  overviewPanel.append(overviewActions);document.querySelector('.power-panel').after(overviewPanel);

  const read=data=>api('admin/read',data);
  function button(text,callback,kind='secondary'){const b=el('button',text,kind);b.type='button';b.onclick=async()=>{b.disabled=true;try{await callback();}catch(error){message(error.message);}finally{b.disabled=false;}};return b;}
  function input(label,value='',type='text'){const wrap=el('label',label),node=el('input');node.type=type;node.value=value;node.autocomplete=type==='password'?'new-password':'off';wrap.append(node);return {wrap,node};}
  function select(label,options,value){const wrap=el('label',label),node=el('select');for(const [key,text]of options){const option=el('option',text);option.value=key;node.append(option);}if(value!==undefined)node.value=value;wrap.append(node);return {wrap,node};}
  function check(label,value=false){const wrap=el('label',undefined,'admin-check'),node=el('input');node.type='checkbox';node.checked=value;wrap.append(node,el('span',label));return {wrap,node};}
  function form(fields){const block=el('div',undefined,'panel'),grid=el('div',undefined,'fields');grid.append(...fields.map(f=>f.wrap));block.append(grid);return block;}
  function pre(value){return rawEl('pre',typeof value==='string'?value:JSON.stringify(value,null,2));}
  function table(headers,rows){const wrap=el('div',undefined,'table-scroll'),table=el('table'),head=el('tr');headers.forEach(h=>head.append(el('th',h)));table.append(head);for(const cells of rows){const tr=el('tr');for(const cell of cells){const td=rawEl('td');if(cell instanceof Node)td.append(cell);else td.textContent=String(cell??'');tr.append(td);}table.append(tr);}wrap.append(table);return wrap;}
  function actions(...items){const row=el('div',undefined,'result-actions');row.append(...items);return row;}
  function rawJSON(value){const details=el('details',undefined,'admin-help');details.append(el('summary','Details anzeigen'),pre(value));return details;}
  let folderId=0;
  function folder(label,value='/mnt'){
    const f=input(label,value),id='admin-folder-'+(++folderId);f.node.id=id;
    const v=el('input');v.type='hidden';v.id=id+'-view';v.value='host';f.wrap.append(v);
    f.initialize=()=>{const holder=el('form');f.wrap.before(holder);holder.append(f.wrap);installFolderPicker(id,v.id);holder.replaceWith(f.wrap);f.node.dispatchEvent(new Event('input'));};
    return f;
  }

  const dialog=el('dialog',undefined,'power-dialog admin-dialog'),title=el('h2','Änderung prüfen'),details=el('div'),confirm=input('Zur Bestätigung AUSFUEHREN eingeben'),feedback=el('p');feedback.setAttribute('role','status');
  const cancel=button('Abbrechen',()=>{prepared=null;confirm.node.value='';dialog.close();}),apply=button('Bestätigen',async()=>{
    if(!prepared||confirm.node.value!==prepared.confirmation)return;
    const request=prepared;prepared=null;
    try{const job=await api('admin/execute',{nonce:request.nonce,confirmation:confirm.node.value});confirm.node.value='';dialog.close();page('audit-admin');await load('audit-admin');watch(job.id);document.dispatchEvent(new CustomEvent('admin-task-started',{detail:{id:job.id,operation:request.preview?.operation}}));}
    catch(error){feedback.textContent=error.message;}
  },'danger');
  const confirmationCaption=el('span','Zur Bestätigung AUSFUEHREN eingeben');confirm.wrap.firstChild.replaceWith(confirmationCaption);
  apply.disabled=true;confirm.node.oninput=()=>apply.disabled=!prepared||confirm.node.value!==prepared.confirmation;
  dialog.append(title,details,confirm.wrap,feedback,actions(cancel,apply));document.body.append(dialog);
  let prepared=null,preparing=false;
  dialog.addEventListener('close',()=>{prepared=null;confirm.node.value='';});
  async function preview(data){
    if(preparing)return;preparing=true;message();
    try{
      const result=await api('admin/prepare',data);prepared=result;confirm.node.value='';apply.disabled=true;feedback.textContent='';details.replaceChildren();
      I18N.bind(confirmationCaption,'Zur Bestätigung '+result.confirmation+' eingeben');
      for(const warning of result.warnings||[])details.append(el('p',warning,'warning-text'));
      const labels={pid:'PID',uid:'UID',package:'Paket',acme_consent:'ACME-Zustimmung',command:'Root-Befehl',settings:'Einstellungen',port:'Port',protocol:'Protokoll',engine:'Nativer Proxy',domain:'Domain',upstream:'Zieldienst',email:'E-Mail für Zertifikatskonto',database:'Datenbank',db_user:'Datenbankbenutzer',remote:'Remote-Ziel',provider:'Protokoll',host:'Hostname',user:'Benutzer',key_file:'SSH-Schlüssel',known_hosts_file:'known_hosts-Datei',endpoint:'S3-Endpunkt',region:'S3-Region',irreversible:'Endgültige Löschung',minimum_age_hours:'Mindestalter in Stunden',hour:'Stunde',minute:'Minute',password_change:'Passwort wird geändert',operation:'Aktion',name:'Name',verb:'Aktion',path:'Pfad',device:'Datenträger',uuid:'UUID',persistent:'Beim Systemstart automatisch einhängen',shell:'Shell',login:'Anmeldung mit Shell erlauben',lock_action:'Passwortanmeldung',groups:'Zusätzliche Gruppen (Komma getrennt)',mode:'Rechte',owner:'Eigentümer',group:'Gruppe',container:'Container',source:'Quellordner',destination:'Sicherungsziel',hours:'Intervall in Stunden',enabled:'Zeitplan aktivieren',archive:'Archiv',target:'Wiederherstellungsziel'};
      const operationNames={process_signal:'Prozesssignal senden',tool_install:'Werkzeug installieren',shell_run:'Root-Befehl ausführen',docker_clean:'Alte Images und Cache bereinigen',volume_delete:'Volume endgültig löschen',firewall_rule:'Firewall-Regel ändern',settings_save:'Automatik-Einstellungen speichern',webhook_test:'Testnachricht senden',update_policy:'Update-Zeitplan speichern',proxy_apply:'Proxy einrichten',bundle_run:'Komprimierte Sicherung erstellen',remote_save:'Remote-Profil speichern',heal_resume:'Auto-Heiler-Sperre zurücksetzen',service:'Dienst ändern',updates_refresh:'Paketlisten aktualisieren',updates_install:'Updates installieren',mount:'Einhängen',unmount:'Aushängen',user_create:'Benutzer erstellen',user_edit:'Benutzer bearbeiten',group_create:'Gruppe erstellen',permissions:'Dateirechte ändern',container:'Container verwalten',backup_save:'Sicherungsplan speichern',backup_run:'Jetzt sichern',backup_verify:'Inhalte prüfen',backup_restore:'Wiederherstellen',backup_toggle:'Zeitplan ändern'};
      Object.assign(operationNames,{lab_janitor:'Erweiterter Docker-Janitor',lab_clone:'Container klonen',lab_env:'Container-Umgebung ändern',lab_template:'App-Vorlage starten',lab_dotenv:'.env-Datei ändern',lab_compose:'Compose neu bereitstellen',lab_registry:'Registry vergleichen',lab_settings:'Wächter-Einstellungen speichern',lab_baseline:'FIM-Vergleichsbasis übernehmen',lab_session_end:'Anmeldesitzung beenden',lab_http:'HTTP-Status prüfen',lab_speedtest:'Speedtest ausführen',lab_rotate:'Log-Richtlinie ausführen',lab_restore_test:'Isolierten SQL-Testrestore starten'});
      Object.assign(operationNames,{lab_cache:'RAM-Dateicache',lab_apt_clean:'Paket-Wartung',lab_orphan_end:'SIGTERM vorschauen',lab_panic:'Notfallbremse',lab_panic_release:'Jetzt zurücknehmen',lab_config_write:'Konfiguration mit Rücknahme',lab_config_keep:'Beibehalten',lab_config_undo:'Jetzt zurücknehmen',lab_ddns_save:'DDNS-Einstellungen',lab_ddns_update:'Dynamisches DNS',lab_inode_watch:'Inode-Wächter',lab_domain_proxy:'Domain zum Container',lab_builder:'Compose-Baukasten',lab_volume_write:'Volume-Dateien',lab_trivy:'Image-Schwachstellen'});
      Object.assign(labels,{addresses:'Verwaltungs-IP-Adressen, eine je Zeile',seconds:'Sekunden',packages:'Pakete',bytes:'Größe in Bytes',kind:'Konfiguration',config:'Einstellungen',services:'Dienste',threshold:'Warnung ab (%)'});
      Object.assign(labels,{targets:'Endgültige Löschziele',shared_mounts:'Geteilte Datenpfade (nur lesend)',readonly:'Daten nur lesend teilen',env_updates:'Geänderte Variablen (maskiert)',bind:'Bind-IP',template:'App-Vorlage',directory:'Projektbasis',files:'Compose-Dateien',service:'Dienst',session:'Sitzung',user:'Benutzer',url:'Webadresse',expected:'Erwarteter HTTP-Status',driver:'Speedtest-Anbieter',consent:'Bedingungen und Datenübertragung bestätigt',paths:'Überwachte Pfade',image:'Lokales Datenbank-Image',file_count:'Dateien in der Vergleichsbasis'});
      const rows=Object.entries(result.preview).filter(([key])=>key in labels).map(([key,value])=>[el('span',labels[key]),key==='operation'?el('span',operationNames[value]||value):typeof value==='boolean'?el('span',value?'Ja':'Nein'):Array.isArray(value)?value.join(', '):value&&typeof value==='object'?pre(value):value]);
      details.append(table(['Einstellung','Geplanter Wert'],rows));
      if(result.preview.simulation)details.append(pre(result.preview.simulation));
      details.append(rawJSON(result.preview),el('p','Die Vorschau ist 120 Sekunden gültig.'));dialog.showModal();confirm.node.focus();
    }finally{if(data.password)data.password='';preparing=false;}
  }
  async function watch(id){
    for(let i=0;i<7200;i++){
      await new Promise(r=>setTimeout(r,2000));
      try{const data=await read({view:'audit'});const job=data.rows.find(r=>r.id===id);
        if(!job||!['queued','running'].includes(job.status)){if(!$('audit-admin').hidden)await load('audit-admin');return;}
        if(!$('audit-admin').hidden)states.get('audit-admin').textContent=t('Verwaltungsaktion läuft …');
      }catch{return;}
    }
  }
  const requests=new Map();
  async function load(id){
    const seq=(requests.get(id)||0)+1;requests.set(id,seq);const status=states.get(id),body=panels.get(id);status.textContent=t('Prüfung läuft …');
    try{
      const capability=await api('admin/status');if(requests.get(id)!==seq)return;
      if(!capability.enabled){status.textContent=capability.note;body.replaceChildren(el('p','Host-Helfer nicht bereit. docker compose up -d --build starten und die host-bootstrap-Logs prüfen.'));return;}
      const views={'health-admin':'health','services-admin':'services','updates-admin':'updates','disks-admin':'disks','containers-admin':'containers','backups-admin':'backups','network-admin':'network','users-admin':'users','audit-admin':'audit'};
      const data=id==='rights-admin'?{}:await read({view:views[id]});if(requests.get(id)!==seq)return;
      status.textContent=capability.demo?t('Beispieldaten – keine Verbindung zu deinem Server.'):t('Stand: {time}',{time:new Date().toLocaleTimeString(I18N.locale)});body.replaceChildren();
      body.append(button('↻ Aktualisieren',()=>load(id)));
      render(id,body,data);
    }catch(error){if(requests.get(id)===seq)status.textContent=error.message;}
  }
  function render(id,body,data){
    if(id==='health-admin'){
      body.append(table(['Name / Pfad','Ergebnis'],[
        [el('span','Servername'),data.hostname],['CPU',data.cpus],[el('span','Last (1/5/15 Minuten)'),data.load.join(' / ')],[el('span','Laufzeit'),Math.round(data.uptime/3600)+' h'],
        [el('span','RAM verfügbar / gesamt'),fmt(data.memory.MemAvailable)+' / '+fmt(data.memory.MemTotal)],[el('span','Neustart erforderlich'),el('span',data.reboot_required?'Ja':'Nein')]]));
      if(!data.findings.length)body.append(el('p','Keine Warnung in diesen Prüfungen. Weitere Fehler können trotzdem vorliegen.'));
      for(const finding of data.findings){const card=el('div',undefined,'finding');card.append(el('strong',finding.meaning),rawEl('p',finding.path||''),el('p',finding.next));const target=finding.code==='space'?'storage':finding.code==='failed_services'?'services-admin':'containers-admin';card.append(button('Nächster Schritt',()=>{page(target);if(panels.has(target))load(target);}));body.append(card);}
      body.append(el('h2','Fehler beim aktuellen Start'),pre(data.journal),button('Diese Logs auswerten',()=>{page('log');$('log-text').value=data.journal;run({action:'log',text:data.journal},$('log-result'),'log');}));
    }
    if(id==='services-admin'){
      const filter=input('Dienste filtern'),result=el('div');body.append(filter.wrap,result);
      const draw=()=>result.replaceChildren(table(['Dienst','Status','Autostart','Startzeit','Aktionen'],data.rows.filter(r=>r.name.toLowerCase().includes(filter.node.value.toLowerCase())).map(row=>[
        row.name,row.active+' / '+(row.sub||''),row.autostart,row.started||'—',actions(button('Details anzeigen',async()=>{const result=await read({view:'service',name:row.name});showDetails(result);}),...['start','stop','restart','enable','disable'].map(verb=>button({start:'Starten',stop:'Stoppen',restart:'Neustart',enable:'Autostart an',disable:'Autostart aus'}[verb],()=>preview({operation:'service',name:row.name,verb}))))])));
      filter.node.oninput=draw;draw();
    }
    if(id==='updates-admin')body.append(actions(button('Paketlisten aktualisieren',()=>preview({operation:'updates_refresh'})),button('Updates installieren',()=>preview({operation:'updates_install'}),'primary')),el('p',data.note),pre(data.simulation));
    if(id==='disks-admin'){
      body.append(table(['Datenträger','Größe','Dateisystem','Label / UUID','Einhängepunkte','Aktionen'],data.rows.map(row=>{
        const mounts=(row.mountpoints||[]).filter(Boolean),controls=actions();
        if(row.type==='disk'&&data.smart_available)controls.append(button('Zustand (SMART)',async()=>{const result=await read({view:'smart',device:row.path});showDetails({summary:result.smart_status?.passed===true?t('SMART meldet keinen Ausfall. Das ersetzt keine Sicherung.'):result.smart_status?.passed===false?t('SMART meldet ein Problem. Daten sichern und Laufwerk prüfen.'):t('SMART-Zustand nicht verfügbar. USB-Adapter oder Laufwerk unterstützen die Abfrage möglicherweise nicht.'),temperature:result.temperature?.current,details:result});}));
        if(!mounts.length&&row.fstype&&['disk','part'].includes(row.type))controls.append(button('Einhängen',()=>mountForm(row)));
        for(const path of mounts.filter(m=>m.startsWith('/mnt/')))controls.append(button('Aushängen',()=>preview({operation:'unmount',path}),'danger'));
        return [row.path,fmt(Number(row.size)),row.fstype||'—',(row.label||'')+' / '+(row.uuid||''),mounts.join('\n')+'\n'+row.usage.map(u=>u.percent+'% · '+fmt(u.free)+' free').join('\n'),controls];
      })));
      if(!data.smart_available)body.append(el('p','SMART-Werkzeug fehlt. Auf dem Host smartmontools installieren.'));
      body.append(rawJSON(data.mounts));
    }
    if(id==='containers-admin'){
      const resources=new Map(data.resources.map(r=>[r.ID,r]));body.append(table(['Container','Status','CPU / RAM','Aktionen'],data.rows.map(row=>{
        const usage=resources.get(row.ID)||{};
        return [row.Names,row.Status,(usage.CPUPerc||'—')+' / '+(usage.MemUsage||'—'),actions(button('Logs',()=>{page('docker');run({action:'docker_logs',container:row.ID},$('docker-result'),'docker_logs');}),...['start','stop','restart'].map(verb=>button({start:'Starten',stop:'Stoppen',restart:'Neustart'}[verb],()=>preview({operation:'container',container:row.ID,verb}))))];
      })),rawJSON(data.resources));
    }
    if(id==='network-admin'){
      body.append(el('h2','Adressen und Routen'),table(['Schnittstelle','Adressen'],data.addresses.map(row=>[row.ifname,(row.addr_info||[]).map(r=>r.local+(r.prefixlen!==undefined?'/'+r.prefixlen:'')).join('\n')])),table(['Ziel','Gateway','Schnittstelle'],data.routes.map(row=>[row.dst,row.gateway||'—',row.dev||'—'])),el('h2','Offene Ports'),pre(data.ports),el('h2','DNS-Konfiguration'),pre(data.dns));
      const host=input('Hostname oder IP','example.com'),port=input('Port','443','number'),block=form([host,port]),result=el('div');
      block.append(button('Erreichbarkeit prüfen',async()=>{const answer=await read({view:'probe',host:host.node.value,port:port.node.value});result.replaceChildren(pre(answer));}),result);body.append(block);
    }
    if(id==='users-admin')renderUsers(body,data);
    if(id==='rights-admin'){
      const path=input('Datei- oder Ordnerpfad','/mnt'),block=form([path]),result=el('div');
      block.append(button('Rechte erklären',async()=>{const answer=await read({view:'rights',path:path.node.value});result.replaceChildren(table(['Pfad','Rechte','Eigentümer','Gruppe'],answer.rows.map(r=>[r.path,r.rights+' ('+r.mode+')',r.owner,r.group])),el('p',answer.note),pre(answer.acl));const last=answer.rows.at(-1),owner=input('Eigentümer',last.owner),group=input('Gruppe',last.group),mode=input('Rechte (z. B. 750)',last.mode),change=form([owner,group,mode]);if(window.ServerLotsePermissions)change.append(window.ServerLotsePermissions(mode.node));change.append(button('Änderung vorschauen',()=>preview({operation:'permissions',path:path.node.value,owner:owner.node.value,group:group.node.value,mode:mode.node.value}),'primary'));result.append(change);}),result);body.append(block);
    }
    if(id==='backups-admin')renderBackups(body,data);
    if(id==='audit-admin'){
      body.append(button('JSON herunterladen',()=>download(data,'json')));
      body.append(table(['Zeit','Aktion','Status','Details'],data.rows.map(row=>[new Date(row.created*1000).toLocaleString(I18N.locale),row.operation,el('span',row.status),button('Details anzeigen',async()=>showDetails(await read({view:'audit_detail',id:row.id})))])));
    }
  }
  function showDetails(data){const dialog=el('dialog',undefined,'power-dialog admin-dialog');dialog.append(el('h2','Details anzeigen'),pre(data),button('Schließen',()=>{dialog.close();dialog.remove();}));dialog.addEventListener('cancel',()=>dialog.remove());document.body.append(dialog);dialog.showModal();}
  function mountForm(row){
    const modal=el('dialog',undefined,'power-dialog'),name=input('Name unter /mnt','datenplatte'),persistent=check('Beim Systemstart automatisch einhängen'),block=form([name,persistent]);
    block.append(button('Änderung vorschauen',async()=>{modal.close();modal.remove();await preview({operation:'mount',device:row.path,name:name.node.value,persistent:persistent.node.checked});},'primary'),button('Abbrechen',()=>{modal.close();modal.remove();}));modal.append(el('h2','Laufwerk einhängen'),rawEl('p',row.path),block);modal.addEventListener('cancel',()=>modal.remove());document.body.append(modal);modal.showModal();
  }
  function renderUsers(body,data){
    const name=input('Benutzername'),login=check('Anmeldung mit Shell erlauben'),password=input('Neues Passwort (optional)','','password'),groups=input('Zusätzliche Gruppen (Komma getrennt)'),locked=select('Passwortanmeldung',[['keep','Unverändert'],['lock','Sperren'],['unlock','Entsperren']]),block=form([name,login,password,groups,locked]);let edit=false;
    block.prepend(el('h2','Benutzer erstellen oder bearbeiten'));
    block.append(button('Änderung vorschauen',async()=>{const secret=password.node.value;password.node.value='';await preview({operation:edit?'user_edit':'user_create',name:name.node.value,login:login.node.checked,password:secret,groups:groups.node.value.split(',').map(x=>x.trim()).filter(Boolean),lock_action:locked.node.value});},'primary'),button('Neuer Benutzer',()=>{edit=false;name.node.readOnly=false;name.node.value='';groups.node.value='';password.node.value='';login.node.checked=false;locked.node.value='keep';}));body.append(block);
    body.append(table(['Benutzer','UID:GID','Gruppen','Home / Shell','Aktionen'],data.rows.map(row=>[row.name,row.uid+':'+row.gid,row.groups.join(', '),row.home+'\n'+row.shell,row.editable?button('Bearbeiten',()=>{edit=true;name.node.value=row.name;name.node.readOnly=true;login.node.checked=!row.shell.endsWith('nologin')&&!row.shell.endsWith('/false');groups.node.value='';password.node.value='';locked.node.value='keep';block.scrollIntoView({block:'center',behavior:'smooth'});}):el('span','Systemkonto geschützt')])));
    const group=input('Neuer Gruppenname'),groupForm=form([group]);groupForm.append(button('Gruppe erstellen',()=>preview({operation:'group_create',name:group.node.value})));body.append(groupForm,rawJSON(data.groups));
  }
  function renderBackups(body,data){
    const name=input('Sicherungsname'),source=folder('Quellordner'),destination=folder('Sicherungsziel'),hours=input('Intervall in Stunden','24','number'),enabled=check('Zeitplan aktivieren'),block=form([name,source,destination,hours,enabled]);
    block.append(button('Sicherungsplan vorschauen',()=>preview({operation:'backup_save',name:name.node.value,source:source.node.value,destination:destination.node.value,hours:hours.node.value,enabled:enabled.node.checked}),'primary'));body.append(block);source.initialize();destination.initialize();
    for(const cfg of data.rows){
      const card=el('article',undefined,'panel');card.append(rawEl('h2',cfg.name),rawEl('p',cfg.source+' → '+cfg.destination),el('p',cfg.enabled?'Zeitplan aktiv':'Zeitplan pausiert'),rawEl('p',new Date(cfg.next_run*1000).toLocaleString(I18N.locale)));
      card.append(actions(button('Jetzt sichern',()=>preview({operation:'backup_run',id:cfg.id}),'primary'),button(cfg.enabled?'Zeitplan pausieren':'Zeitplan aktivieren',()=>preview({operation:'backup_toggle',id:cfg.id,enabled:!cfg.enabled})),button('Archive anzeigen',async()=>{
        const archives=await read({view:'archives',id:cfg.id}),list=el('div');
        for(const archive of archives.rows){const row=el('div',undefined,'panel');row.append(rawEl('p',archive.name+' · '+fmt(archive.bytes)),actions(button('Inhalte prüfen',()=>preview({operation:'backup_verify',id:cfg.id,archive:archive.name})),button('Wiederherstellen',()=>{
          const modal=el('dialog',undefined,'power-dialog'),target=folder('Wiederherstellungsziel'),f=form([target]);
          f.append(button('Wiederherstellung vorschauen',async()=>{const path=target.node.value;modal.close();modal.remove();await preview({operation:'backup_restore',id:cfg.id,archive:archive.name,target:path});},'primary'),button('Abbrechen',()=>{modal.close();modal.remove();}));modal.append(el('h2','Separat wiederherstellen'),f);modal.addEventListener('cancel',()=>modal.remove());document.body.append(modal);target.initialize();modal.showModal();
        })));list.append(row);}
        if(!archives.rows.length)list.append(el('p','Keine fertigen Archive vorhanden.'));archiveResult.replaceChildren(list);
      })));
      const archiveResult=el('div');card.append(archiveResult);body.append(card);
    }
  }
  async function dashboardStatus(){
    if(!$('access').hidden){I18N.bind(statusOverview,'Für die Host-Steuerung bitte anmelden.');return;}
    try{const status=await api('admin/status');if(!status.enabled){statusOverview.textContent=status.note;return;}
      const data=await read({view:'health'});statusOverview.textContent=t('Warnungen: {count}',{count:data.findings.length});
      statusOverview.classList.toggle('warning-text',data.findings.length>0);
    }catch(error){statusOverview.textContent=error.message;}
  }
  const previousOverview=overview;overview=async function(){await previousOverview();await dashboardStatus();};$('refresh').onclick=overview;
  window.ServerLotseAdmin={preview};
  document.addEventListener('languagechange',()=>{for(const [id]of sections)if(!$(id).hidden)load(id);});
  overview();
})();
