/* Extended tools reuse the existing authenticated preview/confirmation/audit flow. */
(() => {
  const definitions=[
    ['radar-lab','Container-Radar','Docker','Ressourcenverlauf, Laufzeit, Healthchecks und passive Image-Updateprüfung.'],
    ['clone-lab','Klonen und App-Vorlagen','Docker','Konfiguration duplizieren oder eine neue App getrennt starten.'],
    ['config-lab','Konfigurationsinspektor','Docker','Umgebungsvariablen und .env-Dateien maskiert anzeigen und gezielt ändern.'],
    ['networks-lab','Docker-Netzwerkplan','Docker','Container und ihre Netzwerkmitgliedschaften als Karte anzeigen.'],
    ['janitor-lab','Erweiterter Docker-Janitor','Docker','Konkrete gestoppte Container und unbenutzte Ressourcen nach Vorschau entfernen.'],
    ['sessions-lab','Anmeldesitzungen','Sicherheit','SSH-, lokale und ServerLotse-Sitzungen prüfen und gezielt beenden.'],
    ['certificates-lab','Zertifikats-Countdown','Sicherheit','Lokale Zertifikate und verbleibende Gültigkeit prüfen.'],
    ['wear-lab','SSD-Verschleiß','Speicher','Herstellerwerte für NVMe und eindeutig bekannte SATA-Attribute auswerten.'],
    ['history-lab','CPU-Spitzen und OOM','Monitoring','Die Verursacher vergangener Lastspitzen und Speicherabbrüche ansehen.'],
    ['restore-lab','Datenbank-Testrestore','Sicherungen','Ein SQL-Archiv in einer isolierten Wegwerf-Datenbank tatsächlich importieren.'],
    ['logs-lab','Log-Wartung','System','Große Logs finden und vorhandene Rotationsrichtlinien nutzen.'],
    ['web-lab','Web und Bandbreite','Netzwerk','HTTP-Status prüfen und einen ausdrücklich gestarteten Speedtest ausführen.'],
    ['guardian-lab','Datei- und Dienstwächter','Automatik','Dateiänderungen, Zertifikate, Webseiten, OOM und Log-Wartung überwachen.']
  ];
  function humanBytes(value){if(!value)return '0 B';const units=['B','KiB','MiB','GiB','TiB'],i=Math.min(4,Math.floor(Math.log(value)/Math.log(1024)));return (value/1024**i).toLocaleString(I18N.locale,{maximumFractionDigits:1})+' '+units[i];}
  const pages=new Map(),pending=new Set();let lastPreviewPage=null,selectedContainer='';
  const read=data=>api('admin/read',data);
  function change(data){lastPreviewPage=[...pages].find(([,p])=>!p.section.hidden)?.[0];return window.ServerLotseAdmin.preview(data);}
  function go(id){document.querySelector('nav [data-page="'+id+'"]')?.click();}
  function button(text,callback,kind='secondary'){const node=el('button',text,kind);node.type='button';node.onclick=async()=>{node.disabled=true;try{await callback();}catch(e){message(e.message);}finally{node.disabled=false;}};return node;}
  function input(label,value='',type='text'){const wrap=el('label',label),node=el(type==='textarea'?'textarea':'input');if(type!=='textarea')node.type=type;else node.rows=4;node.value=value;node.autocomplete=type==='password'?'new-password':'off';node.setAttribute('aria-label',t(label));wrap.append(node);return {wrap,node};}
  function select(label,options,value){const wrap=el('label',label),node=el('select');node.setAttribute('aria-label',t(label));for(const [key,text]of options){const option=rawEl('option',text);option.value=key;node.append(option);}if(value!==undefined&&[...node.options].some(option=>option.value===String(value)))node.value=value;wrap.append(node);return {wrap,node};}
  function check(label,value=false){const wrap=el('label',undefined,'admin-check'),node=el('input');node.type='checkbox';node.checked=value;wrap.append(node,el('span',label));return {wrap,node};}
  function fields(...items){const node=el('div',undefined,'fields');node.append(...items.map(item=>item.wrap));return node;}
  function panel(title,...nodes){const block=el('div',undefined,'panel');if(title)block.append(el('h2',title));block.append(...nodes);return block;}
  function table(headers,rows){const wrap=el('div',undefined,'table-scroll'),node=el('table'),head=el('tr');headers.forEach(label=>head.append(el('th',label)));node.append(head);for(const values of rows){const row=el('tr');for(const value of values){const cell=rawEl('td');if(value instanceof Node)cell.append(value);else cell.textContent=String(value??'—');row.append(cell);}node.append(row);}wrap.append(node);return wrap;}
  function pre(data){return rawEl('pre',typeof data==='string'?data:JSON.stringify(data,null,2));}
  function group(name){let found=[...document.querySelectorAll('nav .nav-category')].find(n=>I18N.original(n.querySelector('summary').textContent)===I18N.original(name));if(!found){found=el('details',undefined,'nav-category');found.dataset.pages='';found.append(el('summary',name));document.querySelector('nav').insertBefore(found,document.querySelector('nav [data-page="history"]'));}return found;}
  for(const [id,title,category,description]of definitions){
    const section=el('section',undefined,'page lab-page');section.id=id;section.hidden=true;const state=el('p','Noch nicht geladen.','hint'),body=el('div'),output=el('div');
    section.append(el('span',category,'eyebrow'),el('h1',title),el('p',description),state,body,output);document.querySelector('footer').before(section);pages.set(id,{section,state,body,output});
    const nav=button(title,()=>open(id));nav.className='';nav.dataset.page=id;const parent=group(category);parent.dataset.pages+=','+id;parent.append(nav);
    let dashboard=[...$('overview').querySelectorAll('.dashboard-category')].find(n=>I18N.original(n.querySelector('summary').textContent)===I18N.original(category));
    if(!dashboard){dashboard=el('details',undefined,'dashboard-category');dashboard.append(el('summary',category),el('div',undefined,'tools'));$('overview').querySelector('.explanation').before(dashboard);}
    const card=button('',()=>open(id),'tool');card.append(el('h3',title),el('p',description),el('strong','Werkzeug öffnen →'));dashboard.querySelector('.tools').append(card);
  }
  let pickerId=0;
  function folder(label,value='/mnt'){
    const item=input(label,value),id='lab-folder-'+(++pickerId),view=el('input');item.node.id=id;view.type='hidden';view.id=id+'-view';view.value='host';item.wrap.append(view);
    item.install=()=>{const form=el('form');item.wrap.before(form);form.append(item.wrap);installFolderPicker(id,view.id);form.replaceWith(item.wrap);item.node.dispatchEvent(new Event('input'));};return item;
  }
  async function open(id){page(id);await load(id);}
  async function load(id){
    if(id==='radar-lab'&&radarView){await refreshRadar();return;}
    if(pending.has(id))return;pending.add(id);const p=pages.get(id);p.state.textContent=t('Prüfung läuft …');
    try{
      const capability=await api('admin/status');if(!capability.enabled)throw Error(capability.note);
      if(!capability.demo&&!capability.workbench)throw Error(t('Host-Helfer nicht bereit. docker compose up -d --build starten und die host-bootstrap-Logs prüfen.'));
      p.body.replaceChildren();p.state.textContent=capability.demo?t('Beispieldaten – keine Verbindung zu deinem Server.'):t('Stand: {time}',{time:new Date().toLocaleTimeString(I18N.locale)});
      if(id==='radar-lab')await radar(p.body);
      if(id==='clone-lab')await clones(p.body);
      if(id==='config-lab')await inspector(p.body);
      if(id==='networks-lab')await networkMap(p.body);
      if(id==='janitor-lab')p.body.append(panel('Bewusst aufräumen',el('p','Gestoppte Container können ungesicherte Dateien enthalten. Unbenutzte Volumes können vollständige Datenbanken enthalten. Die endgültige Aktion verlangt LOESCHEN.','warning-text'),button('Löschziele vorschauen',()=>change({operation:'lab_janitor'}),'danger')));
      if(id==='sessions-lab')await sessions(p.body);
      if(id==='certificates-lab')await certificates(p.body);
      if(id==='wear-lab')await wear(p.body);
      if(id==='history-lab')await history(p.body);
      if(id==='restore-lab')await restore(p.body);
      if(id==='logs-lab')await logs(p.body);
      if(id==='web-lab')await web(p.body);
      if(id==='guardian-lab')await guardian(p.body);
      p.body.append(button('↻ Aktualisieren',()=>load(id)));
    }catch(e){p.state.textContent=e.message;}
    finally{pending.delete(id);}
  }
  function chart(rows,existing=null){
    const block=existing||el('div',undefined,'sensor-chart'),canvas=existing?.querySelector('canvas')||el('canvas'),hint=existing?.querySelector('p')||rawEl('p');canvas.width=900;canvas.height=260;canvas.setAttribute('role','img');canvas.setAttribute('aria-label',t('Container-Verlauf: CPU und RAM'));if(!existing)block.append(canvas,hint);
    const context=canvas.getContext('2d');if(!context)return block;
    const values=rows.slice(-240),max=Math.max(100,...values.map(row=>row.cpu||0));context.font='12px system-ui';
    for(let i=0;i<=4;i++){const y=20+i*50;context.strokeStyle='#dbe6e6';context.beginPath();context.moveTo(50,y);context.lineTo(880,y);context.stroke();context.fillStyle='#5b7278';context.fillText(String(Math.round(max*(1-i/4))),3,y+4);}
    for(const [key,color]of [['cpu','#16877c'],['memory_percent','#bb6d2d']]){context.strokeStyle=color;context.lineWidth=2;context.beginPath();values.forEach((row,index)=>{const x=50+index/Math.max(1,values.length-1)*830,y=220-(row[key]||0)/max*200;if(index)context.lineTo(x,y);else context.moveTo(x,y);});context.stroke();}
    const show=index=>{const row=values[index];hint.textContent=row?new Date(row.time*1000).toLocaleTimeString(I18N.locale)+' · CPU '+row.cpu.toFixed(1)+' % · RAM '+row.memory_percent.toFixed(1)+' % · '+row.memory:t('Noch keine Messwerte.');};show(values.length-1);
    canvas.onmousemove=event=>{const rect=canvas.getBoundingClientRect(),x=(event.clientX-rect.left)/rect.width*900;show(Math.max(0,Math.min(values.length-1,Math.round((x-50)/830*(values.length-1)))));};
    if(!existing)block.append(el('p','Türkis: CPU, 100 % pro Kern. Orange: RAM in Prozent des Container-Limits. Maus über die Kurve für Einzelwerte.','hint'));return block;
  }
  let radarView=null,radarBusy=false,radarPaused=false;
  async function radar(body){
    const selected=select('Container',[],selectedContainer),graph=el('div'),health=el('div',undefined,'radar-health'),note=el('p',undefined,'hint'),error=el('p',undefined,'warning-text'),grid=table(['Container','Status','CPU / RAM','Image-Update','Aktionen'],[]),pause=button('Pausieren',()=>{radarPaused=!radarPaused;I18N.bind(pause,radarPaused?'Fortsetzen':'Pausieren');if(!radarPaused)refreshRadar();});
    radarView={body,selected,graph,health,note,error,grid,rows:new Map()};selected.node.onchange=()=>{selectedContainer=selected.node.value;refreshRadar();};
    body.append(fields(selected),pause,el('p','Messwerte werden alle 5 Sekunden abgerufen. Auswahl, Buttons und Scrollposition bleiben erhalten.','hint'),graph,health,note,error,grid);
    await refreshRadar();
  }
  async function refreshRadar(){
    if(radarBusy||!radarView)return;radarBusy=true;const v=radarView;
    try{
      const requested=selectedContainer,data=await read({view:'lab_docker',history_container:requested});if(v!==radarView)return;
      const available=new Set(data.rows.map(r=>r.id));for(const option of [...v.selected.node.options])if(!available.has(option.value))option.remove();
      for(const row of data.rows){let option=[...v.selected.node.options].find(o=>o.value===row.id);if(!option){option=rawEl('option',row.name);option.value=row.id;v.selected.node.append(option);}else option.textContent=row.name;}
      if(!available.has(selectedContainer))selectedContainer=v.selected.node.options[0]?.value||'';v.selected.node.value=selectedContainer;
      const rows=data.history[selectedContainer]||[];if(v.graph.firstElementChild)chart(rows,v.graph.firstElementChild);else v.graph.append(chart(rows));
      v.note.textContent=data.note;v.error.textContent=data.error||'';const usage=new Map(data.stats.map(row=>[row.id,row]));
      for(const [id,entry]of v.rows)if(!available.has(id)){entry.tr.remove();v.rows.delete(id);}
      for(const row of data.rows){
        let entry=v.rows.get(row.id);
        if(!entry){const tr=el('tr'),cells=Array.from({length:5},()=>rawEl('td')),actions=el('div',undefined,'result-actions'),registry=button('Registry vergleichen',()=>change({operation:'lab_registry',container:row.id}));
          actions.append(button('Auto-Heiler konfigurieren',()=>go('automation-advanced')),button('Image-Schwachstellen',()=>window.ServerLotseExpert?.scan(row.id)),registry);cells[4].append(actions);tr.append(...cells);v.grid.querySelector('table').append(tr);entry={tr,cells,registry};v.rows.set(row.id,entry);}
        const resources=usage.get(row.id),update=row.update?(row.update.available?t('Update verfügbar'):t('Gleicher Image-Inhalt'))+' · '+new Date(row.update.time*1000).toLocaleString(I18N.locale):t('Noch nicht geprüft');
        [row.name,row.status,resources?resources.cpu.toFixed(1)+' % / '+resources.memory:t('Noch keine Messwerte.'),update].forEach((value,index)=>{if(entry.cells[index].textContent!==value)entry.cells[index].textContent=value;});entry.registry.disabled=Boolean(row.protected);
      }
      if(selectedContainer){const id=selectedContainer,result=await read({view:'lab_health',container:id});if(id===selectedContainer&&v===radarView)v.health.replaceChildren(table(['Healthcheck','Fehlerfolge','Neustarts','OOM','Gestartet'],[[result.health,result.failing,result.restarts,result.oom?'Ja':'Nein',result.started]]),table(['Healthcheck-Start','Ende','Exitcode'],result.checks.map(row=>[row.Start,row.End,row.ExitCode])));}
      else v.health.replaceChildren(el('p','Keine Container vorhanden.'));
      pages.get('radar-lab').state.textContent=t('Stand: {time}',{time:new Date().toLocaleTimeString(I18N.locale)});
    }catch(e){v.error.textContent=e.message;}finally{radarBusy=false;}
  }
  async function clones(body){
    const data=await read({view:'lab_docker'}),source=select('Quellcontainer',data.rows.filter(row=>!row.protected).map(row=>[row.id,row.name])),name=input('Neuer Containername','meine-kopie'),port=input('Neuer Host-Port (optional)','','number'),bind=input('Bind-IP','127.0.0.1'),readonly=check('Vorhandene Volumes nur lesend teilen');
    body.append(panel('Container klonen',fields(source,name,port,bind,readonly),el('p','Kopiert Konfiguration und Image, keine Daten. Standard: leere neue Volumes und bridge-Netzwerk. Nur ein einzelner TCP-Port kann hier neu zugeordnet werden.','hint'),button('Klon vorschauen',()=>change({operation:'lab_clone',container:source.node.value,name:name.node.value,port:port.node.value||null,bind:bind.node.value,readonly:readonly.node.checked}),'primary')));
    const app=select('App-Vorlage',[['nginx','Nginx'],['wordpress','WordPress + MariaDB'],['nextcloud','Nextcloud + MariaDB']]),project=input('Projektname','meine-app'),directory=folder('Projektbasis','/mnt'),appPort=input('Host-Port','8088','number'),appBind=input('App-Bind-IP','127.0.0.1'),checkOutput=el('div');
    body.append(panel('Neue App aus Vorlage',fields(app,project,directory,appPort,appBind),el('p','Eigener Projektordner mit Compose-Datei, Datenablage und zufälligen Datenbankpasswörtern. Offizielle stabile Image-Kanäle. Keine vorhandene Installation wird übernommen.','hint'),button('Port prüfen',async()=>{const r=await read({view:'lab_ports',port:appPort.node.value,bind:appBind.node.value});checkOutput.replaceChildren(el('p',r.available?'Port ist aktuell frei.':'Port ist belegt oder Bind-IP fehlt.'),pre(r.conflicts));}),checkOutput,button('App-Start vorschauen',()=>change({operation:'lab_template',template:app.node.value,name:project.node.value,directory:directory.node.value,port:appPort.node.value,bind:appBind.node.value}),'primary')));directory.install();
  }
  async function inspector(body){
    const data=await read({view:'lab_docker'}),container=select('Container',data.rows.filter(row=>!row.protected).map(row=>[row.id,row.name])),result=el('div'),key=input('Variablenname'),value=input('Neuer Wert','','password'),remove=check('Variable entfernen');
    const loadEnv=async()=>{const r=await read({view:'lab_environment',container:container.node.value});result.replaceChildren(table(['Variable','Wert'],r.rows.map(row=>[row.key,row.value])),el('p',r.note,'hint'));if(r.compose)result.append(el('p','Compose-Container: schnelle Änderungen erzeugen eine eigene Override-Datei. Diese bei späteren Portainer-/Compose-Updates mitverwenden. Alternativ .env unten bearbeiten.','hint'));};
    body.append(panel('Container-Umgebung',fields(container),button('Maskierte Werte laden',loadEnv),result,fields(key,value,remove),button('Container-Änderung vorschauen',async()=>{try{await change({operation:'lab_env',container:container.node.value,env_updates:{[key.node.value]:remove.node.checked?null:value.node.value}});}finally{value.node.value='';}}),button('Compose neu bereitstellen',()=>change({operation:'lab_compose',container:container.node.value}))));
    const folderInput=folder('.env-Ordner','/mnt'),envResult=el('div'),envKey=input('.env-Variablenname'),envValue=input('.env-Neuer Wert','','password'),envRemove=check('.env-Variable entfernen');
    const filename=()=>folderInput.node.value.replace(/\/$/,'')+'/.env';
    body.append(panel('.env-Datei bearbeiten',fields(folderInput),button('.env maskiert laden',async()=>{const r=await read({view:'lab_dotenv',path:filename()});envResult.replaceChildren(table(['Variable','Wert'],r.rows.map(row=>[row.key,row.value])));}),envResult,fields(envKey,envValue,envRemove),el('p','Datei muss root-geschützt sein. Nur eindeutige einzeilige KEY=VALUE-Einträge; Kommentare bleiben erhalten. Speichern startet noch keinen Container neu.','hint'),button('.env-Änderung vorschauen',async()=>{try{await change({operation:'lab_dotenv',path:filename(),env_updates:{[envKey.node.value]:envRemove.node.checked?null:envValue.node.value}});}finally{envValue.node.value='';}})));folderInput.install();
  }
  async function networkMap(body){
    const data=await read({view:'lab_networks'}),filter=select('Netzwerk',[['',t('Alle Netzwerke')],...data.networks.map(row=>[row.name,row.name+' · '+row.driver])]),map=el('div');body.append(fields(filter),el('p',data.note,'hint'),map);
    function draw(){
      const nets=data.networks.filter(row=>!filter.node.value||row.name===filter.node.value),containers=data.containers.filter(row=>!filter.node.value||row.networks.includes(filter.node.value));
      const shownNets=nets.slice(0,30),shownContainers=containers.slice(0,40),canvas=el('canvas'),height=Math.max(250,Math.max(shownNets.length,shownContainers.length)*42);canvas.width=1000;canvas.height=height;canvas.setAttribute('role','img');canvas.setAttribute('aria-label',t('Docker-Netzwerkmitgliedschaften'));const context=canvas.getContext('2d');
      if(context){context.font='14px system-ui';for(let i=0;i<shownContainers.length;i++){const row=shownContainers[i],y=30+i*42;for(const net of row.networks){const index=shownNets.findIndex(n=>n.name===net);if(index>=0){context.strokeStyle='#9fc6c3';context.beginPath();context.moveTo(310,30+index*42);context.lineTo(650,y);context.stroke();}}context.fillStyle='#153b40';context.fillRect(650,y-13,330,28);context.fillStyle='#fff';context.fillText(row.name.slice(0,40),660,y+6);}shownNets.forEach((row,index)=>{const y=30+index*42;context.fillStyle='#137f75';context.fillRect(10,y-13,300,28);context.fillStyle='#fff';context.fillText(row.name.slice(0,34)+' · '+row.driver,20,y+6);});canvas.onclick=event=>{const rect=canvas.getBoundingClientRect(),x=(event.clientX-rect.left)/rect.width*1000,y=(event.clientY-rect.top)/rect.height*height,index=Math.round((y-30)/42);if(x<310&&shownNets[index]){filter.node.value=shownNets[index].name;draw();}};}
      map.replaceChildren(canvas,el('p','Netzwerk anklicken zum Filtern. Karte auf 30 Netzwerke und 40 Container begrenzt; Tabelle zeigt die vollständige Auswahl.','hint'),table(['Container','Netzwerke'],containers.map(row=>[row.name,row.networks.join(', ')])));
    }filter.node.onchange=draw;draw();
  }
  async function sessions(body){
    const data=await read({view:'lab_sessions'});body.append(el('p',data.note,'hint'),table(['Sitzung','Benutzer','Gegenstelle','TTY','Aktion'],data.rows.map(row=>[row.Id,row.Name,row.RemoteHost||t('Lokal'),row.TTY,button('Sitzung beenden',()=>change({operation:'lab_session_end',session:row.Id}),'danger')])));
    body.append(el('h2','ServerLotse-Terminals'),table(['Sitzung','Alter (Sekunden)','Aktion'],data.terminals.map(row=>[row.id.slice(0,8),row.age,button('Terminal beenden',()=>change({operation:'lab_session_end',kind:'terminal',session:row.id}),'danger')])));
  }
  async function certificates(body){const data=await read({view:'lab_certificates'});body.append(el('p',data.note,'hint'),table(['Zertifikat','Resttage','Gültig bis','Datei'],data.rows.map(row=>[row.subject,rawEl('strong',row.days+' '+t('Tage'),row.days<=14?'warning-text':''),new Date(row.expires*1000).toLocaleString(I18N.locale),row.path])),button('Ablaufwarnungen einrichten',()=>open('guardian-lab')));}
  async function wear(body){const data=await read({view:'lab_disks'});body.append(el('p',data.note,'hint'),table(['Datenträger','Modell','Geschätzte Endurance übrig','SMART','Quelle'],data.rows.map(row=>[row.path,row.model,row.remaining===null?t('Unbekannt'):row.remaining+' %',row.passed===undefined?t('Unbekannt'):row.passed?t('OK'):t('Warnung'),row.source])));}
  async function history(body){
    const data=await read({view:'lab_history'});body.append(el('p',data.note,'hint'));if(data.warning)body.append(el('p',data.warning,'warning-text'));
    body.append(el('h2','CPU-Spitzen'),table(['Zeit','CPU','Top 5 Prozesse'],[...data.peaks].reverse().map(row=>[new Date(row.time*1000).toLocaleString(I18N.locale),row.cpu+' %',(row.processes||[]).map(p=>p.name+' · PID '+p.pid+' · '+p.cpu.toFixed(1)+' %').join('\n')])));
    body.append(el('h2','OOM-Ereignisse'),table(['Zeit','Quelle','Meldung'],[...data.oom].reverse().map(row=>[new Date(row.time*1000).toLocaleString(I18N.locale),row.source,row.text])));
  }
  async function restore(body){
    const data=await read({view:'lab_backup_options'}),backup=select('Sicherungsplan',data.backups.map(row=>[row.id,row.name])),archive=select('Archiv',[]),image=select('Lokales Datenbank-Image',data.images.map(row=>[row.id,(row.tags||[]).join(', ')+' · '+row.id.slice(7,19)]));
    const populate=()=>{archive.node.replaceChildren();for(const row of data.backups.find(row=>row.id===backup.node.value)?.archives||[]){const option=rawEl('option',row.name);option.value=row.name;archive.node.append(option);}};backup.node.onchange=populate;populate();
    body.append(panel('SQL-Wiederherstellung testen',fields(backup,archive,image),el('p','Nur vorhandene offizielle MySQL-/MariaDB-Images. Bis 512 MiB SQL, 1 GiB RAM und begrenzte RAM-Datenablage. Der Testcontainer hat weder Netzwerk noch Host-Mounts. Dein laufender Datenbankcontainer wird nicht verwendet.','hint'),button('Testrestore vorschauen',()=>change({operation:'lab_restore_test',id:backup.node.value,archive:archive.node.value,image:image.node.value}),'primary')));
    if(!data.backups.length||!data.images.length)body.append(el('p','Zuerst ein Backup mit SQL-Export und ein passendes lokales Datenbank-Image bereitstellen.'));
  }
  async function logs(body){const data=await read({view:'lab_logs'});if(!data.available)body.append(button('Logrotate installieren',()=>change({operation:'tool_install',package:'logrotate'})));const config=select('Vorhandene Rotationsrichtlinie',data.configs.map(path=>[path,path])),output=table(['Logdatei','Größe'],data.rows.map(row=>[row.path,humanBytes(row.bytes)]));output.classList.add('console-table');body.append(el('p',data.note,'hint'),output,panel('Vorzeitig rotieren',fields(config),button('Rotation vorschauen',()=>change({operation:'lab_rotate',path:config.node.value}))),button('Größenwächter einrichten',()=>open('guardian-lab')));}
  async function web(body){
    const data=await read({view:'lab_guardian'}),url=input('Webadresse','https://example.com'),expected=input('Erwarteter HTTP-Status','200','number');
    body.append(panel('HTTP-Erreichbarkeit',fields(url,expected),button('HTTP-Test vorschauen',()=>change({operation:'lab_http',url:url.node.value,expected:expected.node.value})),table(['Webadresse','Status','Erwartet','Zeit (ms)'],data.http.map(row=>[row.url,row.status,row.expected,row.milliseconds]))));
    const driver=select('Speedtest-Anbieter',[['community','Debian speedtest-cli'],['ookla','Ookla CLI']]),consent=check('Bedingungen und Übertragung von IP-/Netzwerkdaten an Testanbieter akzeptieren'),terms=el('a','Speedtest-Bedingungen lesen');terms.href='https://www.speedtest.net/about/terms';terms.target='_blank';terms.rel='noopener noreferrer';
    const block=panel('Netzwerk-Speedtest',fields(driver,consent),el('p','Verbraucht Bandbreite und übermittelt Netzwerkdaten an den gewählten Testanbieter. Community-CLI kann abhängig vom Anbieter scheitern; es werden keine Messergebnisse erfunden.','hint'),terms,button('Speedtest vorschauen',()=>change({operation:'lab_speedtest',driver:driver.node.value,consent:consent.node.checked})),table(['Zeit','Download (Mbit/s)','Upload (Mbit/s)','Ping (ms)'],[...data.speedtests].reverse().map(row=>[new Date(row.time*1000).toLocaleString(I18N.locale),row.download_mbps.toFixed(1),row.upload_mbps.toFixed(1),Number(row.ping).toFixed(1)])));
    if(!data.tools['speedtest-cli'])block.append(button('Debian-Speedtest installieren',()=>change({operation:'tool_install',package:'speedtest-cli'})));
    block.append(button('Zeitplan einrichten',()=>open('guardian-lab')));body.append(block);
  }
  async function guardian(body){
    const data=await read({view:'lab_guardian'}),cfg=data.settings,enabled=check('Wächter aktivieren',cfg.enabled),fim=check('Dateiänderungen melden',cfg.fim),cert=check('Zertifikate ab 14 Resttagen melden',cfg.certificates),http=check('HTTP-Status überwachen',cfg.http),oom=check('OOM-Ereignisse melden',cfg.oom),rotation=check('Große Logs automatisch nach Richtlinie rotieren',cfg.logrotate),speed=check('Speedtest-Zeitplan aktivieren',cfg.speedtest),speedConsent=check('Bedingungen und Übertragung von IP-/Netzwerkdaten an Testanbieter akzeptieren',cfg.speedtest_consent),driver=select('Speedtest-Anbieter',[['community','Debian speedtest-cli'],['ookla','Ookla CLI']],cfg.speedtest_driver),hours=input('Speedtest alle … Stunden',cfg.speedtest_hours,'number'),threshold=input('Log-Grenze (MiB)',cfg.log_megabytes,'number'),peak=input('CPU-Spitze ab (%)',cfg.peak_cpu,'number'),paths=input('FIM-Pfade unter /etc, eine Zeile je Pfad',cfg.fim_paths.join('\n'),'textarea'),targets=input('HTTP-Ziele: Status und URL je Zeile',cfg.http_targets.map(row=>row.expected+' '+row.url).join('\n'),'textarea'),configs=input('Logrotate-Dateien, eine Zeile je Pfad',cfg.rotation_configs.map(row=>row.path).join('\n'),'textarea');
    const certificateDirs=input('Zusätzliche Zertifikatsordner, eine Zeile je Ordner',(cfg.certificate_dirs||[]).join('\n'),'textarea');
    if(data.last_error?.message)body.append(panel('Letzte Prüfmeldung',rawEl('p',data.last_error.message,'warning-text')));
    body.append(panel('Ausdrücklich aktivierbare Wächter',el('p','Benachrichtigungen nutzen das vorhandene Ziel unter Automatik und Meldungen. Ohne Ziel funktionieren lokale Befunde; Versand meldet einen Fehler. FIM erkennt Abweichungen, nicht deren Absicht.','hint'),fields(enabled,fim,cert,http,oom,rotation,speed,speedConsent,driver,hours,threshold,peak),fields(paths,targets,configs,certificateDirs),button('Wächter-Einstellungen vorschauen',()=>{
      const lines=node=>node.value.split('\n').map(s=>s.trim()).filter(Boolean);
      const checks=lines(targets.node).map(line=>{const match=line.match(/^(\d{3})\s+(https?:\/\/\S+)$/);if(!match)throw Error(t('HTTP-Ziele als 200 https://example.com angeben.'));return {expected:Number(match[1]),url:match[2]};});
      return change({operation:'lab_settings',settings:{enabled:enabled.node.checked,fim:fim.node.checked,certificates:cert.node.checked,http:http.node.checked,oom:oom.node.checked,logrotate:rotation.node.checked,speedtest:speed.node.checked,speedtest_consent:speedConsent.node.checked,speedtest_driver:driver.node.value,speedtest_hours:hours.node.value,log_megabytes:threshold.node.value,peak_cpu:peak.node.value,fim_paths:lines(paths.node),certificate_dirs:lines(certificateDirs.node),http_targets:checks,rotation_configs:lines(configs.node)}});
    },'primary')));
    body.append(panel('Datei-Vergleichsbasis',el('p',data.baseline?'FIM-Vergleichsbasis vorhanden.':'Noch keine FIM-Vergleichsbasis vorhanden.'),button('Aktuellen Dateistand als Basis vorschauen',()=>change({operation:'lab_baseline'})),table(['Datei','Abweichung'],data.fim.map(row=>[row.path,row.change])),button('Benachrichtigungsziel öffnen',()=>go('automation-advanced'))));
    for(const tool of ['logrotate','openssl'])if(!data.tools[tool])body.append(button(tool+' '+t('installieren'),()=>change({operation:'tool_install',package:tool})));
  }
  document.addEventListener('admin-task-started',event=>{
    if(!event.detail.operation.startsWith('lab_'))return;const p=pages.get(lastPreviewPage);if(!p)return;
    p.output.replaceChildren(panel('Ergebnis',el('p','Aufgabe läuft …')));
    (async()=>{for(let i=0;i<1200;i++){await new Promise(resolve=>setTimeout(resolve,2000));try{const job=await read({view:'audit_detail',id:event.detail.id});if(['queued','running'].includes(job.status))continue;let result=job.result;try{result=JSON.parse(result);}catch{}p.output.replaceChildren(panel(job.status==='done'?'Abgeschlossen':'Fehlgeschlagen',pre(result)));return;}catch(e){p.output.replaceChildren(el('p',e.message));return;}}})();
  });
  // Surface existing tools rather than duplicate their implementation.
  document.getElementById('clean-advanced')?.append(button('Erweiterten Janitor öffnen',()=>open('janitor-lab')));
  const dashboard=panel('Zertifikate und SSD-Zustand',el('p','Zuletzt geprüfte lokale Werte. Öffnen aktualisiert die jeweilige Diagnose.','hint'),button('Zertifikate prüfen',()=>open('certificates-lab')),button('SSD-Verschleiß prüfen',()=>open('wear-lab'))),summary=el('div');dashboard.append(summary);$('overview').querySelector('.explanation').before(dashboard);
  async function refreshSummary(){try{const data=await read({view:'lab_summary'});summary.replaceChildren(table(['Zertifikat','Resttage'],data.certificates.map(row=>[row.subject,row.days])),table(['Datenträger','Geschätzte Endurance übrig'],data.disks.map(row=>[row.path,row.remaining===null?t('Unbekannt'):row.remaining+' %'])));}catch{}}
  refreshSummary();
  setInterval(()=>{if(!$('overview').hidden)refreshSummary();},60000);
  setInterval(()=>{if(!document.hidden&&!radarPaused&&!pages.get('radar-lab').section.hidden)refreshRadar();},5000);
  document.addEventListener('languagechange',()=>{for(const [id,p]of pages)if(!p.section.hidden)load(id);refreshSummary();});
})();
