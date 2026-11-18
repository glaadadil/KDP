"use strict";
const $ = (s, root=document) => root.querySelector(s);
const $$ = (s, root=document) => [...root.querySelectorAll(s)];
const esc = v => String(v ?? "").replace(/[&<>"']/g, c=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));
const opt = (items,selected) => Object.entries(items).map(([k,v])=>`<option value="${esc(k)}" ${k===selected?"selected":""}>${esc(v)}</option>`).join("");
const dictionary = v => Object.fromEntries(v.map(s=>[s,s]));
const kinds={livre:"Livre",outil:"Outil de calcul",imprimable:"Imprimable"};
const ai={unknown:"À préciser",none:"Aucune",assisted:"Assistance à la création",generated:"Contenu généré"};
const statuses={open:"À faire",review:"À valider",approved:"Validé",revise:"À corriger"};
const levels={ok:"Conforme",warning:"Avertissement",error:"Bloquant",human:"Vérification humaine"};
const tabs={atelier:"Atelier",fiche:"Fiche produit",fichiers:"Importer",controle:"Contrôler",depot:"Dépôt",historique:"Historique"};
let cfg,p,stageIndex=0,all=[],timer,routeGeneration=0,filter="",search="";
const main=$("#main"),dlg=$("#modal");
function note(text,error=false){
  const el=dlg.open?$("#dialog-note"):$("#toast");
  if(!el)return;
  el.hidden=false;el.textContent=text;el.className=error?"error notice":"";
  clearTimeout(timer);
  if(el.id==="toast")timer=setTimeout(()=>el.hidden=true,6500);
}
function bind(sel,event,fn,root=document){
  for(const el of $$(sel,root))el.addEventListener(event,async ev=>{
    try{await fn(ev,el)}catch(e){note(e.message,true)}
  });
}
function modal(title,html){
  $("#modal-title").textContent=title;$("#modal-body").innerHTML=html+'<p id="dialog-note" hidden role="status"></p>';
  if(!dlg.open)dlg.showModal();
}
function close(){if(dlg.open)dlg.close()}
async function api(path,method="GET",body,project=false,raw=false){
  const headers={"X-Venture-Action":"local"};
  if(project)headers["If-Match"]=p.rev;
  if(body!==undefined && !(body instanceof FormData)){headers["Content-Type"]="application/json";body=JSON.stringify(body)}
  let r;
  try{r=await fetch("/api"+path,{method,headers,body})}catch{throw Error("Serveur local inaccessible. Reprends après le redémarrage.")}
  if(!r.ok){let msg;try{msg=(await r.json()).detail}catch{}throw Error(msg||"L’action a échoué ("+r.status+").")}
  return raw?r:r.json();
}
const pp=()=>"/projects/"+p.id;
function download(blob,name){
  const u=URL.createObjectURL(blob),link=document.createElement("a");link.href=u;link.download=name;link.click();setTimeout(()=>URL.revokeObjectURL(u),20000);
}
async function downloadResponse(r,fallback){
  const name=/filename="([^"]+)"/.exec(r.headers.get("Content-Disposition")||"")?.[1]||fallback;
  download(await r.blob(),name);
}
function draftForm(selector,key){
  const form=$(selector);
  const name="venture:draft:"+key;
  let stored={};try{stored=JSON.parse(localStorage.getItem(name)||"{}")}catch{}
  for(const input of form.elements)if(input.name && Object.hasOwn(stored,input.name))input.value=stored[input.name];
  form.addEventListener("input",()=>{try{localStorage.setItem(name,JSON.stringify(Object.fromEntries(new FormData(form))))}catch{note("Brouillon trop volumineux. Enregistre-le dans le projet.",true)}});
  return ()=>localStorage.removeItem(name);
}
function go(id,tab="atelier"){location.hash=id?"/"+id+"/"+tab:"/"}
function date(s){return new Date(s).toLocaleString("fr-FR",{dateStyle:"short",timeStyle:"short"})}
function nextTab(x){if(x.status==="Correction nécessaire")return "controle";if(x.status!=="Brouillon")return "depot";return x.files?"controle":"atelier"}
async function library(){
  p=null;all=await api("/projects");
  main.innerHTML=`<section class="hero"><div><h1>Bibliothèque</h1><p>Retrouve tes éditions, leurs fichiers et la prochaine étape de production.</p><div class="actions"><button id="new">＋ Nouveau projet</button><button class="ghost" id="import">Importer une fiche</button></div></div><div class="books" aria-hidden="true"><span></span><span></span><span></span></div></section>
  <div class="stats">${[["","Tous les projets",all.length],["corriger","À corriger",all.filter(x=>x.blocking_count||x.status==="Correction nécessaire").length],["valider","À valider",all.filter(x=>x.review).length],["Prêt au dépôt","Prêts au dépôt",all.filter(x=>x.status==="Prêt au dépôt").length],["Publié","Publiés",all.filter(x=>x.status==="Publié").length]].map(([k,v,n])=>`<button class="stat" data-filter="${k}">${v}<b>${n}</b></button>`).join("")}</div>
  <div class="section-head"><h2>Mes éditions</h2><div class="filters"><input id="search" type="search" aria-label="Rechercher un projet" placeholder="Rechercher un projet" value="${esc(search)}"><select id="filter" aria-label="Filtrer">${opt({"":"Tous les statuts","valider":"À valider","corriger":"À corriger",...dictionary(["Brouillon","Prêt au dépôt","Dépôt en cours","Soumis","En examen","Publié","Correction nécessaire"])},filter)}</select></div></div>
  <div id="cards"></div><div class="footer line"><button id="demo" class="link">Ouvrir un exemple complet</button><span>·</span><button id="connection" class="link">Connexion Etsy</button><span>·</span><button id="guide" class="link">Guide d’utilisation</button></div>`;
  bind("#new","click",newProject);bind("#import","click",importForm);bind("#demo","click",demoForm);
  bind("#guide","click",()=>modal("Guide d’utilisation",guide()));bind("#connection","click",connection);
  bind("#search","input",(e,el)=>{search=el.value;cards()});bind("#filter","change",(e,el)=>{filter=el.value;cards()});
  bind("[data-filter]","click",(e,el)=>{filter=el.dataset.filter;$("#filter").value=filter;cards()});cards();
}
function cards(){
 const list=all.filter(x=>(!filter||(filter==="valider"?x.review:filter==="corriger"?(x.blocking_count||x.status==="Correction nécessaire"):x.status===filter))&&x.manifest.title.toLocaleLowerCase().includes(search.toLocaleLowerCase()));
 $("#cards").innerHTML=list.length?`<div class="grid">${list.map(x=>`<button class="project" data-id="${esc(x.id)}"><span class="upper">${esc(cfg.channels[x.manifest.channel])} · v${esc(x.manifest.version)}</span><strong>${esc(x.manifest.title)}</strong><span class="tag">${esc(x.status)}</span><small>${x.progress}/8 étapes validées · ${x.files} fichier(s)${x.blocking_count?" · "+x.blocking_count+" à corriger":""}</small><progress class="progress" value="${x.progress}" max="8"></progress></button>`).join("")}</div>`:`<div class="empty"><h3>${all.length?"Aucune édition correspondante":"Ta bibliothèque est prête"}</h3><p>${all.length?"Modifie ta recherche ou le filtre.":"Crée un projet ou explore le parcours avec un exemple et ses fichiers."}</p><button id="emptyAction">${all.length?"Effacer les filtres":"Explorer un exemple"}</button></div>`;
 bind("[data-id]","click",(e,el)=>{const x=all.find(x=>x.id===el.dataset.id);go(x.id,nextTab(x))});
 bind("#emptyAction","click",()=>{if(all.length){filter="";search="";return library()}demoForm()});
}
function newProject(){
 modal("Nouveau projet",`<form id="newform" class="fields"><label class="full">Titre du produit<input required name="title" maxlength="200" autofocus></label><label>Parcours<select name="kind">${opt(kinds,"livre")}</select></label><label>Destination<select name="channel">${opt(cfg.channels,"paper")}</select></label><label>Version<input name="version" value="1.0" required></label><label>Langue du produit<input name="language" value="en" required></label><label class="full">Public, objectif et contraintes<textarea name="brief" rows="4"></textarea></label><button class="primary full">Créer le projet</button></form>`);
 const clear=draftForm("#newform","create");
 bind("#newform","submit",async e=>{e.preventDefault();const m=Object.fromEntries(new FormData(e.target));const result=await api("/projects","POST",{schema_version:"1.0",...m});clear();close();go(result.id)});
}
function importForm(){
 modal("Importer une fiche produit",`<div class="drop"><b>Dossier complet</b><label>ZIP avec produit.json et fichiers<input id="bundle" type="file" accept=".zip"></label></div><form id="imform" class="stack"><label>Fichier JSON<input type="file" id="jsonfile" accept=".json"></label><label>Ou colle le manifeste JSON<textarea name="json" rows="11" required placeholder='{"schema_version":"1.0", ...}'></textarea></label><a href="/api/schema" target="_blank" rel="noopener">Consulter le format du manifeste</a><p>Les contrôles et validations déclarés dans une fiche importée sont conservés pour référence. L’application vérifie les fichiers déposés.</p><button class="primary">Importer le manifeste</button></form>`);
 bind("#bundle","change",async(e,el)=>{if(!el.files[0])return;const d=new FormData();d.append("archive",el.files[0]);const x=await api("/bundle","POST",d);close();go(x.id,"fichiers")});
 const clear=draftForm("#imform","manifest");
 bind("#jsonfile","change",async(e,el)=>{if(el.files[0]){const area=$("#imform textarea");area.value=await el.files[0].text();area.dispatchEvent(new Event("input",{bubbles:true}))}});
 bind("#imform","submit",async e=>{e.preventDefault();let m;try{m=JSON.parse(e.target.json.value)}catch{throw Error("JSON illisible. Vérifie les virgules et les guillemets.")}const x=await api("/projects","POST",m);clear();close();go(x.id,"fichiers")});
}
function demoForm(){
 modal("Explorer un exemple",`<p>Choisis une édition de démonstration. Ses fichiers et sa fiche seront ajoutés à ta bibliothèque.</p><div class="actions">${Object.entries({...cfg.channels,outil:"Outil de calcul Etsy"}).map(([k,v])=>`<button data-demo="${k}">${v}</button>`).join("")}</div>`);
 bind("[data-demo]","click",async(e,el)=>{el.disabled=true;try{const x=await api("/demo/"+el.dataset.demo,"POST");close();go(x.id,"controle")}finally{el.disabled=false}});
}
function guide(){return '<div class="stack"><p><b>Atelier.</b> Copie la mission dans ChatGPT, puis ouvre « Importer la réponse ChatGPT ». Colle sa réponse, vérifie l’aperçu et enregistre-la. La validation de l’étape t’appartient.</p><p><b>Importer.</b> Dépose les fichiers prêts. Attribue à chacun un rôle. Remplacer un nom identique conserve la version précédente.</p><p><b>Contrôler et déposer.</b> Corrige les erreurs, prépare le ZIP et examine les points humains. Déclare le statut après confirmation sur Etsy ou KDP.</p><p><b>Sauvegarder.</b> Télécharge une sauvegarde complète du catalogue et des originaux. La procédure de restauration figure dans le README fourni.</p></div>'}
async function route(){
 const generation=++routeGeneration;const [,id,requested]=location.hash.slice(1).split("/");close();
 if(!id){await library();return}
 const data=await api("/projects/"+encodeURIComponent(id));if(generation!==routeGeneration)return;
 if(p?.id!==id){stageIndex=data.stages.findIndex(s=>s.status!=="approved");if(stageIndex<0)stageIndex=7}
 p=data;const t=Object.hasOwn(tabs,requested)?requested:"atelier";
 main.innerHTML=`<button class="link" id="back">← Bibliothèque</button><div class="splithead"><div><span class="upper">${esc(cfg.channels[p.manifest.channel])} · ${esc(kinds[p.manifest.kind])} · v${esc(p.manifest.version)}</span><h1>${esc(p.manifest.title)}</h1></div><div><span class="tag">${esc(p.status)}</span> <button id="edition">Nouvelle édition</button></div></div><nav class="tabs" aria-label="Sections du projet">${Object.entries(tabs).map(([k,v])=>`<button data-tab="${k}" class="${k===t?"sel":""}">${v}</button>`).join("")}</nav><div id="content"></div>`;
 bind("#back","click",()=>go());bind("[data-tab]","click",(e,el)=>go(id,el.dataset.tab));bind("#edition","click",edition);
 await ({atelier:workshop,fiche:metadata,fichiers:files,controle:checks,depot:publication,historique:historyPage})[t]();
}
function edition(){
 modal("Créer une édition",`<form id="editionform" class="stack"><label>Version<input name="version" required placeholder="Ex. 1.1"></label><label>Destination<select name="channel">${opt(cfg.channels,p.manifest.channel)}</select></label><p>Les fichiers et les étapes sont repris. Le suivi de publication démarre au brouillon.</p><button class="primary">Créer l’édition</button></form>`);
 bind("#editionform","submit",async e=>{e.preventDefault();const x=await api(pp()+"/edition","POST",Object.fromEntries(new FormData(e.target)));close();go(x.id,"fiche")});
}
const proposalLabels = {
  title: "Titre",
  subtitle: "Sous-titre",
  description: "Description",
  category: "Catégorie",
  keywords: "Mots-clés"
};

function readableValue(value) {
  return Array.isArray(value) ? value.join(" · ") : String(value ?? "");
}

function proposalEntries(packet) {
  return Object.entries(packet?.suggested_metadata || {})
    .filter(([key, value]) => Object.hasOwn(proposalLabels, key) && value != null && readableValue(value));
}

function metadataDraftValue(value) {
  return Array.isArray(value) ? value.join("\n") : String(value ?? "");
}

function packetDetails(packet, editableProposals=false) {
  if (!packet) return "";
  const groups = [
    ["Orientations et décisions", packet.decisions],
    ["Questions ouvertes", packet.open_questions],
    ["Sources indiquées", packet.sources],
    ["Contrôles déclarés par le spécialiste", packet.checks]
  ];
  const lists = groups.filter(([, items]) => items?.length).map(([title, items]) =>
    `<details class="packet-list"><summary>${esc(title)} (${items.length})</summary>
       <ul>${items.map(item => `<li>${esc(item)}</li>`).join("")}</ul></details>`
  ).join("");
  const proposals = proposalEntries(packet);
  const suggested = proposals.map(([key, value]) => {
    const current = readableValue(p.manifest[key]);
    const target = readableValue(value);
    if (!editableProposals) {
      return `<div class="packet-value"><b>${proposalLabels[key]}</b><p>${esc(target)}</p></div>`;
    }
    return `<label class="proposal-row"><input type="checkbox" name="field" value="${key}" ${current===target?"disabled":""}>
      <span><b>${proposalLabels[key]}</b><small>Valeur actuelle · ${esc(current || "Non renseignée")}</small>
      <span class="packet-value">${esc(target)}</span></span></label>`;
  }).join("");
  const fields = proposals.length ? (editableProposals
    ? `<fieldset id="proposal-fields" class="proposal-fields"><legend>Propositions pour la fiche produit</legend>
       ${suggested}<button type="button" id="apply-proposals" disabled>Appliquer les champs cochés</button></fieldset>`
    : `<details class="packet-list"><summary>Propositions pour la fiche produit (${proposals.length})</summary>${suggested}</details>`)
    : "";
  return `<section class="packet-section"><h3>Transmission à l’étape suivante</h3>
    <p class="packet-value">${esc(packet.handoff)}</p>${lists}${fields}</section>`;
}

async function showCopiedPrompt(text, success) {
  try {
    await navigator.clipboard.writeText(text);
    note(success);
  } catch {
    const fallback='<label id="copy-manually">Consigne à sélectionner et copier<textarea id="copy-prompt" rows="10" readonly></textarea></label>';
    if (dlg.open) {
      $("#copy-manually")?.remove();
      $("#dialog-note").insertAdjacentHTML("beforebegin",fallback);
    } else {
      modal("Copier la consigne",fallback);
    }
    const prompt=$("#copy-prompt");
    prompt.value=text;
    prompt.focus();
    prompt.select();
  }
}

function isStagePacket(text) {
  return /"protocol"\s*:\s*"venture\.stage\.v1"/.test(text) && /"edition_id"\s*:/.test(text);
}

function importStageReply(clearManualDraft, initial="", fromManualField=false) {
  const index=stageIndex;
  const project=p.id;
  const endpoint=pp()+"/stages/"+index;
  const missionPath=pp()+"/mission/"+index;
  const stage=p.stages[index];
  const manual=$("#stageform");
  const manualText=fromManualField ? stage.text : manual.elements.text.value;
  const notes=manual.elements.notes.value;
  const unsaved=manualText!==stage.text || notes!==stage.notes;
  const key=project+"/reply/"+index;
  modal("Importer la réponse ChatGPT", `<div class="stack">
    <p><b>${esc(cfg.stages[index])}</b> · ${esc(p.manifest.title)} · v${esc(p.manifest.version)}</p>
    <form id="reply-source" class="stack">
      <label>Réponse de ChatGPT<textarea id="stage-reply" name="response" rows="7" autofocus placeholder="Colle toute la réponse à la mission."></textarea></label>
      <label>Ou choisir un fichier JSON<input type="file" id="stage-reply-file" accept=".json,application/json"></label>
      <div class="line"><button class="primary" id="preview-stage-reply">Vérifier la réponse</button>
      <button type="button" id="conversion">Adapter une réponse en texte libre</button></div>
    </form>
    <div id="reply-preview" hidden></div>
  </div>`);
  const form=$("#reply-source");
  const area=$("#stage-reply");
  const preview=$("#reply-preview");
  const clearReply=draftForm("#reply-source",key);
  if (initial && (area.value===initial || !area.value || confirm("Remplacer le brouillon de réponse à importer par le texte que tu viens de coller ?"))) {
    area.value=initial;
    area.dispatchEvent(new Event("input",{bubbles:true}));
  }
  const active=()=>dlg.open && form.isConnected && p?.id===project && stageIndex===index;
  let validated="";
  let attempt=0;
  function invalidate() {
    validated="";
    attempt++;
    preview.hidden=true;
    preview.replaceChildren();
    $("#copy-manually")?.remove();
    $("#dialog-note").hidden=true;
  }
  bind("#stage-reply","input",invalidate);
  bind("#stage-reply-file","change",async(e,el)=>{
    const file=el.files[0];
    if (!file) return;
    if (file.size>2_000_000) throw Error("Ce fichier est trop volumineux pour une réponse d’atelier (2 Mo maximum).");
    const text=await file.text();
    if (active()) {
      area.value=text;
      area.dispatchEvent(new Event("input",{bubbles:true}));
    }
  });
  bind("#conversion","click",async()=>{
    const pasted=area.value.trim();
    const prompt=await api(missionPath+"?convert=true"+(pasted?"&include_current=false":""));
    if (!active()) return;
    const full=pasted ? prompt.text+"\n\nTexte source à convertir\n"+pasted : prompt.text;
    await showCopiedPrompt(full,"Consigne de conversion copiée. Colle-la dans ChatGPT puis rapporte sa réponse ici.");
  });
  bind("#reply-source","submit",async e=>{
    e.preventDefault();
    const raw=area.value;
    if (!raw.trim()) throw Error("Colle la réponse ou choisis son fichier JSON.");
    if (raw.length>280000 && Array.from(raw).length>280000) throw Error("La réponse dépasse 280 000 caractères. Demande à ChatGPT de la raccourcir.");
    const serial=++attempt;
    const packet=await api(endpoint+"/preview","POST",{response:raw});
    if (!active() || attempt!==serial || area.value!==raw) return;
    validated=raw;
    $("#dialog-note").hidden=true;
    preview.hidden=false;
    preview.innerHTML=`<div class="stack"><h3 tabindex="-1">Aperçu du résultat</h3>
      <details open><summary>Livrable de ${esc(packet.stage)}</summary><pre class="reply-text">${esc(packet.deliverable)}</pre></details>
      ${packetDetails(packet)}
      ${stage.text?'<p>Le résultat actuel restera consultable dans l’historique de l’édition.</p>':""}
      ${stage.status==="approved"?'<p>Cette étape et les étapes approuvées qui la suivent repasseront en relecture.</p>':""}
      ${unsaved?'<p class="notice">Ton brouillon de saisie sera enregistré dans l’historique avant l’importation.</p>':""}
      <button class="primary" id="save-stage-reply">Enregistrer pour validation</button></div>`;
    $("h3",preview).focus();
    bind("#save-stage-reply","click",async(ev,button)=>{
      if (!active() || validated!==area.value) return;
      const response=validated;
      button.disabled=true;
      for (const field of form.elements) field.disabled=true;
      try {
        if (unsaved) {
          const saved=await api(endpoint,"PUT",{text:manualText,notes,decision:"draft"},true);
          if (p?.id!==project) return;
          p=saved;
          if (!active()) return;
        }
        const updated=await api(endpoint,"PUT",{response,notes,decision:"draft"},true);
        if (p?.id!==project) return;
        p=updated;
        if (!active()) return;
        clearManualDraft();
        clearReply();
        close();
        await route();
        note("Réponse enregistrée. Relis le résultat puis valide l’étape.");
      } finally {
        button.disabled=false;
        for (const field of form.elements) field.disabled=false;
      }
    },preview);
  });
}

async function workshop(){
  const stage=p.stages[stageIndex];
  const name=cfg.stages[stageIndex];
  const stages=cfg.stages.map((title,i)=>
    `<button data-step="${i}" class="${i===stageIndex?"sel":""}"><span>${esc(title)}</span>
     <small>${p.stages[i].status==="approved"?"✓":i+1}</small></button>`
  ).join("");
  $("#content").innerHTML=`<div class="two"><aside>
      <nav class="stages" aria-label="Étapes de production">${stages}</nav>
      <details class="workshop-kind"><summary>Spécialité des missions</summary>
        <form id="kind-form" class="stack"><label>Parcours de production<select id="workshop-kind" name="kind">
          ${opt({"":"Selon la fiche · "+kinds[p.manifest.kind],...kinds},p.workshop_kind??"")}
        </select></label><button id="apply-workshop-kind">Appliquer le parcours</button></form>
      </details>
    </aside><section class="panel stack">
      <div><span class="upper">Mission ${stageIndex+1} sur ${cfg.stages.length} · ${esc(kinds[p.workshop_kind || p.manifest.kind])}</span><h2>${esc(name)}</h2></div>
      <span class="tag">${statuses[stage.status]}</span>
      <div class="line"><button class="primary" id="copy">Copier la mission</button>
        <button id="import-stage">Importer la réponse ChatGPT</button><button id="viewMission" class="link">Lire la consigne</button></div>
      <p class="sub">Colle la mission dans ChatGPT, puis rapporte sa réponse. Tu peux aussi joindre le dossier de contexte si le spécialiste a besoin des livrables complets.</p>
      <a class="link" href="/api${pp()}/mission/${stageIndex}/context" download>Télécharger le contexte complet</a>
      <form id="stageform" class="stack"><label>Résultat du spécialiste<textarea name="text" rows="7" placeholder="Saisie manuelle ou livrable existant">${esc(stage.text)}</textarea></label>
        <label>Corrections ou observations<textarea name="notes" rows="3">${esc(stage.notes)}</textarea></label>
        <div class="actions"><button data-decision="draft">Enregistrer</button><button data-decision="revise">Demander une correction</button>
        <button class="primary" data-decision="approve">Valider l’étape</button></div></form>
      ${packetDetails(stage.packet,true)}
    </section></div>`;
  const clear=draftForm("#stageform",p.id+"/stage/"+stageIndex);
  bind("[data-step]","click",async(e,el)=>{stageIndex=Number(el.dataset.step);await workshop()});
  const missionPath=pp()+"/mission/"+stageIndex;
  bind("#viewMission","click",async()=>modal(name,`<pre>${esc((await api(missionPath)).text)}</pre>`));
  bind("#copy","click",async()=>showCopiedPrompt((await api(missionPath)).text,"Mission copiée. Colle-la dans ChatGPT."));
  bind("#import-stage","click",()=>importStageReply(clear));
  bind("#stageform [name=text]","paste",e=>{
    const pasted=e.clipboardData?.getData("text") || "";
    if (!isStagePacket(pasted)) return;
    e.preventDefault();
    importStageReply(clear,pasted);
  });
  bind("#kind-form","submit",async e=>{
    e.preventDefault();
    const kind=$("#workshop-kind").value || null;
    p=await api(pp()+"/workshop-kind","PUT",{kind},true);
    await workshop();
    note("Parcours enregistré. La prochaine consigne utilisera cette spécialité.");
  });
  bind("#proposal-fields input","change",()=>{
    $("#apply-proposals").disabled=!$("#proposal-fields input:checked");
  });
  bind("#apply-proposals","click",async(e,button)=>{
    const fields=$$("#proposal-fields input:checked").map(input=>input.value);
    if (!fields.length) return;
    const draftName="venture:draft:"+p.id+"/meta";
    const readDraft=()=>JSON.parse(localStorage.getItem(draftName)||"{}") || {};
    const draft=readDraft();
    const proposed=stage.packet.suggested_metadata;
    const changed=fields.filter(key=>Object.hasOwn(draft,key)
      && draft[key]!==metadataDraftValue(p.manifest[key])
      && draft[key]!==metadataDraftValue(proposed[key]));
    if (changed.length && !confirm("Remplacer aussi ton brouillon de fiche pour les champs « "+changed.map(key=>proposalLabels[key]).join(" », « ")+" » ?")) return;
    button.disabled=true;
    try {
      p=await api(pp()+"/stages/"+stageIndex+"/apply-metadata","POST",{fields},true);
      const latest=readDraft();
      for (const key of fields) {
        if (latest[key]===draft[key]) delete latest[key];
      }
      if (Object.keys(latest).length) localStorage.setItem(draftName,JSON.stringify(latest));
      else localStorage.removeItem(draftName);
      await route();
      note("Les champs sélectionnés ont été enregistrés dans la fiche produit.");
    } finally {
      if (button.isConnected) button.disabled=false;
    }
  });
  bind("#stageform","submit",async e=>{
    e.preventDefault();
    const decision=e.submitter?.dataset.decision || "draft";
    const fields=Object.fromEntries(new FormData(e.target));
    if (fields.text!==stage.text && isStagePacket(fields.text)) {
      importStageReply(clear,fields.text,true);
      return;
    }
    if (stage.packet && fields.text!==stage.text) {
      if (!confirm("Enregistrer ta nouvelle rédaction comme résultat manuel ? La transmission structurée précédente restera dans l’historique.")) return;
    }
    p=await api(pp()+"/stages/"+stageIndex,"PUT",{...fields,decision},true);
    clear();
    if (decision==="approve" && stageIndex<cfg.stages.length-1) stageIndex++;
    await route();
    note("Étape enregistrée.");
  });
}
function metadata(){
 const m=p.manifest;
 function input(key,label,type="text"){return `<label>${label}<input name="${key}" type="${type}" ${type==="number"?'min=".01" step=".01"':""} value="${esc(m[key])}"></label>`}
 $("#content").innerHTML=`<div class="panel"><h2>Fiche produit</h2><form id="meta" class="fields gap">${input("title","Titre")}${input("subtitle","Sous-titre")}${input("author","Auteur ou marque")}${input("language","Langue")}<label class="full">Brief de production<textarea name="brief" rows="3">${esc(m.brief)}</textarea></label><label class="full">Description commerciale<textarea name="description" rows="5">${esc(m.description)}</textarea></label>${input("category","Catégorie prévue")}<label>Mots-clés, un par ligne<textarea name="keywords" rows="3">${esc(m.keywords.join("\n"))}</textarea></label>${input("price","Prix envisagé","number")}${input("currency","Devise (ex. USD)")}<label>Usage de l’IA<select name="ai">${opt(ai,m.ai)}</select></label>${input("ai_details","Précisions sur les textes, images ou traductions")}${m.channel==="paper"?`<label>Format en pouces<select name="trim">${opt(dictionary(["5x8","5.5x8.5","6x9","7x10","8x10"]),m.print.trim)}</select></label><label>Impression<select name="paper">${opt({white:"Noir sur blanc",cream:"Noir sur crème","standard-color":"Couleur standard","premium-color":"Couleur premium"},m.print.paper)}</select></label><label>Intérieur avec fond perdu<select name="bleed">${opt({no:"Non",yes:"Oui"},m.print.bleed?"yes":"no")}</select></label>`:""}<div class="full actions"><button class="primary">Enregistrer la fiche</button><button type="button" id="getManifest">Télécharger le manifeste enregistré</button></div></form></div>`;
 const clear=draftForm("#meta",p.id+"/meta");
 bind("#meta","submit",async e=>{e.preventDefault();const f=Object.fromEntries(new FormData(e.target));const settings=f.trim?{trim:f.trim,paper:f.paper,bleed:f.bleed==="yes"}:m.print;delete f.trim;delete f.paper;delete f.bleed;
 p=await api(pp(),"PUT",{...m,...f,print:settings,price:f.price?Number(f.price):null,currency:f.currency.toUpperCase(),keywords:f.keywords.split("\n").map(x=>x.trim()).filter(Boolean)},true);clear();await route();note("Fiche enregistrée.")});
 bind("#getManifest","click",()=>download(new Blob([JSON.stringify(m,null,2)],{type:"application/json"}),"produit.json"));
}

function showPreview(f,page=1){
 const url="/api"+pp()+"/files/"+f.id;
 if(f.info.ext!==".pdf"){modal(f.name,`<img class="preview" alt="Aperçu de ${esc(f.name)}" src="${url}?inline=true">`);return}
 const count=f.info.pages;
 modal(f.name,`<img class="preview" alt="Page ${page} du PDF" src="${url}/page/${page}"><div class="actions"><button id="previous" ${page<=1?"disabled":""}>Page précédente</button><span>${page} / ${count}</span><button id="next" ${page>=count?"disabled":""}>Page suivante</button></div>`);
 bind("#previous","click",()=>showPreview(f,page-1));bind("#next","click",()=>showPreview(f,page+1));
}


function files(){
 const active=p.files.filter(f=>f.active),older=p.files.filter(f=>!f.active);
 const compatible={etsy:["client","notice","preview"],paper:["interior","cover"],kindle:["ebook","cover"]}[p.manifest.channel];
 const roles=Object.fromEntries(["pending",...compatible,"source"].map(k=>[k,cfg.roles[k]]));
 function row(f){
   const details=f.info.error||[f.info.ext.toUpperCase().slice(1),Math.ceil(f.size/1024)+" Ko",f.info.pages?f.info.pages+" pages":"",f.info.pixels?f.info.pixels.join(" × ")+" px":""].filter(Boolean).join(" · ");
   return `<div class="row"><div><strong>${esc(f.name)}</strong><div class="sub">${esc(details)}</div></div><div class="line">${f.active?`<select data-role="${f.id}" aria-label="Rôle de ${esc(f.name)}">${opt(roles,f.role)}</select>`:""}${[".pdf",".png",".jpg",".jpeg"].includes(f.info.ext)&&!f.info.error?`<button data-preview="${f.id}">Aperçu</button>`:""}<a class="btn" href="/api${pp()}/files/${f.id}" download>Original</a>${f.active?`<button data-remove="${f.id}">Retirer</button>`:""}</div></div>`;
 }
 $("#content").innerHTML=`<section class="panel"><h2>Fichiers de l’édition</h2><div class="drop" id="zone"><b>Dépose ici les fichiers du produit</b><div class="sub">PDF, EPUB, images, archives, documents et tableurs. Les originaux sont conservés.</div><input id="browse" aria-label="Choisir des fichiers" type="file" multiple accept=".pdf,.epub,.png,.jpg,.jpeg,.zip,.xlsx,.ods,.txt,.md,.csv,.docx"></div>
 ${active.length?active.map(row).join(""):'<p class="muted">Aucun fichier associé.</p>'}
 ${older.length?`<details class="gap"><summary>Versions précédentes et fichiers retirés (${older.length})</summary>${older.map(row).join("")}</details>`:""}
 <button id="tochecks" class="primary gap">Contrôler le dossier</button></section>`;
 const upload=async list=>{if(!list.length)return;const data=new FormData();for(const f of list)data.append("files",f);$("#zone b").textContent="Importation et lecture des fichiers…";try{p=await api(pp()+"/files","POST",data,true);files();note("Fichiers enregistrés. Vérifie les rôles attribués.")}catch(e){files();throw e}};
 bind("#browse","change",(e,el)=>upload(el.files));const zone=$("#zone");
 for(const evt of ["dragover","dragleave","drop"])bind("#zone",evt,(e)=>{e.preventDefault();zone.classList.toggle("over",evt==="dragover");if(evt==="drop")return upload(e.dataTransfer.files)});
 bind("[data-role]","change",async(e,el)=>{p=await api(pp()+"/files/"+el.dataset.role,"PATCH",{role:el.value},true);files()});
 bind("[data-remove]","click",async(e,el)=>{if(!confirm("Retirer ce fichier de l’édition ? L’original restera consultable."))return;p=await api(pp()+"/files/"+el.dataset.remove,"DELETE",undefined,true);files()});
 bind("[data-preview]","click",(e,el)=>showPreview(p.files.find(x=>x.id===el.dataset.preview)));
 bind("#tochecks","click",()=>go(p.id,"controle"));
}
async function checks(){
 const report=await api(pp()+"/checks"),errors=report.filter(r=>r.level==="error").length;
 $("#content").innerHTML=`<section class="panel"><span class="upper">${esc(cfg.channels[p.manifest.channel])}</span><h2>Rapport de contrôle</h2><p>${errors?errors+" point(s) bloquant(s) à corriger avant le dépôt.":"Les fichiers passent les contrôles automatiques. Consulte les vérifications humaines avant le dépôt."}</p>${report.map(r=>`<div class="check ${r.level}"><b>${levels[r.level]}</b>${esc(r.text)}</div>`).join("")}<div class="actions"><button data-go="fiche">Modifier la fiche</button><button data-go="fichiers">Gérer les fichiers</button>${!errors?'<button class="primary" data-go="depot">Préparer le dépôt</button>':""}</div></section>`;
 bind("[data-go]","click",(e,el)=>go(p.id,el.dataset.go));
}
async function publication(){
 const m=p.manifest,etsy=m.channel==="etsy",report=await api(pp()+"/checks"),valid=!report.some(r=>r.level==="error");
 cfg=await api("/config");
 $("#content").innerHTML=`<section class="panel stack"><span class="upper">${etsy?"Etsy · annonce numérique":"Amazon KDP · publication assistée"}</span><h2>Dossier de dépôt</h2><p>Le ZIP réunit les fichiers à déposer, les métadonnées, le rapport et les étapes à suivre.</p><div class="line"><button id="export" class="primary" ${valid?"":"disabled"}>Télécharger le dossier ZIP</button><button id="checks">Voir les contrôles</button></div>${valid?"":'<p class="notice">Des erreurs bloquent la préparation du dossier.</p>'}
 <hr><h3>Suivi de publication</h3><p>État enregistré · <b>${esc(p.status)}</b> ${p.reference?" · "+esc(p.reference):""}</p><div class="line"><button id="openplatform">Ouvrir ${etsy?"Etsy Shop Manager":"la bibliothèque KDP"} ↗</button>${p.export_fingerprint?'<button id="manual">Confirmer un statut</button>':""}</div></section>${etsy?`<section class="panel gap stack"><h3>Connexion officielle Etsy</h3><p>${cfg.etsy.connected?"Boutique connectée · "+esc(cfg.etsy.shop):"Le dépôt manuel est disponible. La connexion API nécessite les accès de ta boutique."}</p><div class="line"><button id="connection">Gérer la connexion</button>${cfg.etsy.connected&&p.export_fingerprint?'<button id="remoteDraft">Créer ou reprendre le brouillon Etsy</button>':""}${cfg.etsy.connected&&p.status==="Dépôt en cours"&&p.reference?'<button id="remoteLive" class="warm">Activer l’annonce sur Etsy</button>':""}</div></section>`:""}`;
 if(etsy){
   const pending=await api(pp()+"/etsy-pending");
   if(pending.length){
     $("#content").insertAdjacentHTML("beforeend",`<section class="panel gap"><h3>Résultat Etsy à vérifier</h3><p>Contrôle le brouillon dans ta boutique avant toute reprise.</p>${pending.map(a=>`<div class="row"><strong>${esc(a.label)}</strong><button data-op="${esc(a.op)}">Rapprocher l’action</button></div>`).join("")}</section>`);
     bind("[data-op]","click",(e,el)=>{modal("Rapprocher avec la boutique",`<form id="reconcile" class="stack"><label>Résultat vérifié<select name="outcome"><option value="present">Présent, vérifier l’identifiant auprès d’Etsy</option>${el.dataset.op==="activate"?"":'<option value="absent">J’ai vérifié son absence dans Etsy</option>'}</select></label><label>Identifiant distant correspondant<input name="remote_id"></label><button class="primary">Enregistrer la vérification</button></form>`);
       bind("#reconcile","submit",async ev=>{ev.preventDefault();const f=new FormData(ev.target);p=await api(pp()+"/etsy-reconcile","POST",{op:el.dataset.op,remote_id:f.get("remote_id"),absent:f.get("outcome")==="absent",confirmed:true},true);close();await route()})});
   }
 }
 bind("#checks","click",()=>go(p.id,"controle"));bind("#connection","click",connection);
 bind("#openplatform","click",()=>{if(confirm("Ouvrir la plateforme externe dans un nouvel onglet ?"))window.open(etsy?"https://www.etsy.com/your/shops/me/dashboard":"https://kdp.amazon.com/bookshelf","_blank","noopener,noreferrer")});
 bind("#export","click",async(e,el)=>{el.disabled=true;try{const r=await api(pp()+"/export","POST",undefined,true,true);await downloadResponse(r,"Venture-dossier.zip");await route();note("Dossier préparé et téléchargé.")}finally{el.disabled=false}});
 bind("#manual","click",()=>{modal("Confirmer un statut",`<form id="statusform" class="stack"><p>Enregistre ce que tu as constaté sur la plateforme.</p><label>Statut observé<select name="state">${opt(dictionary(["Dépôt en cours","Soumis","En examen","Publié","Correction nécessaire"]),p.status)}</select></label><label>Référence, ASIN ou lien<input name="reference" value="${esc(p.reference)}"></label><button class="primary">Confirmer le statut observé</button></form>`);
 bind("#statusform","submit",async e=>{e.preventDefault();p=await api(pp()+"/status","POST",{...Object.fromEntries(new FormData(e.target)),confirmed:true},true);close();await route()})});
 bind("#remoteDraft","click",()=>{modal("Créer le brouillon sur Etsy",`<form id="draftetsy" class="stack"><p>Cette opération enverra les textes, les images et les fichiers client à la boutique ${esc(cfg.etsy.shop)}. Vérifie que le prix correspond à sa devise.</p><label>ID de catégorie Etsy<input name="taxonomy" type="number" min="1" required></label><label>Période de création Etsy<input name="when" required placeholder="Valeur acceptée par Etsy"></label><button class="primary">Confirmer l’envoi du brouillon</button></form>`);
 bind("#draftetsy","submit",async e=>{e.preventDefault();const data=Object.fromEntries(new FormData(e.target));p=await api(pp()+"/etsy/draft","POST",{taxonomy:Number(data.taxonomy),when:data.when,confirmed:true},true);close();await route()})});
 bind("#remoteLive","click",async()=>{if(confirm("Activer cette annonce réellement sur Etsy ? Cette action peut entraîner des frais.")){p=await api(pp()+"/etsy/publish","POST",{confirmed:true},true);await route()}});
}
async function connection(){
 cfg=await api("/config");
 if(!cfg.etsy.configured){
   modal("Configurer la session Etsy",`<form id="settings" class="stack"><p>Utilise les paramètres de ton application approuvée dans Etsy Developers. Ils resteront en mémoire pour cette session.</p><label>Clé API<input name="key" required autocomplete="off"></label><label>Secret partagé<input name="secret" type="password" required autocomplete="off"></label><label>Identifiant numérique de la boutique<input name="shop" inputmode="numeric" required></label><label>URI de retour HTTPS locale enregistrée<input name="redirect" type="url" value="https://localhost:8766/etsy-return" required></label><button class="primary">Utiliser pour cette session</button></form>`);
   bind("#settings","submit",async e=>{e.preventDefault();await api("/etsy/settings","POST",Object.fromEntries(new FormData(e.target)));await connection()});return
 }
 if(cfg.etsy.connected){modal("Boutique connectée",`<p>Boutique ${esc(cfg.etsy.shop)}</p><button id="disc">Déconnecter cette session</button>`);bind("#disc","click",async()=>{await api("/etsy/disconnect","POST");close();await route()});return}
 modal("Autoriser la connexion Etsy",`<div class="stack"><p>Ouvre l’autorisation officielle, puis colle ici l’adresse complète de retour locale affichée par ton navigateur. La connexion est conservée en mémoire jusqu’à l’arrêt de l’application.</p><button id="oauth">Ouvrir Etsy pour autoriser</button><form id="oauthform" class="stack"><label>Adresse de retour<input type="password" name="url" required autocomplete="off"></label><button class="primary">Terminer la connexion</button></form></div>`);
 bind("#oauth","click",async()=>{const url=(await api("/etsy/connect","POST",{confirmed:true})).url;const a=document.createElement("a");a.textContent="Continuer sur Etsy ↗";a.href=url;a.target="_blank";a.rel="noopener noreferrer";$("#oauth").replaceWith(a)});
 bind("#oauthform","submit",async e=>{e.preventDefault();await api("/etsy/return","POST",{url:e.target.url.value});close();await route();note("Boutique connectée.")});
}
async function historyPage(){
 const items=await api(pp()+"/history");
 $("#content").innerHTML=`<div class="panel"><h2>Historique de l’édition</h2>${items.map(i=>`<div class="row"><div><strong>${esc(i.message)}</strong><div class="sub">${esc(date(i.at))} · révision ${i.rev}</div></div><button data-snapshot="${i.rev}">Consulter la version</button></div>`).join("")}</div>`;
 bind("[data-snapshot]","click",async(e,el)=>{const x=await api(pp()+"/history/"+el.dataset.snapshot);modal("Version enregistrée · "+x.rev,`<pre>${esc(JSON.stringify(x,null,2))}</pre>`)});
}
bind("#dismiss","click",close);bind("#home","click",()=>go());
bind("#backup","click",async()=>{const r=await api("/backup","POST",undefined,false,true);await downloadResponse(r,"Venture-sauvegarde.zip");note("Sauvegarde complète téléchargée.")});
window.addEventListener("hashchange",()=>route().catch(e=>note(e.message,true)));
(async()=>{cfg=await api("/config");await route()})().catch(e=>{main.textContent=e.message});

