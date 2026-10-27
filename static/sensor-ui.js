/* Read-only monitoring. No shell, deletion, firewall or process mutations. */
(() => {
  const definitions=[
    ['live-sensors','Live-Monitoring','Monitoring','CPU, RAM, Temperaturen und Netzwerk im Verlauf.'],
    ['process-sensors','Prozesse','Monitoring','Prozesse nach PID, CPU oder RAM sortieren.'],
    ['log-sensors','Live-Logs','Monitoring','Logende automatisch nachführen und Meldungen filtern.'],
    ['ssh-sensors','SSH-Prüfung','Sicherheit','Root-Login, Passwortanmeldung und Schlüsselanmeldung prüfen.'],
    ['firewall-sensors','Firewall-Status','Sicherheit','Bestehende UFW-, iptables- oder nftables-Regeln anzeigen.'],
    ['fail2ban-sensors','fail2ban','Sicherheit','Jails, fehlgeschlagene Anmeldungen und gesperrte IPs anzeigen.'],
    ['unused-sensors','Docker-Speicherprüfung','Docker','Nicht referenzierte Volumes und verwaiste Images finden.'],
    ['console-sensors','Diagnose-Konsole','System','Lesende Diagnosebefehle auswählen und die Ausgabe prüfen.'],
    ['proxy-sensors','Proxy-Vorlagen','Netzwerk','Nginx- und Caddy-Vorlagen erstellen, ohne bestehende Einstellungen zu ändern.']
  ];
  const help={
    'live-sensors':'CPU-Auslastung wird aus zwei Messungen berechnet. RAM nutzt MemAvailable statt nur völlig freiem Speicher. Temperaturen hängen von der Hardware ab. Die Diagramme zeigen maximal eine Stunde seit dem Start des Helfers.',
    'process-sensors':'Ein Prozess ist ein laufendes Programm. Wartend ist meist normal. Mehr als 100 % CPU bedeutet mehrere belegte Kerne. Aktionen für normale Benutzerprozesse benötigen eine Vorschau. Root-, System- und Zugangsprozesse bleiben geschützt. Erzwingen kann ungespeicherte Arbeit verlieren.',
    'log-sensors':'Die Ansicht lädt alle drei Sekunden das letzte Logende neu. Sie folgt auch einer normalen Logrotation. Bei fehlenden Dateien stoppt die Nachführung mit einer Meldung. Geheimnisse können trotz bestmöglicher Maskierung in Logs vorkommen.',
    'ssh-sensors':'sshd -T zeigt effektive Standardwerte. Root-Login und Passwortanmeldung erhöhen die Angriffsfläche. Match-Blöcke können andere Werte festlegen. Diese Prüfung ändert keine SSH-Einstellung und bestätigt nicht deine Anmeldungsmethode.',
    'firewall-sensors':'Eine Firewallregel kann Zugriff erlauben oder blockieren. Reihenfolge und weitere Regeln zählen ebenfalls. Veröffentlichte Docker-Ports können UFW umgehen. Der Blick vom Server ersetzt keinen Test von einem anderen Internetanschluss.',
    'fail2ban-sensors':'fail2ban zählt fehlgeschlagene Zugriffe und sperrt IPs nach den Regeln eines Jails. Eine gesperrte IP beweist keinen Einbruch. Ein leerer Status beweist nicht, dass es keine Angriffe gab.',
    'unused-sensors':'Ein nicht referenziertes Volume kann weiterhin wichtige Daten enthalten. Die Liste ist eine Momentaufnahme, keine Löschfreigabe. Bestehende Nextcloud-, Datenbank- oder Backupdaten zuerst eindeutig zuordnen.',
    'console-sensors':'Die Diagnose-Konsole bietet eine feste Auswahl lesender Befehle. Es gibt keine freie Root-Shell. Ausgaben sind begrenzt und werden bestmöglich von bekannten Zugangsdatenmustern bereinigt.',
    'proxy-sensors':'Die Vorlagen werden nur angezeigt. Caddy kann öffentliche Zertifikate nach deiner manuellen Einrichtung selbst anfordern. Dafür müssen DNS und Portweiterleitungen stimmen. Nginx braucht zusätzlich eine TLS-Einrichtung. Bestehenden Nginx Proxy Manager weiter über seine eigene Oberfläche verwalten.'
  };
  const nav=document.querySelector('nav'),pages=new Map(),statusNodes=new Map(),loaded=new Map();
  function group(name){
    let item=[...nav.querySelectorAll('.nav-category')].find(n=>I18N.original(n.querySelector('summary').textContent)===name);
    if(!item){item=el('details',undefined,'nav-category');item.dataset.pages='';item.append(el('summary',name));nav.insertBefore(item,nav.querySelector('[data-page="history"]'));}
    return item;
  }
  function button(text,callback){const b=el('button',text,'secondary');b.type='button';b.onclick=()=>callback();return b;}
  function select(label,options){const wrap=el('label',label),node=el('select');node.setAttribute('aria-label',t(label));for(const [value,text]of options){const o=el('option',text);o.value=value;node.append(o);}wrap.append(node);return {wrap,node};}
  function input(label,value=''){const wrap=el('label',label),node=el('input');node.setAttribute('aria-label',t(label));node.value=value;wrap.append(node);return {wrap,node};}
  function fields(...items){const block=el('div',undefined,'fields');block.append(...items.map(i=>i.wrap));return block;}
  function table(headers,rows){const wrap=el('div',undefined,'table-scroll'),node=el('table'),head=el('tr');headers.forEach(h=>head.append(el('th',h)));node.append(head);for(const values of rows){const row=el('tr');for(const value of values){const td=rawEl('td');if(value instanceof Node)td.append(value);else td.textContent=String(value??'');row.append(td);}node.append(row);}wrap.append(node);return wrap;}
  const pct=value=>Number.isFinite(value)?new Intl.NumberFormat(I18N.locale,{maximumFractionDigits:1}).format(value)+' %':t('Unbekannt');
  const number=value=>Number.isFinite(value)?new Intl.NumberFormat(I18N.locale,{maximumFractionDigits:1}).format(value):t('Unbekannt');
  const rate=value=>{if(!Number.isFinite(value))return t('Unbekannt');if(Math.abs(value)<1024)return number(value)+' B/s';if(Math.abs(value)<1048576)return number(value/1024)+' KiB/s';return number(value/1048576)+' MiB/s';};
  function bar(label,value){const block=el('div',undefined,'sensor-meter');block.append(rawEl('span',label),rawEl('strong',pct(value)));const line=el('div',undefined,'bar'+(value>=90?' warning':'')),fill=el('span');fill.style.width=(Number.isFinite(value)?Math.max(0,Math.min(100,value)):0)+'%';line.append(fill);block.append(line);return block;}
  function chart(title,rows,key,color,maximum=100,unit='%'){
    const block=el('article',undefined,'sensor-chart'),heading=el('h2',title),canvas=el('canvas');
    canvas.width=720;canvas.height=240;canvas.setAttribute('role','img');canvas.setAttribute('aria-label',t(title));
    const last=rows.at(-1)?.[key];block.append(heading,canvas,rawEl('p',(Number.isFinite(last)?number(last):t('Unbekannt'))+' '+unit));
    const context=canvas.getContext('2d');if(!context)return block;
    const samples=rows.slice(-720),width=canvas.width-72,height=canvas.height-48,x0=52,y0=16;
    const values=samples.map(r=>r[key]).filter(Number.isFinite);if(maximum===null)maximum=Math.max(1,...values)*1.15;
    context.font='12px system-ui';context.lineWidth=1;
    for(let i=0;i<=4;i++){const y=y0+height-i*height/4;context.strokeStyle='#dfe8e8';context.beginPath();context.moveTo(x0,y);context.lineTo(x0+width,y);context.stroke();context.fillStyle='#61777c';context.fillText(number(maximum*i/4),2,y+4);}
    context.strokeStyle=color;context.lineWidth=2.5;context.beginPath();let connected=false;
    const first=samples[0]?.time,lastTime=samples.at(-1)?.time;
    samples.forEach((row,index)=>{const value=row[key];if(!Number.isFinite(value)){connected=false;return;}const x=x0+(lastTime>first?(row.time-first)/(lastTime-first):index/Math.max(1,samples.length-1))*width,y=y0+height-Math.min(maximum,Math.max(0,value))/maximum*height;if(connected)context.lineTo(x,y);else{context.moveTo(x,y);connected=true;}});context.stroke();
    if(samples.length){context.fillStyle='#61777c';context.fillText(new Date(first*1000).toLocaleTimeString(I18N.locale),x0,canvas.height-5);context.fillText(new Date(lastTime*1000).toLocaleTimeString(I18N.locale),canvas.width-96,canvas.height-5);}
    return block;
  }
  for(const [id,name,category,description]of definitions){
    const section=el('section',undefined,'page sensor-page');section.id=id;section.hidden=true;
    section.append(el('span',category,'eyebrow'),el('h1',name),el('p',description));
    const explain=el('details',undefined,'admin-help');explain.append(el('summary','Was bedeutet das?'),el('p',help[id]));
    const status=el('p','Noch nicht geladen.','hint');status.setAttribute('role','status');statusNodes.set(id,status);
    const panel=el('div',undefined,'panel'),body=el('div');pages.set(id,{section,panel,body});
    section.append(explain,status,panel,body);document.querySelector('footer').before(section);
    const item=button(name,()=>open(id));item.classList.remove('secondary');item.dataset.page=id;const parent=group(category);parent.dataset.pages+=','+id;parent.append(item);
    let dashboard=[...$('overview').querySelectorAll('.dashboard-category')].find(n=>I18N.original(n.querySelector('summary').textContent)===category);
    if(!dashboard){dashboard=el('details',undefined,'dashboard-category');dashboard.append(el('summary',category),el('div',undefined,'tools'));$('overview').querySelector('.explanation').before(dashboard);}
    const card=el('button',undefined,'tool');card.append(el('h3',name),el('p',description),el('strong','Werkzeug öffnen →'));card.onclick=()=>open(id);dashboard.querySelector('.tools').append(card);
  }
  const livePause=button('Pausieren',()=>{paused.live=!paused.live;I18N.bind(livePause,paused.live?'Fortsetzen':'Pausieren');});
  pages.get('live-sensors').panel.append(livePause,el('p','Ab 90 % CPU oder RAM erscheint hier eine Browserwarnung. Es wird keine Push-Nachricht versendet.','hint'));
  const processFilter=input('Prozesse filtern'),sort=select('Sortieren nach',[['rss','RAM'],['cpu','CPU'],['pid','PID'],['name','Name']]);
  pages.get('process-sensors').panel.append(fields(processFilter,sort));processFilter.node.oninput=()=>renderProcesses();sort.node.onchange=()=>renderProcesses();
  const log=select('Logquelle',[['journal','Systemjournal'],['syslog','/var/log/syslog'],['auth','/var/log/auth.log'],['nginx','/var/log/nginx/error.log'],['apache','/var/log/apache2/error.log']]),filter=input('Suche im Log'),logPause=button('Pausieren',()=>{paused.logs=!paused.logs;I18N.bind(logPause,paused.logs?'Fortsetzen':'Pausieren');});
  pages.get('log-sensors').panel.append(fields(log,filter),logPause,el('p','Automatische Nachführung alle 3 Sekunden. Logrotation wird beim nächsten Abruf berücksichtigt.','hint'));log.node.onchange=()=>refresh('log-sensors');filter.node.onchange=()=>refresh('log-sensors');
  const jail=select('Jail',[['','Alle Jails']]);pages.get('fail2ban-sensors').panel.append(jail.wrap);jail.node.onchange=()=>refresh('fail2ban-sensors');
  const commands=select('Diagnosebefehl',[['uptime','uptime · Laufzeit und Last'],['disk','df -hT · Speicher'],['inodes','df -i · Dateieinträge'],['memory','free -h · Arbeitsspeicher'],['addresses','ip · Adressen'],['routes','ip route · Routen'],['ports','ss · Offene Ports'],['failed','systemctl · Fehlgeschlagene Dienste'],['boot_errors','journalctl · Bootfehler'],['docker_space','docker system df · Docker-Speicher']]);
  pages.get('console-sensors').panel.append(commands.wrap,button('Befehl ausführen',()=>refresh('console-sensors')));
  const domain=input('Domain','example.com'),upstream=input('Zieldienst','http://127.0.0.1:3000');pages.get('proxy-sensors').panel.append(fields(domain,upstream),button('Vorlagen erstellen',()=>refresh('proxy-sensors')));
  for(const [id]of definitions){if(!['console-sensors','proxy-sensors'].includes(id))pages.get(id).panel.append(button('↻ Aktualisieren',()=>refresh(id)));}
  const paused={live:false,logs:false};let lastProcess=null;const pending=new Set(),lastFetch=new Map();let capability=null,capabilityAt=0;
  function open(id){page(id);refresh(id);}
  function renderProcesses(){
    if(!lastProcess)return;const needle=processFilter.node.value.toLocaleLowerCase();
    const rows=lastProcess.rows.filter(row=>(row.pid+' '+row.name+' '+row.uid).toLocaleLowerCase().includes(needle));
    const key=sort.node.value;rows.sort((a,b)=>key==='name'?a.name.localeCompare(b.name):key==='pid'?a.pid-b.pid:(b[key]??-1)-(a[key]??-1));
    const labels={R:'Läuft',S:'Wartet',D:'Wartet auf Ein-/Ausgabe',T:'Pausiert',t:'Angehalten',Z:'Zombie',I:'Kernel-Leerlauf'};
    pages.get('process-sensors').body.replaceChildren(table(['PID','Name','Status','CPU','RAM','UID','Aktionen'],rows.map(row=>{
      const state=el('span',labels[row.state]||'Unbekannt');state.append(rawEl('span',' ('+row.state+')'));const controls=el('div',undefined,'result-actions');
      if(row.uid>=1000&&row.uid<65534&&row.pid>1){for(const [verb,label]of [['term','Beenden'],['stop','Pausieren'],['continue','Fortsetzen'],['kill','Erzwingen']]){const control=el('button',label,verb==='kill'?'danger':'secondary');control.type='button';control.onclick=async()=>{try{await window.ServerLotseAdmin.preview({operation:'process_signal',pid:row.pid,verb});}catch(error){message(error.message);}};controls.append(control);}}
      else controls.append(el('span','Systemprozess geschützt'));
      return [row.pid,row.name,state,pct(row.cpu),row.rss<1073741824?number(row.rss/1048576)+' MiB':fmt(row.rss),row.uid,controls];
    })),el('p',lastProcess.note));
  }
  async function refresh(id){
    if(pending.has(id))return;pending.add(id);lastFetch.set(id,Date.now());const status=statusNodes.get(id),body=pages.get(id).body;
    try{
      if(!capability||Date.now()-capabilityAt>30000){capability=await api('admin/status');capabilityAt=Date.now();}
      if(!capability.enabled)throw Error(capability.note||t('Host-Verwaltung ist nicht erreichbar.'));
      if(!capability.demo&&!capability.sensors)throw Error(t('Host-Helfer nicht bereit. docker compose up -d --build starten und die host-bootstrap-Logs prüfen.'));
      const view={'live-sensors':'sensor_live','process-sensors':'sensor_processes','log-sensors':'sensor_logs','ssh-sensors':'sensor_ssh','firewall-sensors':'sensor_firewall','fail2ban-sensors':'sensor_fail2ban','unused-sensors':'sensor_unused','console-sensors':'sensor_console','proxy-sensors':'sensor_proxy'}[id];
      const data=await api('admin/read',{view,...(id==='log-sensors'?{log:log.node.value,filter:filter.node.value}:{}),...(id==='fail2ban-sensors'?{jail:jail.node.value}:{}),...(id==='console-sensors'?{command:commands.node.value}:{}),...(id==='proxy-sensors'?{domain:domain.node.value,upstream:upstream.node.value}:{})});
      if(pages.get(id).section.hidden)return;
      status.textContent=capability.demo?t('Beispieldaten – keine Verbindung zu deinem Server.'):t('Stand: {time}',{time:new Date().toLocaleTimeString(I18N.locale)});status.classList.remove('warning-text');
      if(id==='live-sensors'){
        const latest=data.latest;if(!latest){body.replaceChildren(el('p',data.error?'Sensoren konnten nicht gelesen werden.':'Die erste Messung wird vorbereitet …'));return;}
        const meters=el('div',undefined,'sensor-grid'),stats=el('article',undefined,'sensor-card');stats.append(el('h2','CPU je Kern'),bar('CPU',latest.cpu));
        Object.entries(latest.cores).forEach(([key,value])=>stats.append(bar(key,value)));
        const memory=el('article',undefined,'sensor-card');memory.append(el('h2','Arbeitsspeicher'),bar('RAM',latest.ram_percent),rawEl('p',fmt(latest.memory.MemTotal-latest.memory.MemAvailable)+' / '+fmt(latest.memory.MemTotal)),bar('Swap',latest.swap_percent));
        const temperatures=el('article',undefined,'sensor-card'),temperatureGrid=el('div',undefined,'temperature-tiles');temperatures.append(el('h2','Temperatursensoren'));if(!latest.temperatures.length)temperatures.append(el('p','Keine Temperatursensoren verfügbar.'));
        for(const value of latest.temperatures){const tile=el('div',undefined,'temperature-tile'),name=/iwl|wifi/i.test(value.name)?'WLAN':/coretemp|k10temp|cpu/i.test(value.name)?'CPU':/nvme/i.test(value.name)?'SSD':value.name;tile.append(rawEl('span',name),rawEl('strong',number(value.celsius)+' °C'),rawEl('small',value.name));temperatureGrid.append(tile);}temperatures.append(temperatureGrid);
        const oldDetails=body.querySelector('.network-virtual'),network=el('article',undefined,'sensor-card network-card'),physical=el('div',undefined,'network-list'),virtual=el('details',undefined,'network-virtual'),virtualList=el('div',undefined,'network-list');network.append(el('h2','Netzwerkdurchsatz'));
        const interfaces=Object.entries(latest.network).sort(([a],[b])=>a.localeCompare(b));let virtualCount=0;
        for(const [name,value]of interfaces){const row=el('div',undefined,'network-interface');row.append(rawEl('strong',name),rawEl('span','↓ '+rate(value.rx),'network-rx'),rawEl('span','↑ '+rate(value.tx),'network-tx'));if(/^(br-|docker|veth|lo$)/.test(name)){virtualList.append(row);virtualCount++;}else physical.append(row);}
        network.append(physical);if(virtualCount){virtual.append(el('summary',t('Virtuelle Schnittstellen ({count})',{count:virtualCount})),virtualList);virtual.open=Boolean(oldDetails?.open);network.append(virtual);}
        meters.append(stats,memory,temperatures,network);const graphs=el('div',undefined,'sensor-grid');
        graphs.append(chart('CPU-Verlauf',data.rows,'cpu','#18897c'),chart('RAM-Verlauf',data.rows,'ram','#dc6969'),chart('Temperaturverlauf',data.rows,'temperature','#a7812c',null,'°C'),chart('Swap-Verlauf',data.rows,'swap','#458dc4'),chart('Netzwerk empfangen',data.rows.map(r=>({...r,rx:Number.isFinite(r.rx)?r.rx/1048576:null})),'rx','#7c6cc4',null,'MiB/s'),chart('Netzwerk gesendet',data.rows.map(r=>({...r,tx:Number.isFinite(r.tx)?r.tx/1048576:null})),'tx','#b76c9c',null,'MiB/s'));
        body.replaceChildren();if(latest.cpu>=90||latest.ram_percent>=90)body.append(el('div','Hohe Auslastung: CPU oder RAM liegt bei mindestens 90 %.','finding'));body.append(meters,graphs,el('p',data.note));
      }else if(id==='process-sensors'){lastProcess=data;renderProcesses();}
      else if(id==='proxy-sensors')body.replaceChildren(el('h2','Caddy'),rawEl('pre',data.caddy),el('h2','Nginx'),rawEl('pre',data.nginx),el('p',data.note));
      else if(id==='ssh-sensors')body.replaceChildren(table(['SSH-Einstellung','Aktueller Wert','Empfehlung','Hinweis'],data.rows.map(row=>[row.name,row.value,row.recommended,el('span',row.attention?'Prüfen':'Entspricht Empfehlung')])),el('p',data.note));
      else if(id==='unused-sensors')body.replaceChildren(el('p',data.note,'warning-text'),rawEl('pre',data.text),el('h2','Nicht referenzierte Volumes'),rawEl('pre',data.volumes.join('\n')||'—'),el('h2','Verwaiste Images'),rawEl('pre',data.images.join('\n')||'—'));
      else{
        if(id==='fail2ban-sensors'&&!jail.node.value){const old=jail.node.value;jail.node.replaceChildren(el('option','Alle Jails'));jail.node.options[0].value='';for(const name of data.jails||[]){const option=rawEl('option',name);option.value=name;jail.node.append(option);}jail.node.value=old;}
        const old=body.querySelector('pre'),scroll=old?.scrollTop||0,atBottom=old?old.scrollTop+old.clientHeight>=old.scrollHeight-8:true;
        const output=rawEl('pre',data.text||''),note=el('p',data.note||'');output.className='sensor-output';body.replaceChildren(output,note);output.scrollTop=atBottom?output.scrollHeight:scroll;
      }
    }catch(error){status.textContent=error.message;status.classList.add('warning-text');lastFetch.set(id,Date.now()+15000);}
    finally{pending.delete(id);}
  }
  setInterval(()=>{
    if(document.hidden)return;
    for(const [id,period]of [['live-sensors',5000],['process-sensors',5000],['log-sensors',3000]]){
      if(pages.get(id).section.hidden||(id==='live-sensors'&&paused.live)||(id==='log-sensors'&&paused.logs))continue;
      if(Date.now()-(lastFetch.get(id)||0)>=period)refresh(id);
    }
  },1000);
  document.addEventListener('languagechange',()=>{for(const [id]of definitions)if(!pages.get(id).section.hidden)refresh(id);});
})();
