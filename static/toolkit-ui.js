document.querySelector('header p')?.remove();
document.querySelector('.section-heading')?.remove();
const tools = [
  {id:'browse',icon:'▤',name:'Dateibrowser',title:'Deine Dateien. Ohne Umwege.',description:'Ordner öffnen, Dateigrößen, Eigentümer und Rechte ansehen.',folder:true},
  {id:'largest',icon:'◱',name:'Große Dateien',title:'Die größten Platzverbraucher.',description:'Die 200 größten Dateien im gewählten Ordner finden.',folder:true},
  {id:'types',icon:'▧',name:'Dateitypen',title:'Was belegt den Platz?',description:'Speicher nach Dateiendung aufschlüsseln: Videos, Archive, Bilder und mehr.',folder:true},
  {id:'search',icon:'⌕',name:'Dateisuche',title:'Finde, was du suchst.',description:'Nach Dateinamen suchen. * steht für beliebig viele Zeichen, ? für ein Zeichen.',folder:true,extra:[['pattern','Suchmuster','*.pdf']]},
  {id:'duplicates',icon:'▣',name:'Duplikate',title:'Doppelt gespeichert?',description:'Inhaltsgleiche Dateien über SHA-256 erkennen. Es wird nichts gelöscht.',folder:true},
  {id:'system',icon:'◎',name:'Systemdiagnose',title:'Ein Blick unter die Haube.',description:'Laufzeit, Last, Arbeitsspeicher, Kernel und Hinweise zur Belegung.'},
  {id:'mounts',icon:'◈',name:'Datenträger-Zuordnung',title:'Welche Platte steckt dahinter?',description:'Dateisystemkennungen in Host- und Systemansicht vergleichen.'},
  {id:'docker',icon:'⬡',name:'Docker',title:'Deine Container im Überblick.',description:'Status, Images, Einbindungen und Logs. Benötigt das optionale Docker-Lesemodul.'},
  {id:'log',icon:'≋',name:'Log-Helfer',title:'Aus Meldungen werden Hinweise.',description:'Protokolltext einfügen: typische Fehler werden gruppiert und verständlich erklärt.',text:true},
  {id:'copy_plan',icon:'↗',name:'Dateien retten',title:'Eine geprüfte Kopie anlegen.',description:'Zuerst Vorschau, dann bestätigen. Kopien landen in einem neuen Rettungsordner; Originale bleiben erhalten.',folder:true},
  {id:'checklist',icon:'☑',name:'Prüfleitfäden',title:'Der nächste sinnvolle Schritt.',description:'Geführte Hinweise für vollen Speicher, fehlende Dateien und Containerprobleme.'}
];
const toolMap = Object.fromEntries(tools.map(t=>[t.id,t]));
let currentSettings = {}, activeJob = null;
function field(label, tag, id, value) {
  const wrap=el('label',label),input=el(tag); input.id=id;
  if(tag==='select') for(const [v,l] of [['host','Host · sichtbare Dateien'],['system','Systemplatte · verdeckte Daten']]) {const o=el('option',l);o.value=v;input.append(o);}
  else {input.value=value||'';input.required=true;}
  wrap.append(input);return wrap;
}
for(const tool of tools){
  const nav=el('button',tool.icon+' '+tool.name);nav.dataset.page=tool.id;nav.onclick=()=>page(tool.id);document.querySelector('nav').append(nav);
  const section=el('section',undefined,'page');section.id=tool.id;section.hidden=true;
  section.append(el('span',tool.name.toUpperCase(),'eyebrow'),el('h1',tool.title),el('p',tool.description));
  const form=el('form',undefined,'panel');form.id=tool.id+'-form';const fields=el('div',undefined,'fields');
  if(tool.folder){fields.append(field('Ansicht','select',tool.id+'-view'),field('Ordnerpfad','input',tool.id+'-path','/mnt'));}
  if(tool.extra)for(const [key,label,value]of tool.extra)fields.append(field(label,'input',tool.id+'-'+key,value));
  form.append(fields);
  if(tool.text){const area=field('Protokolltext (maximal 500.000 Zeichen)','textarea','log-text','');area.lastChild.maxLength=500000;area.lastChild.rows=12;form.append(area);form.append(el('p','Bitte bekannte Passwörter und Tokens vor dem Einfügen entfernen. Die Analyse läuft auf deiner ServerLotse-Instanz.','hint'));}
  const button=el('button',tool.id==='copy_plan'?'Kopiervorschau erstellen →':tool.id==='docker'?'Container laden →':'Prüfung starten →','primary');button.type='submit';form.append(button);
  form.onsubmit=e=>{e.preventDefault();const data={action:tool.id};if(tool.folder){data.view=$(tool.id+'-view').value;data.path=$(tool.id+'-path').value;}if(tool.extra)for(const [key]of tool.extra)data[key]=$(tool.id+'-'+key).value;if(tool.text)data.text=$('log-text').value;run(data,$(tool.id+'-result'),tool.id);};
  section.append(form);const result=el('div');result.id=tool.id+'-result';section.append(result);document.querySelector('footer').before(section);
  const card=el('button',undefined,'tool');card.append(el('span',tool.icon,'tool-icon'),el('h3',tool.name),el('p',tool.description),el('strong','Werkzeug öffnen →'));card.onclick=()=>page(tool.id);document.querySelector('.tools').append(card);
}
const historyPage=el('section',undefined,'page');historyPage.id='history';historyPage.hidden=true;historyPage.append(el('span','AUFGABENVERLAUF','eyebrow'),el('h1','Was wurde geprüft?'),el('p','Aufgaben bleiben beim Wechsel der Seite erhalten. Nach einem Containerneustart ist der Verlauf leer.'));const historyButton=el('button','↻ Verlauf aktualisieren','secondary');historyButton.onclick=loadHistory;historyPage.append(historyButton);const historyResult=el('div');historyResult.id='history-result';historyPage.append(historyResult);document.querySelector('footer').before(historyPage);const historyNav=el('button','◷ Verlauf');historyNav.dataset.page='history';historyNav.onclick=()=>{page('history');loadHistory();};document.querySelector('nav').append(historyNav);
document.querySelector('.explanation h3').textContent='Deine Werkzeugkiste wächst mit.';
document.querySelector('.explanation p').textContent='Analyse, Suche, Vergleich und Diagnose an einem Ort. Host-Dateien sind schreibgeschützt. Optionale Rettungskopien brauchen eine ausdrückliche Bestätigung.';
function download(data,format){let text,mime;if(format==='csv'){const rows=data.rows||[],keys=[...new Set(rows.flatMap(Object.keys))];const quote=value=>'"'+String(value??'').replace(/^[=+@\-]/,"'$&").replaceAll('"','""')+'"';text='\uFEFF'+[keys.map(quote).join(';'),...rows.map(r=>keys.map(k=>quote(r[k])).join(';'))].join('\r\n');mime='text/csv;charset=utf-8';}else{text=JSON.stringify(data,null,2);mime='application/json';}const url=URL.createObjectURL(new Blob([text],{type:mime}));const a=el('a');a.href=url;a.download='serverlotse-ergebnis.'+format;a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);}
const basicResultBox=resultBox;
resultBox=function(data,type){
  if(type==='scan'||type==='compare'){const box=basicResultBox(data,type);const csv=el('button','CSV herunterladen','secondary');csv.onclick=()=>download(data,'csv');box.append(csv);return box;}
  const box=el('div',undefined,'result');box.append(el('h2',toolMap[type]?.name||'Ergebnis'));
  if(data.files!==undefined)box.append(el('p',`${data.files} Dateien · ${data.errors||0} Lesefehler · ${data.skipped||0} übersprungene Einträge`));
  if(data.errors||data.skipped)box.append(el('p','Ergebnis möglicherweise unvollständig. Übersprungene Einträge und Lesefehler vor weiteren Schritten prüfen.','warning-text'));
  for(const finding of data.findings||[])box.append(el('div',finding,'finding'));
  if(data.text){const pre=el('pre',data.text);box.append(pre);const analyze=el('button','Diese Logs auswerten','secondary');analyze.onclick=()=>{page('log');$('log-text').value=data.text;run({action:'log',text:data.text},$('log-result'),'log');};box.append(analyze);}
  const rows=data.rows||[];
  if(!rows.length&&!data.text)box.append(el('p','Keine Einträge gefunden. Hinweise und Fehlermeldungen unten beachten.'));
  const table=el('table');
  const labels={name:'Name / Pfad',value:'Ergebnis',bytes:'Größe',count:'Anzahl',kind:'Typ',rights:'Rechte',owner:'UID:GID',view:'Ansicht',device:'Dateisystem',image:'Image',mounts:'Einbindungen',evidence:'Letzter passender Eintrag'};
  const keys=[...new Set(rows.flatMap(Object.keys))].filter(k=>k in labels);
  const head=el('tr');keys.forEach(k=>head.append(el('th',labels[k])));if(rows.length)table.append(head);
  for(const row of rows){const tr=el('tr');for(const key of keys){const cell=el('td',key==='bytes'&&row[key]!==undefined?fmt(row[key]):row[key]??'');if(key==='name'&&type==='browse'&&row.kind==='Ordner'){const open=el('button',row.name,'link-button');open.onclick=()=>{const path=$('browse-path').value.replace(/\/$/,'')+'/'+row.name;$('browse-path').value=path;run({action:'browse',path,view:$('browse-view').value},$('browse-result'),'browse');};cell.replaceChildren(open);}if(['name','mounts','evidence'].includes(key)&&!['system','log','checklist','copy_plan','copy_apply'].includes(type))cell.dataset.noTranslate='';tr.append(cell);}if(type==='docker'&&row.id){const cell=el('td'),logs=el('button','Logs','secondary');logs.onclick=()=>run({action:'docker_logs',container:row.id},$('docker-result'),'docker_logs');cell.append(logs);tr.append(cell);}table.append(tr);}const scroll=el('div',undefined,'table-scroll');scroll.append(table);box.append(scroll);
  if(data.truncated)box.append(el('p','Darstellung begrenzt. Bitte einen kleineren Ordner untersuchen.'));
  box.append(el('p',data.note||''));const actions=el('div',undefined,'result-actions');for(const format of ['json','csv']){const button=el('button',format.toUpperCase()+' herunterladen','secondary');button.onclick=()=>download(data,format);actions.append(button);}box.append(actions);
  if(data.plan_id){const label=field('Zum Kopieren KOPIEREN eingeben','input','copy-confirmation');label.lastChild.value='';label.lastChild.autocomplete='off';const confirm=el('button','Geprüfte Kopie anlegen','primary');confirm.onclick=()=>run({action:'copy_apply',plan_id:data.plan_id,confirmation:$('copy-confirmation').value},$('copy_plan-result'),'copy_apply');box.append(label,el('p','Bei Abbruch können Teilkopien im Rettungsordner bleiben. Die Quelle bleibt unverändert.','hint'),confirm);}
  return box;
};
run=async function(data,target,type){if(busy){message('Eine Aufgabe läuft bereits. Du findest sie im Verlauf.');return;}busy=true;message();const pending=el('div',undefined,'pending'),status=el('p','Aufgabe wird gestartet …'),cancel=el('button','Abbrechen','secondary');pending.append(status,cancel);target.replaceChildren(pending);let job;try{job=await api('jobs',data);activeJob=job.id;cancel.onclick=async()=>{try{await api('cancel/'+job.id,{});cancel.disabled=true;status.textContent='Abbruch angefordert …';}catch(e){message(e.message);}};await followJob(job.id,target,type,status);}catch(e){target.replaceChildren(el('div',e.message,'result'));}finally{busy=false;activeJob=null;}};
async function followJob(id,target,type,status){while(true){await new Promise(r=>setTimeout(r,1000));const job=await api('jobs/'+id);if(status)status.textContent=job.progress||'Prüfung läuft …';if(job.status==='error'||job.status==='cancelled')throw Error(job.error);if(job.status==='done'){target.replaceChildren(resultBox(job.result,type));break;}}}
async function loadHistory(){
  try{
    const data=await api('jobs'),box=el('div',undefined,'result');
    box.append(el('p',data.note));
    for(const job of data.rows){
      const row=el('div',undefined,'history-row'),description=el('span');
      description.append(rawEl('span',new Date(job.created*1000).toLocaleString(I18N.locale)+' · '),el('span',toolMap[job.action]?.name||job.action),rawEl('span',' · '),el('span',job.status));
      row.append(description);
      const open=el('button','Anzeigen','secondary');
      open.onclick=async()=>{
        try{
          const state=await api('jobs/'+job.id);
          if(state.status==='done')$('history-result').replaceChildren(resultBox(state.result,state.action));
          else if(state.status==='error'||state.status==='cancelled')message(state.error);
          else{
            const pending=el('div',undefined,'pending'),text=el('p',state.progress||'Läuft'),stop=el('button','Abbrechen','secondary');
            stop.onclick=()=>api('cancel/'+job.id,{}).catch(e=>message(e.message));
            pending.append(text,stop);$('history-result').replaceChildren(pending);
            await followJob(job.id,$('history-result'),job.action,text);
          }
        }catch(e){message(e.message);}
      };
      row.append(open);box.append(row);
    }
    $('history-result').replaceChildren(box);
  }catch(e){message(e.message);}
}
const oldOverview=overview;
overview=async function(){await oldOverview();try{currentSettings=await api('settings');if(!currentSettings.demo)$('mode').textContent='Verbunden · Werkzeugkiste '+currentSettings.version;const copy=$('copy_plan-form').querySelector('button');copy.disabled=!currentSettings.copy;copy.textContent=currentSettings.copy?'Kopiervorschau erstellen →':'Rettungsmodul noch nicht aktiviert';}catch{}};
$('refresh').onclick=overview;$('connect').onclick=()=>{token=$('token').value;$('token').value='';overview();};
const disconnect=el('button','Abmelden','secondary');disconnect.onclick=()=>{token='';location.reload();};document.querySelector('header').append(disconnect);
overview();
