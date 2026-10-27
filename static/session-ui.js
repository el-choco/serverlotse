/* The only remembered credential is an HttpOnly session cookie issued by the server. */
const rememberLabel = el('label', undefined, 'remember-session');
const remember = document.createElement('input');
remember.type = 'checkbox';
remember.checked = true;
remember.id = 'remember-session';
rememberLabel.append(remember, el('span','Angemeldet bleiben (30 Tage)'));
$('access').append(rememberLabel);
const loginHelp = $('access').querySelector('small');
I18N.bind(loginHelp,'Einmal mit dem Schlüssel aus deiner .env anmelden. Danach meldet dich dieser Browser automatisch an.');
async function signIn() {
  const button = $('connect');
  button.disabled = true;
  message(t('Anmeldung läuft …'));
  try {
    await api('login',{token:$('token').value,remember:remember.checked});
    $('token').value='';
    token='';
    await overview();
    document.dispatchEvent(new Event('serverlotse:authenticated'));
  } catch(error) {
    $('token').value='';
    message(error.message);
  } finally {
    button.disabled=false;
  }
}
$('connect').onclick=signIn;
$('token').addEventListener('keydown',event=>{
  if(event.key==='Enter'){event.preventDefault();signIn();}
});
disconnect.onclick=async()=>{
  try{await window.ServerLotseTerminal?.stop();await api('logout',{});token='';location.reload();}
  catch(error){message(error.message);}
};
const languageLabel=el('label',undefined,'language-switch');
languageLabel.setAttribute('aria-label','Language / Idioma / Sprache');
const languageSelect=el('select');
languageSelect.id='language-select';
languageSelect.setAttribute('aria-label','Language / Idioma / Sprache');
languageSelect.dataset.noTranslate='';
for(const [value,name]of [['de','DE · Deutsch'],['es','ES · Español'],['en','EN · English']]){
  const option=rawEl('option',name);option.value=value;languageSelect.append(option);
}
languageSelect.value=I18N.lang;
languageSelect.onchange=()=>I18N.change(languageSelect.value);
languageLabel.append(languageSelect);
document.querySelector('header').insertBefore(languageLabel,disconnect);
document.querySelector('.sidebar-bottom small').textContent='VERSION 0.3 · WERKZEUGKISTE';
document.addEventListener('languagechange',()=>{
  overview();
  if(!$('history').hidden)loadHistory();
});
I18N.ready.catch(()=>message('Language catalog could not be loaded. Please refresh the page.'));
