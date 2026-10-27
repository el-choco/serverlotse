/* Line icons for navigation, category cards and folder dialogs. Inline SVG keeps the strict CSP intact. */
const ServerLotseIcons = (() => {
  const paths = {
    grid:'M4 4h6v6H4zM14 4h6v6h-6zM14 14h6v6h-6zM4 14h6v6H4z',
    compare:'M7 4 3 8l4 4M3 8h14M17 12l4 4-4 4M21 16H7',
    folder:'M3 7a2 2 0 0 1 2-2h4l2 2h8a2 2 0 0 1 2 2v9a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z',
    folderOpen:'M3 7a2 2 0 0 1 2-2h4l2 2h7a2 2 0 0 1 2 2v1M3 7v11a2 2 0 0 0 2 2h12.5a2 2 0 0 0 1.9-1.4L21.5 12a1 1 0 0 0-1-1.3H7.3a2 2 0 0 0-1.9 1.4L3 18',
    sortBars:'M4 6h16M4 12h11M4 18h6',
    tag:'M3 12V4h8l9 9-8 8zM7.5 7.5h.01',
    search:'M11 4a7 7 0 1 0 0 14 7 7 0 0 0 0-14zM20 20l-4-4',
    copy:'M9 9h11v11H9zM5 15H4V4h11v1',
    lifebuoy:'M12 3a9 9 0 1 0 0 18 9 9 0 0 0 0-18zM12 8a4 4 0 1 0 0 8 4 4 0 0 0 0-8zM5.6 5.6l3.6 3.6M14.8 14.8l3.6 3.6M18.4 5.6l-3.6 3.6M9.2 14.8l-3.6 3.6',
    pie:'M12 3a9 9 0 1 0 9 9h-9zM15 3.5A9 9 0 0 1 20.5 9H15z',
    stethoscope:'M5 3v5a4 4 0 0 0 8 0V3M9 12v2a5 5 0 0 0 10 0v-1M19 9a2 2 0 1 0 0 4 2 2 0 0 0 0-4z',
    lines:'M5 6h14M5 10h14M5 14h9M5 18h6',
    checklist:'M10 6h10M10 12h10M10 18h10M4 6l1.5 1.5L8 5M4 12l1.5 1.5L8 11M4 18l1.5 1.5L8 17',
    heart:'M12 20s-7-4.4-7-10a4 4 0 0 1 7-2.6A4 4 0 0 1 19 10c0 5.6-7 10-7 10zM8 11h2l1-2 2 4 1-2h2',
    power:'M12 3v8M7 6.3a7 7 0 1 0 10 0',
    download:'M12 4v11M7 10l5 5 5-5M5 20h14',
    terminal:'M4 5h16v14H4zM8 10l3 2-3 2M13 15h4',
    shieldTerminal:'M12 3l8 3v6c0 5-3.5 8-8 9-4.5-1-8-4-8-9V6zM9 10l2 2-2 2M13 14h2',
    calendar:'M4 6h16v14H4zM4 10h16M8 3v4M16 3v4M8 14h3',
    rotate:'M4 12a8 8 0 0 1 14-5.3M20 12a8 8 0 0 1-14 5.3M18 3v4h-4M6 21v-4h4',
    clock:'M12 3a9 9 0 1 0 0 18 9 9 0 0 0 0-18zM12 7v5l3 2',
    ghost:'M6 20V10a6 6 0 0 1 12 0v10l-2-2-2 2-2-2-2 2-2-2zM10 10h.01M14 10h.01',
    chip:'M7 7h10v10H7zM10 10h4v4h-4zM10 3v4M14 3v4M10 17v4M14 17v4M3 10h4M3 14h4M17 10h4M17 14h4',
    help:'M12 3a9 9 0 1 0 0 18 9 9 0 0 0 0-18zM9.5 9.5a2.5 2.5 0 1 1 3.5 2.3c-.6.3-1 .9-1 1.5V14M12 17h.01',
    undo:'M9 14 4 9l5-5M4 9h10a6 6 0 0 1 0 12h-3',
    package:'M12 3l8 4.5v9L12 21l-8-4.5v-9zM4 7.5l8 4.5 8-4.5M12 12v9M8 5.3l8 4.5',
    boxes:'M3 8h18v12H3zM5 8l2-4h10l2 4M8 12v4M12 12v4M16 12v4',
    whale:'M3 12h17c.4-1.2 1.2-2 2-2-.3 5-4.3 9-10 9-5 0-8.3-2.7-9-7zM6 12V9h3v3M9 9h3v3M12 9h3v3M12 6h3v3M7 15.5h.01',
    driveScan:'M3 14h18v6H3zM3 14l3-9h12l3 9M7 17h.01M11 17h6',
    broom:'M15 3l-4 8M11 11l-6 3 1 7h8l2-7zM9 21l1-5M13 21l-.3-4',
    radar:'M12 3a9 9 0 1 0 9 9M12 7a5 5 0 1 0 5 5M12 12l6-6M12 12h.01',
    clone:'M8 8h12v12H8zM4 16V4h12M14 11v6M11 14h6',
    eye:'M2 12s4-7 10-7 10 7 10 7-4 7-10 7S2 12 2 12zM12 9a3 3 0 1 0 0 6 3 3 0 0 0 0-6z',
    nodes:'M12 3a3 3 0 1 0 0 6 3 3 0 0 0 0-6zM5 15a3 3 0 1 0 0 6 3 3 0 0 0 0-6zM19 15a3 3 0 1 0 0 6 3 3 0 0 0 0-6zM12 9v3M12 12l-5.2 3.6M12 12l5.2 3.6',
    trash:'M4 7h16M10 11v6M14 11v6M6 7l1 13h10l1-13M9 7V4h6v3',
    layers:'M12 3l9 5-9 5-9-5zM3 13l9 5 9-5M3 17l9 5 9-5',
    bug:'M8 9h8v7a4 4 0 0 1-8 0zM9 9V7a3 3 0 0 1 6 0v2M4 13h4M16 13h4M5 7l3 2M19 7l-3 2M5 20l3-2M19 20l-3-2',
    fileEdit:'M14 3H6v18h5M14 3l4 4v4M14 3v4h4M13 21v-2.5l5.5-5.5 2.5 2.5-5.5 5.5z',
    drive:'M3 6h18v12H3zM7 14h.01M11 14h6M3 10h18',
    plug:'M9 2v5M15 2v5M6 7h12v4a6 6 0 0 1-12 0zM12 17v5',
    battery:'M3 8h16v8H3zM21 11v2M6 11h4v2H6z',
    hash:'M5 9h14M5 15h14M10 4 8 20M16 4l-2 16',
    archive:'M3 4h18v4H3zM5 8v12h14V8M10 12h4',
    database:'M12 3c4.4 0 8 1.3 8 3s-3.6 3-8 3-8-1.3-8-3 3.6-3 8-3zM4 6v12c0 1.7 3.6 3 8 3s8-1.3 8-3V6M4 12c0 1.7 3.6 3 8 3s8-1.3 8-3',
    cloud:'M7 18a4 4 0 0 1-.5-8A6 6 0 0 1 18 9a4.5 4.5 0 0 1-.5 9zM12 11v5M9.5 13.5 12 11l2.5 2.5',
    databaseCheck:'M12 3c4.4 0 8 1.3 8 3s-3.6 3-8 3-8-1.3-8-3 3.6-3 8-3zM4 6v12c0 1.7 3.6 3 8 3M20 6v6M4 12c0 1.7 3.6 3 8 3M15 19l2 2 4-4',
    globe:'M12 3a9 9 0 1 0 0 18 9 9 0 0 0 0-18zM3 12h18M12 3c2.5 2.5 3.5 5.5 3.5 9s-1 6.5-3.5 9c-2.5-2.5-3.5-5.5-3.5-9s1-6.5 3.5-9z',
    template:'M4 4h16v6H4zM4 14h7v6H4zM15 14h5v6h-5z',
    route:'M6 3a3 3 0 1 0 0 6 3 3 0 0 0 0-6zM18 15a3 3 0 1 0 0 6 3 3 0 0 0 0-6zM9 6h6.5a3.5 3.5 0 0 1 0 7h-7a3.5 3.5 0 0 0 0 7H15',
    gauge:'M4 18a8 8 0 1 1 16 0M12 18l4-6M4 18h16',
    refreshGlobe:'M20 12a8 8 0 1 1-2.3-5.7M20 4v5h-5M12 8v4l2 2',
    signpost:'M12 3v18M5 5h11l3 3-3 3H5zM19 13H8l-3 3 3 3h11z',
    users:'M9 11a4 4 0 1 0 0-8 4 4 0 0 0 0 8zM2 21a7 7 0 0 1 14 0M16 3.5a4 4 0 0 1 0 7M22 21a7 7 0 0 0-4-6.3',
    lock:'M5 11h14v10H5zM8 11V7a4 4 0 0 1 8 0v4M12 15v2',
    clipboard:'M9 3h6v3H9zM7 4.5H5V21h14V4.5h-2M8 11h8M8 15h8M8 19h4',
    pulse:'M3 12h4l3-8 4 16 3-8h4',
    sliders:'M4 6h10M18 6h2M4 12h4M12 12h8M4 18h12M20 18h0M14 4v4M8 10v4M16 16v4',
    scroll:'M5 4h11l3 3v13H5zM8 9h8M8 13h8M8 17h5',
    spike:'M3 20h18M4 16l4-7 3 5 3-10 3 8 2-3 2 3',
    key:'M14.5 3a5.5 5.5 0 1 0 0 11 5.5 5.5 0 0 0 0-11zM10.6 12.4 3 20v1h3l1-1v-2h2v-2h2l.6-.6M16 7.5h.01',
    shield:'M12 3l8 3v6c0 5-3.5 8-8 9-4.5-1-8-4-8-9V6zM9 12l2 2 4-4',
    shieldBan:'M12 3l8 3v6c0 5-3.5 8-8 9-4.5-1-8-4-8-9V6zM9 9l6 6M15 9l-6 6',
    wall:'M3 5h18v14H3zM3 10h18M3 15h18M9 5v5M15 10v5M9 15v4',
    monitor:'M3 4h18v12H3zM8 20h8M12 16v4M10 9.5a2 2 0 1 0 4 0 2 2 0 0 0-4 0M8.5 14a3.5 3.5 0 0 1 7 0',
    certificate:'M5 3h14v12H5zM8 7h8M8 11h5M10 15l-1 6 3-2 3 2-1-6',
    octagon:'M8 3h8l5 5v8l-5 5H8l-5-5V8zM12 8v5M12 16h.01',
    flow:'M3 5h6v5H3zM15 14h6v5h-6zM9 7.5h3v9h3',
    bell:'M6 16v-5a6 6 0 0 1 12 0v5l2 2H4zM10 21h4',
    wrench:'M15 4a5 5 0 0 0-5.6 6.6L3 17v4h4l6.4-6.4A5 5 0 0 0 20 9l-3 3-3-1-1-3 3-3z',
    eyeShield:'M12 3l8 3v6c0 5-3.5 8-8 9-4.5-1-8-4-8-9V6zM7.5 12s1.8-3 4.5-3 4.5 3 4.5 3-1.8 3-4.5 3-4.5-3-4.5-3zM12 11.5v1',
    history:'M3 12a9 9 0 1 0 3-6.7M3 4v5h5M12 8v4l3 2',
    home:'M3 11l9-8 9 8M5 9.5V21h14V9.5M10 21v-6h4v6',
    chevron:'M9 6l6 6-6 6'
  };
  const pages = {
    overview:'grid',history:'history',
    compare:'compare',browse:'folderOpen',largest:'sortBars',types:'tag',search:'search',duplicates:'copy',copy_plan:'lifebuoy',storage:'pie',
    system:'stethoscope',log:'lines',checklist:'checklist','health-admin':'heart','services-admin':'power','updates-admin':'download',
    'console-sensors':'terminal','shell-advanced':'shieldTerminal','updates-advanced':'calendar','logs-lab':'rotate','cron-expert':'clock',
    'orphans-expert':'ghost','cache-expert':'chip','analyzer-expert':'help','undo-expert':'undo','apt-expert':'package',
    'containers-admin':'boxes',docker:'whale','unused-sensors':'driveScan','clean-advanced':'broom','radar-lab':'radar','clone-lab':'clone',
    'config-lab':'eye','networks-lab':'nodes','janitor-lab':'trash','builder-expert':'layers','trivy-expert':'bug','volumes-expert':'fileEdit',
    'disks-admin':'drive',mounts:'plug','wear-lab':'battery','inodes-expert':'hash',
    'backups-admin':'archive','bundle-advanced':'database','remote-advanced':'cloud','restore-lab':'databaseCheck',
    'network-admin':'globe','proxy-sensors':'template','proxy-advanced':'route','web-lab':'gauge','ddns-expert':'refreshGlobe','domain-expert':'signpost',
    'users-admin':'users','rights-admin':'lock','audit-admin':'clipboard',
    'live-sensors':'pulse','process-sensors':'sliders','log-sensors':'scroll','history-lab':'spike',
    'ssh-sensors':'key','firewall-sensors':'shield','fail2ban-sensors':'shieldBan','firewall-advanced':'wall','sessions-lab':'monitor',
    'certificates-lab':'certificate','emergency-expert':'octagon','firewall-expert':'flow',
    'automation-advanced':'bell','healing-advanced':'wrench','guardian-lab':'eyeShield'
  };
  const groups = {'Dateiverwaltung':'folder','System':'stethoscope','Docker':'whale','Speicher':'drive','Sicherungen':'archive','Netzwerk':'globe',
    'Benutzer und Rechte':'users','Verwaltung':'clipboard','Monitoring':'pulse','Sicherheit':'shield','Automatik':'bell'};
  const glyph = /^\s*[^\p{L}\p{N}\s]+\s+/u;
  function icon(name, cls='icon') {
    const svg = document.createElementNS('http://www.w3.org/2000/svg','svg');
    svg.setAttribute('viewBox','0 0 24 24');svg.setAttribute('aria-hidden','true');svg.setAttribute('focusable','false');svg.setAttribute('class',cls);
    const path = document.createElementNS('http://www.w3.org/2000/svg','path');path.setAttribute('d',paths[name]||paths.chevron);svg.append(path);return svg;
  }
  // Older labels carry a text symbol in front ("◎ Systemdiagnose"); replace it with the SVG and keep the translated label.
  function stripGlyph(node) {
    for (const child of [...node.childNodes]) {
      if (child.nodeType !== Node.TEXT_NODE || !glyph.test(child.textContent)) continue;
      const rest = I18N.original(child.textContent).replace(glyph,'');
      if (rest.trim()) child.replaceWith(el('span',rest)); else child.remove();
    }
  }
  function decorate(button, name, cls) {
    if (!name || button.querySelector(':scope>svg.'+cls)) return;
    stripGlyph(button);button.prepend(icon(name,cls));
  }
  function decorateAll() {
    const nav = document.querySelector('aside nav');if (!nav) return;
    observer.disconnect();
    for (const button of nav.querySelectorAll('button[data-page]')) decorate(button,pages[button.dataset.page]||'chevron','nav-icon');
    for (const summary of nav.querySelectorAll('.nav-category>summary')) {
      if (summary.querySelector('.nav-chevron')) continue;
      decorate(summary,groups[I18N.original(summary.textContent.trim())]||'grid','nav-icon');
      summary.append(icon('chevron','nav-chevron'));
    }
    for (const summary of document.querySelectorAll('.dashboard-category>summary')) {
      if (summary.querySelector('.nav-chevron')) continue;
      summary.prepend(icon(groups[I18N.original(summary.textContent.trim())]||'grid','nav-icon'));summary.append(icon('chevron','nav-chevron'));
    }
    for (const section of document.querySelectorAll('.category-page')) {
      const name = I18N.original(section.querySelector('h1')?.textContent||''),group = [...nav.querySelectorAll('.nav-category')].find(g=>I18N.original(g.querySelector('summary').textContent.trim())===name);
      if (!group) continue;
      const buttons = [...group.querySelectorAll('button[data-page]')];
      [...section.querySelectorAll('.tools>.tool')].forEach((card,index)=>{if(buttons[index]&&!card.querySelector('.tool-icon'))card.prepend(Object.assign(document.createElement('span'),{className:'tool-icon'})),card.firstChild.append(icon(pages[buttons[index].dataset.page]||'grid'));});
    }
    observer.observe(nav,{childList:true,subtree:true});
  }
  const observer = new MutationObserver(()=>queueMicrotask(decorateAll));
  I18N.ready.then(()=>setTimeout(decorateAll));
  document.addEventListener('languagechange',()=>setTimeout(decorateAll));
  return {icon};
})();
