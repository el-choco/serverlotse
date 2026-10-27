/* Local xterm.js renderer; short authenticated requests work through existing proxies. */
(() => {
  let current=null,demoTerminal=null,demoObserver=null;
  const rpc=data=>api('terminal',data);
  const b64=bytes=>btoa(String.fromCharCode(...bytes));
  const bytes=text=>Uint8Array.from(atob(text),c=>c.charCodeAt(0));
  function fitTerminal(term,fit){fit.fit();term.resize(Math.max(20,Math.min(400,term.cols)),Math.max(5,Math.min(150,term.rows)));}
  function button(label,fn,kind='secondary'){
    const node=el('button',label,kind);node.type='button';node.onclick=async()=>{try{await fn();}catch(e){message(e.message);}};return node;
  }
  function status(text){if(current)current.status.textContent=t(text);}
  async function stop(){
    const s=current;if(!s)return;
    s.live=false;clearTimeout(s.timer);s.observer.disconnect();
    if(s.id){const id=s.id;s.id=null;try{await rpc({action:'close',id});}catch{}}
    s.term.dispose();s.container.remove();s.close.disabled=true;s.start.disabled=false;
    status('Terminalsitzung beendet.');
    current=null;
  }
  async function flush(s){
    if(s.sending)return;s.sending=true;
    try{
      while(s.live&&s.queue.length){
        const chunk=s.queue.slice(0,4096);
        const result=await rpc({action:'input',id:s.id,data:b64(chunk)});
        s.queue=s.queue.slice(result.written);
        if(!result.written){await new Promise(resolve=>setTimeout(resolve,30));}
      }
    }catch(e){message(e.message);await stop();}
    finally{s.sending=false;}
  }
  async function poll(s){
    if(!s.live)return;
    try{
      const result=await rpc({action:'poll',id:s.id,cursor:s.cursor});
      if(!s.live)return;s.cursor=result.cursor;
      if(result.lost)s.term.reset();
      await new Promise(resolve=>s.term.write(bytes(result.data),resolve));
      if(result.closed){s.term.writeln('\r\n'+t('Terminalsitzung beendet.'));s.live=false;s.close.disabled=false;status('Terminalsitzung beendet.');return;}
      s.timer=setTimeout(()=>poll(s),result.data.length>30000?0:100);
    }catch(e){message(e.message);await stop();}
  }
  function confirmStart(){
    return new Promise(resolve=>{
      const dialog=el('dialog',undefined,'admin-dialog'),heading=el('h2','Root-Terminal öffnen'),
        warning=el('p','Alle Eingaben werden direkt als root auf dem Server ausgeführt. Es gibt keine Vorschau pro Befehl. ROOT eingeben, um die Sitzung zu öffnen.','warning-text'),
        label=el('label','Zur Bestätigung ROOT eingeben'),input=el('input'),yes=button('Terminal öffnen',()=>{dialog.close();dialog.remove();resolve(true);},'danger'),
        no=button('Abbrechen',()=>{dialog.close();dialog.remove();resolve(false);});
      input.autocomplete='off';label.append(input);yes.disabled=true;input.oninput=()=>yes.disabled=input.value!=='ROOT';
      const actions=el('div',undefined,'result-actions');actions.append(no,yes);
      dialog.append(heading,warning,label,actions);dialog.oncancel=()=>{dialog.remove();resolve(false);};document.body.append(dialog);dialog.showModal();input.focus();
    });
  }
  async function start(body,startButton,closeButton,state){
    if(current){current.term.focus();return;}
    startButton.disabled=true;
    try{
      const preview=await rpc({action:'prepare'});
      if(!await confirmStart()){startButton.disabled=false;return;}
      const container=rawEl('div',undefined,'host-terminal');container.setAttribute('aria-label',t('Interaktives Host-Terminal'));body.append(container);
      const term=new Terminal({cursorBlink:true,fontSize:15,scrollback:3000,allowProposedApi:false,theme:{background:'#071418',foreground:'#e5f4ef'}});
      const fit=new FitAddon.FitAddon();term.loadAddon(fit);term.open(container);fitTerminal(term,fit);
      const s={term,fit,container,status:state,start:startButton,close:closeButton,live:true,id:null,cursor:0,queue:new Uint8Array(),sending:false};
      s.observer=new ResizeObserver(()=>{
        if(!s.live||!container.getClientRects().length)return;
        fitTerminal(term,fit);if(s.id)rpc({action:'resize',id:s.id,cols:term.cols,rows:term.rows}).catch(e=>message(e.message));
      });s.observer.observe(container);current=s;
      const result=await rpc({action:'start',nonce:preview.nonce,confirmation:'ROOT',cols:term.cols,rows:term.rows});s.id=result.id;
      closeButton.disabled=false;status('Root-Terminal verbunden.');
      const enqueue=raw=>{
        if(raw.length+s.queue.length>65536){message(t('Zu viel Eingabe auf einmal. Bitte kleinere Abschnitte einfügen.'));return;}
        const combined=new Uint8Array(s.queue.length+raw.length);combined.set(s.queue);combined.set(raw,s.queue.length);s.queue=combined;flush(s);
      };
      term.onData(text=>enqueue(new TextEncoder().encode(text)));
      term.onBinary(text=>enqueue(Uint8Array.from(text,c=>c.charCodeAt(0)&255)));
      // Never read or write the browser clipboard via terminal control sequences.
      term.parser.registerOscHandler(52,()=>true);
      term.focus();poll(s);
    }catch(e){if(current)await stop();startButton.disabled=false;throw e;}
  }
  function render(body,demo=false){
    if(demo){
      demoObserver?.disconnect();demoTerminal?.dispose();
      const note=el('p','Demo: Terminaldarstellung mit Beispieldaten. Keine Host-Verbindung und keine Eingabe.','hint');
      const container=rawEl('div',undefined,'host-terminal');body.append(note,button('Bestätigungsdialog ansehen (Demo)',()=>confirmStart()),container);
      const term=new Terminal({disableStdin:true,fontSize:15,theme:{background:'#071418',foreground:'#e5f4ef'}}),fit=new FitAddon.FitAddon();
      term.loadAddon(fit);term.open(container);fitTerminal(term,fit);
      demoTerminal=term;demoObserver=new ResizeObserver(()=>{if(container.getClientRects().length)fitTerminal(term,fit);});demoObserver.observe(container);
      term.writeln('\x1b[1;36mServerLotse 0.7.4 · DEMO\x1b[0m\r\n');
      term.writeln(t('Echte Host-Shell mit nano, htop und DietPi-Menüs. Keine SSH-Verbindung erforderlich.'));
      term.writeln('\r\n\x1b[32mroot@DietPi\x1b[0m:~# \x1b[90m'+t('Demo: keine Eingabe')+'\x1b[0m');
      return;
    }
    if(current){body.append(current.controls,current.container);fitTerminal(current.term,current.fit);return;}
    const controls=el('div',undefined,'panel'),state=el('p','Terminal nicht verbunden.','hint');
    const startButton=button('Terminal öffnen',()=>start(body,startButton,closeButton,state),'danger'),closeButton=button('Sitzung schließen',stop),full=button('Vollbild',async()=>{
      if(!current)return;if(document.fullscreenElement)await document.exitFullscreen();else await current.container.requestFullscreen();
    });closeButton.disabled=true;
    controls.append(el('p','Echte Host-Shell mit nano, htop und DietPi-Menüs. Keine SSH-Verbindung erforderlich.'),
      el('p','Nach 15 Minuten ohne Eingabe oder 60 Sekunden ohne Browserverbindung wird die Sitzung beendet. Hintergrunddienste können weiterlaufen.','hint'),startButton,closeButton,full,state);
    body.append(controls);
    const originalStart=startButton.onclick;startButton.onclick=async()=>{await originalStart();if(current)current.controls=controls;};
  }
  window.addEventListener('pagehide',()=>{
    if(current?.id){fetch('/api/terminal',{method:'POST',credentials:'same-origin',keepalive:true,headers:{'Content-Type':'application/json',...(token?{Authorization:'Bearer '+token}:{})},body:JSON.stringify({action:'close',id:current.id})}).catch(()=>{});}
  });
  // Logout removes the page. No terminal identifier is persisted in browser storage.
  window.ServerLotseTerminal={render,stop};
})();
