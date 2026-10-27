const folderCache=new Map(),folderRefreshers=[];
async function folderListing(view,path){
  const key=view+'|'+path,existing=folderCache.get(key);
  if(existing&&Date.now()-existing.time<15000)return existing.promise;
  const promise=api('folders?view='+encodeURIComponent(view)+'&path='+encodeURIComponent(path));
  folderCache.set(key,{time:Date.now(),promise});
  try{return await promise;}catch(error){folderCache.delete(key);throw error;}
}
function installFolderPicker(inputId,viewId){
  const input=$(inputId),view=$(viewId);if(!input||!view)return;
  const label=input.closest('label'),labelText=I18N.original(label.firstChild.textContent.trim());input.type='hidden';
  const trigger=el('button',undefined,'server-folder-button'),caption=rawEl('span'),symbol=rawEl('span'),arrow=rawEl('span',undefined,'folder-arrow');trigger.type='button';trigger.id=inputId+'-select';trigger.setAttribute('aria-haspopup','dialog');symbol.append(ServerLotseIcons.icon('folder'));arrow.append(ServerLotseIcons.icon('chevron'));trigger.append(symbol,caption,arrow);
  const errorText=el('small',undefined,'folder-select-error');errorText.id=inputId+'-error';errorText.setAttribute('role','status');trigger.setAttribute('aria-describedby',errorText.id);input.after(trigger,errorText);
  const dialog=el('dialog',undefined,'admin-dialog folder-dialog'),heading=el('h2','Ordner auf dem Server auswählen'),subtitle=el('p','Öffne einen Ordner oder gib den vollständigen Pfad ein.','hint'),crumbs=el('div',undefined,'folder-breadcrumbs'),pathLabel=el('label','Pfad direkt eingeben'),pathInput=el('input'),filterLabel=el('label','Ordner filtern'),filter=el('input'),list=el('div',undefined,'folder-dialog-list'),status=el('p',undefined,'hint');
  dialog.setAttribute('aria-labelledby',inputId+'-dialog-title');heading.id=inputId+'-dialog-title';pathInput.autocomplete='off';filter.autocomplete='off';pathLabel.append(pathInput);filterLabel.append(filter);
  const actions=el('div',undefined,'result-actions'),cancel=el('button','Abbrechen','secondary'),choose=el('button','Diesen Ordner verwenden','primary'),open=el('button','Pfad öffnen','secondary'),refresh=el('button','↻ Aktualisieren','secondary');
  for(const b of [cancel,choose,open,refresh])b.type='button';actions.append(cancel,choose);
  const pathRow=el('div',undefined,'folder-path-row');pathRow.append(pathLabel,open,refresh);dialog.append(heading,subtitle,crumbs,pathRow,filterLabel,list,status,actions);document.body.append(dialog);
  let sequence=0,current='/',names=[],valid=false;
  function sync(){caption.textContent=input.value||t('Ordner auswählen …');trigger.setAttribute('aria-label',t(labelText)+': '+(input.value||t('Ordner auswählen …')));}
  function breadcrumbs(){crumbs.replaceChildren();const parts=current.split('/').filter(Boolean);const add=(text,path)=>{const b=rawEl('button',text);b.type='button';b.onclick=()=>load(path);crumbs.append(b);};add('/','/');crumbs.firstChild.prepend(ServerLotseIcons.icon('home'));parts.forEach((part,index)=>{crumbs.append(rawEl('span','/'));add(part,'/'+parts.slice(0,index+1).join('/'));});}
  function render(){list.replaceChildren();const needle=filter.value.toLocaleLowerCase(),visible=names.filter(n=>n.toLocaleLowerCase().includes(needle));for(const name of visible){const b=rawEl('button',undefined,'folder-directory');b.type='button';const symbol=rawEl('span',undefined,'folder-directory-icon'),next=rawEl('span',undefined,'folder-directory-next');symbol.append(ServerLotseIcons.icon('folder'));next.append(ServerLotseIcons.icon('chevron'));b.append(symbol,rawEl('span',name),next);b.onclick=()=>{filter.value='';return load(current.replace(/\/$/,'')+'/'+name);};list.append(b);}if(!visible.length)list.append(el('p',names.length?'Keine passenden Ordner.':'Keine Unterordner vorhanden.','hint'));}
  async function load(path=current){
    sync();if(!dialog.open)return;const request=++sequence;current=path||'/';pathInput.value=current;breadcrumbs();valid=false;choose.disabled=true;list.replaceChildren();status.textContent=t('Ordner werden geladen …');
    try{const d=await folderListing(view.value,current);if(request!==sequence||!dialog.open)return;names=d.folders;current=d.path;valid=true;choose.disabled=false;status.textContent=d.errors||d.truncated?t('Die Liste ist möglicherweise unvollständig. {errors} Lesefehler.',{errors:d.errors}):t('Wähle einen Unterordner oder verwende den aktuellen Ordner.');render();}
    catch(error){if(request===sequence){status.textContent=error.message;names=[];valid=false;}}
  }
  trigger.onclick=()=>{filter.value='';errorText.textContent='';dialog.showModal();load(input.value||'/');pathInput.focus();};
  cancel.onclick=()=>dialog.close();choose.onclick=()=>{if(!valid)return;input.value=current;input.dispatchEvent(new Event('input',{bubbles:true}));dialog.close();trigger.focus();};open.onclick=()=>{filter.value='';load(pathInput.value.trim());};refresh.onclick=()=>{folderCache.delete(view.value+'|'+current);load(current);};pathInput.onkeydown=e=>{if(e.key==='Enter'){e.preventDefault();open.click();}};filter.oninput=render;
  dialog.addEventListener('close',()=>{sequence++;});input.addEventListener('input',()=>{sync();if(dialog.open)load(input.value||'/');});view.addEventListener('change',()=>{input.value='/';sync();if(dialog.open)load('/');});
  input.form?.addEventListener('submit',event=>{if(!input.value){event.preventDefault();event.stopImmediatePropagation();trigger.click();}},true);
  folderRefreshers.push(sync);sync();
}
installFolderPicker('path','view');installFolderPicker('source','source-view');installFolderPicker('target','target-view');
for(const tool of tools.filter(tool=>tool.folder))installFolderPicker(tool.id+'-path',tool.id+'-view');
const priorOverviewForFolders=overview;overview=async function(){await priorOverviewForFolders();folderRefreshers.forEach(refresh=>refresh());};
document.addEventListener('languagechange',()=>folderRefreshers.forEach(refresh=>refresh()));
const oldHiddenClick=$('hidden').onclick;$('hidden').onclick=()=>{oldHiddenClick();$('path').dispatchEvent(new Event('input'));};
const folderResultBox=resultBox;resultBox=function(data,type){if(type==='browse'){if(data.path)$('browse-path').value=data.path;$('browse-path').dispatchEvent(new Event('input'));}return folderResultBox(data,type);};
