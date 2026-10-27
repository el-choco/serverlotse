/* One catalog for all languages. No tokens or credentials in browser storage. */
const I18N = (() => {
  const supported = ['de','en','es'];
  let saved;
  try { saved = localStorage.getItem('serverlotse.language'); } catch {}
  let lang = supported.includes(saved) ? saved : 'de';
  let catalog = [], patterns = [];
  const sourceText = new WeakMap(), sourceAttrs = new WeakMap();
  const escape = value => value.replace(/[.*+?^${}()|[\]\\]/g,'\\$&');
  function original(value) {
    for (const row of catalog) if (row.includes(value)) return row[0];
    return value;
  }
  function t(value, variables) {
    if (typeof value !== 'string') return value;
    let translated = value;
    const index = {de:0,en:1,es:2}[lang];
    const exact = catalog.find(row => row.includes(value));
    if (exact) translated = exact[index];
    else for (const item of patterns) {
      const match = item.regex.exec(value);
      if (match) {
        translated = item.row[index];
        item.names.forEach((name,i) => translated = translated.replaceAll('{'+name+'}',name === 'label' ? t(match[i+1]) : match[i+1]));
        break;
      }
    }
    if (variables) for (const [key,part] of Object.entries(variables)) translated = translated.replaceAll('{'+key+'}',part);
    return translated;
  }
  function protectedNode(node) {return node.parentElement?.closest('[data-no-translate],pre,script,style');}
  function translateNode(node) {
    if (node.nodeType === Node.TEXT_NODE) {
      if (protectedNode(node) || !node.textContent.trim()) return;
      const previous = sourceText.get(node);
      if (!previous || node.textContent !== t(previous)) sourceText.set(node, original(node.textContent));
      const value = t(sourceText.get(node));
      if (node.textContent !== value) node.textContent = value;
    } else if (node.nodeType === Node.ELEMENT_NODE) {
      if (node.closest('[data-no-translate],pre,script,style')) return;
      let attributes = sourceAttrs.get(node);
      if (!attributes) {attributes = {}; sourceAttrs.set(node,attributes);}
      for (const key of ['placeholder','aria-label','title']) if (node.hasAttribute(key)) {
        const current = node.getAttribute(key);
        if (!(key in attributes) || current !== t(attributes[key])) attributes[key] = original(current);
        const translated = t(attributes[key]);
        if (current !== translated) node.setAttribute(key,translated);
      }
      for (const child of node.childNodes) translateNode(child);
    }
  }
  function refresh() {document.documentElement.lang=lang;translateNode(document.body);}
  function bind(element,value) {
    element.textContent=t(value);
    if (element.firstChild) sourceText.set(element.firstChild,value);
  }
  function change(value) {
    if (!supported.includes(value)) return;
    lang=value;
    try {localStorage.setItem('serverlotse.language',lang);} catch {}
    refresh();
    document.dispatchEvent(new CustomEvent('languagechange'));
  }
  const ready = fetch('/locales.json').then(r=>{if(!r.ok)throw Error('Language catalog unavailable');return r.json();}).then(rows=>{
    catalog=rows;
    for(const row of rows) if(row[0].includes('{')) for(const source of row) {
      const names=[...source.matchAll(/\{(\w+)\}/g)].map(m=>m[1]);
      let regex=escape(source);
      for(const name of names) regex=regex.replace(escape('{'+name+'}'),'(.+?)');
      patterns.push({row,names,regex:new RegExp('^'+regex+'$','s')});
    }
    refresh();
    new MutationObserver(records=>{for(const record of records){if(record.type==='childList')record.addedNodes.forEach(translateNode);else translateNode(record.target);}}).observe(document.body,{childList:true,subtree:true,characterData:true,attributes:true,attributeFilter:['placeholder','aria-label','title']});
  });
  return {t,original,bind,refresh,change,ready,get lang(){return lang;},get locale(){return {de:'de-DE',en:'en-GB',es:'es-ES'}[lang];}};
})();
const t = (value,variables) => I18N.t(value,variables);
