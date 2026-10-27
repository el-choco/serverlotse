const nav=document.querySelector('nav');
const categories=[
  ['Dateiverwaltung',['storage','compare','browse','largest','types','search','duplicates','copy_plan']],
  ['System',['system','mounts','log','checklist']],
  ['Docker',['docker']]
];
for(const [name,pages]of categories){
  const category=el('details',undefined,'nav-category'),summary=el('summary',name);
  category.dataset.pages=pages.join(',');category.append(summary);
  for(const pageId of pages){const button=nav.querySelector('[data-page="'+pageId+'"]');if(button)category.append(button);}
  nav.insertBefore(category,nav.querySelector('[data-page="history"]'));
}
const originalTools=document.querySelector('#overview>.tools');
const cards=[...originalTools.children],cardPages=['storage','storage','compare',...tools.map(tool=>tool.id)];
for(const [name,pages]of categories){
  const group=el('details',undefined,'dashboard-category'),summary=el('summary',name),grid=el('div',undefined,'tools');
  group.append(summary,grid);
  cards.forEach((card,index)=>{if(pages.includes(cardPages[index]))grid.append(card);});
  originalTools.before(group);
}
originalTools.remove();
const oldPage=page;
page=function(name){
  document.querySelectorAll('.nav-category').forEach(category=>{if(category.dataset.pages.split(',').includes(name))category.open=true;});
  oldPage(name);
};
const sidebarBottom=document.querySelector('.sidebar-bottom'),version=sidebarBottom.querySelector('small');
sidebarBottom.replaceChildren(version);I18N.bind(version,'VERSION 0.4 · WERKZEUGKISTE');

const powerPanel=el('section',undefined,'power-panel');
powerPanel.append(el('h2','Server steuern'));
const powerActions=el('div',undefined,'result-actions');
const rebootButton=el('button','Neustart (Reboot)','secondary'),shutdownButton=el('button','Herunterfahren (Shutdown)','danger');
rebootButton.disabled=shutdownButton.disabled=true;
powerActions.append(rebootButton,shutdownButton);
const powerStatus=el('p','Host-Steuerung wird geprüft …','hint');powerStatus.setAttribute('role','status');
powerPanel.append(powerActions,powerStatus);$('disks').after(powerPanel);

const powerDialog=el('dialog',undefined,'power-dialog');
const powerTitle=el('h2'),powerDescription=el('p'),powerHost=rawEl('p',location.hostname,'power-host');
const powerForm=el('form'),confirmationLabel=el('label'),confirmationInput=el('input');
confirmationInput.autocomplete='off';confirmationInput.spellcheck=false;confirmationInput.id='power-confirmation';
const confirmationText=el('span');confirmationLabel.append(confirmationText,confirmationInput);
const modalStatus=el('p');modalStatus.setAttribute('role','status');
const modalActions=el('div',undefined,'result-actions'),cancelPower=el('button','Abbrechen','secondary'),confirmPower=el('button','Bestätigen','danger');
cancelPower.type='button';confirmPower.type='submit';confirmPower.disabled=true;
modalActions.append(cancelPower,confirmPower);powerForm.append(confirmationLabel,modalStatus,modalActions);
powerDialog.append(powerTitle,powerDescription,powerHost,powerForm);powerDialog.setAttribute('aria-labelledby','power-dialog-title');powerTitle.id='power-dialog-title';document.body.append(powerDialog);
let preparedPower=null,powerSending=false,powerSequence=0;
cancelPower.onclick=()=>{powerSequence++;preparedPower=null;powerDialog.close();};
powerDialog.addEventListener('cancel',event=>{if(powerSending)event.preventDefault();else{powerSequence++;preparedPower=null;}});
confirmationInput.oninput=()=>{confirmPower.disabled=!preparedPower||confirmationInput.value!==preparedPower.confirmation;};
async function preparePower(action){
  const request=++powerSequence;
  preparedPower=null;confirmationInput.value='';confirmPower.disabled=true;
  I18N.bind(powerTitle,action==='reboot'?'Neustart bestätigen':'Herunterfahren bestätigen');
  I18N.bind(powerDescription,action==='reboot'?'Alle Dienste werden unterbrochen und der Server wird neu gestartet. Laufende externe Kopiervorgänge vorher beenden.':'Alle Dienste werden beendet und der Server wird ausgeschaltet. Zum erneuten Einschalten benötigst du einen separaten Zugriff.');
  I18N.bind(modalStatus,'Bestätigung wird vorbereitet …');confirmationText.textContent='';powerDialog.showModal();
  try{
    const result=await api('host/prepare',{action});
    if(!powerDialog.open||request!==powerSequence)return;
    preparedPower=result;
    I18N.bind(confirmationText,'Zur Bestätigung {word} eingeben');
    confirmationText.textContent=t('Zur Bestätigung {word} eingeben',{word:result.confirmation});
    modalStatus.textContent=result.demo?t('Demo: Es wird keine Host-Aktion ausgeführt.'):t('Die Bestätigung ist 60 Sekunden gültig.');
    confirmationInput.focus();
  }catch(error){if(request===powerSequence)modalStatus.textContent=error.message;}
}
rebootButton.onclick=()=>preparePower('reboot');shutdownButton.onclick=()=>preparePower('shutdown');
powerForm.onsubmit=async event=>{
  event.preventDefault();if(!preparedPower||powerSending||confirmationInput.value!==preparedPower.confirmation)return;
  powerSending=true;confirmPower.disabled=true;cancelPower.disabled=true;
  try{
    const result=await api('host/execute',{action:preparedPower.action,nonce:preparedPower.nonce,confirmation:confirmationInput.value});
    preparedPower=null;powerDialog.close();powerStatus.textContent=result.note;
    if(result.accepted){rebootButton.disabled=shutdownButton.disabled=true;}
  }catch(error){modalStatus.textContent=error.message;preparedPower=null;}
  finally{powerSending=false;cancelPower.disabled=false;}
};
async function loadHostStatus(){
  rebootButton.disabled=shutdownButton.disabled=true;
  if(!$('access').hidden){I18N.bind(powerStatus,'Für die Host-Steuerung bitte anmelden.');return;}
  try{
    const result=await api('host/status');
    rebootButton.disabled=!result.enabled||!result.reboot;shutdownButton.disabled=!result.enabled||!result.shutdown;
    I18N.bind(powerStatus,result.note||(result.demo?'Demo: Die Host-Steuerung wird nur simuliert.':result.enabled?'Host-Steuerung bereit. Jede Aktion benötigt eine Bestätigung.':'Host-Steuerung ist deaktiviert.'));
  }catch(error){powerStatus.textContent=error.message;}
}
const priorOverviewForPower=overview;
overview=async function(){await priorOverviewForPower();await loadHostStatus();};
overview();
