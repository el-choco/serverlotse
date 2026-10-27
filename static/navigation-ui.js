/* Category landing pages and a persistent path back to the current workspace. */
(() => {
  const crumb=el('div',undefined,'breadcrumbs');crumb.setAttribute('role','navigation');crumb.setAttribute('aria-label',t('Navigationspfad'));document.querySelector('header').after(crumb);
  const groups=[],titles=new Map();let active='overview';
  I18N.ready.then(()=>{
    const navigation=document.querySelector('aside nav'),fileGroup=navigation.querySelector('.nav-category'),storage=navigation.querySelector('[data-page="storage"]');
    if(fileGroup&&storage){const old=storage.closest('.nav-category');if(old)old.dataset.pages=old.dataset.pages.split(',').filter(p=>p!=='storage').join(',');fileGroup.append(storage);fileGroup.dataset.pages+=',storage';}
    for(const [index,group]of [...navigation.querySelectorAll('.nav-category')].entries()){
      const id='category-'+index,name=I18N.original(group.querySelector('summary').textContent),section=el('section',undefined,'page category-page'),grid=el('div',undefined,'tools');section.id=id;section.hidden=true;section.append(el('span','DEIN ARBEITSPLATZ','eyebrow'),el('h1',name),el('p','Wähle ein Werkzeug aus dieser Kategorie.'),grid);
      const ids=group.dataset.pages.split(',').filter(Boolean);groups.push({id,name,ids});
      for(const nav of group.querySelectorAll('button[data-page]')){const pageId=nav.dataset.page,target=$(pageId),heading=target?.querySelector('h1'),description=target?.querySelector('h1+p'),card=el('button',undefined,'tool');titles.set(pageId,I18N.original(nav.textContent).replace(/^[^\p{L}\p{N}]+/u,''));card.type='button';card.append(el('h3',titles.get(pageId)),el('p',description?I18N.original(description.textContent):''),el('strong','Werkzeug öffnen →'));card.onclick=()=>nav.click();grid.append(card);}
      document.querySelector('footer').before(section);
    }
    render(active);
  });
  function render(id){active=id;crumb.replaceChildren();if(id==='overview'){crumb.hidden=true;return;}crumb.hidden=false;
    const add=(label,fn)=>{const b=el('button',label);b.type='button';b.onclick=fn;crumb.append(b);};add('Übersicht',()=>page('overview'));
    const group=groups.find(g=>g.id===id||g.ids.includes(id));
    if(group){crumb.append(rawEl('span','/'));if(group.id!==id)add(group.name,()=>page(group.id));else crumb.append(el('span',group.name));}
    if(group?.id!==id){crumb.append(rawEl('span','/'),el('span',titles.get(id)||I18N.original($(id)?.querySelector('h1')?.textContent||id)));}
  }
  document.addEventListener('serverlotse:page',event=>render(event.detail));document.addEventListener('languagechange',()=>render(active));
  // Status lines ending in an ellipsis ("Prüfung läuft …") describe running work; highlight them wherever they appear.
  const busyText=/(…|\.\.\.)\s*$/,busyCandidate=node=>node?.nodeType===Node.ELEMENT_NODE&&node.matches('main p,main .hint,#message')&&!node.closest('label,button,pre,dialog,.folder-picker');
  function markBusy(node){if(!busyCandidate(node))return;const text=node.textContent.trim();node.classList.toggle('is-busy',text.length>0&&text.length<160&&busyText.test(text));}
  new MutationObserver(records=>{for(const record of records){const target=record.target.nodeType===Node.TEXT_NODE?record.target.parentElement:record.target;markBusy(target);if(record.type==='childList')for(const node of record.addedNodes)if(node.nodeType===Node.ELEMENT_NODE){markBusy(node);node.querySelectorAll?.('p,.hint').forEach(markBusy);}}}).observe(document.body,{subtree:true,childList:true,characterData:true});
  const footer=document.querySelector('footer');footer.replaceChildren();footer.hidden=true;
})();
