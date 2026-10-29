"use strict";

const $ = id => document.getElementById(id);
const state = { token:null, datasets:[], datasetId:null, versions:[], versionId:null, tab:"Data", dataView:"Table",
  preview:null, mapData:null, mapError:null, mapHandle:null, selectedFeature:null, selectedFeatureIndex:-1,
  comparison:null, fromId:null, toId:null, busy:null, pageError:null, downloadError:null, listError:null,
  inspectorOpen:true, generation:0, controllers:new Set() };
function el(tag, className="", value) { const n=document.createElement(tag); if(className)n.className=className; if(value!==undefined&&value!==null)n.textContent=String(value); return n; }
function add(parent,...children) { parent.append(...children); return parent; }
function button(label, className, handler) { const b=el("button",className,label); b.type="button"; b.addEventListener("click",handler); return b; }
function icon(name) { const image=el("img"); image.src=`/assets/icons/${name}.svg`; image.alt=""; image.width=17; image.height=17; return image; }
function display(v) { return v===null||v===undefined||v===""?"—":String(v); }
function num(v) { return typeof v==="number"?new Intl.NumberFormat().format(v):display(v); }
function date(v) { if(!v)return "—"; const d=new Date(v); return Number.isNaN(d.getTime())?String(v):new Intl.DateTimeFormat(undefined,{dateStyle:"medium",timeStyle:"short"}).format(d); }
function shortId(v) { return v?v.slice(0,11)+"…":"—"; }
function humanize(name) { const text=String(name||"").replace(/[_-]+/g," ").trim(); return text?text[0].toUpperCase()+text.slice(1):"—"; }
function dataset() { return state.datasets.find(d=>d.dataset_id===state.datasetId); }
function version() { return state.versions.find(v=>v.version_id===state.versionId); }
function sortedVersions() { return [...state.versions].sort((a,b)=>(Date.parse(b.created_at)||0)-(Date.parse(a.created_at)||0)); }
function versionLabel(v) { return `${date(v.created_at)}${v.version_id===dataset()?.current_version_id?" (current)":""} · ${shortId(v.version_id)}`; }
function disposeMap() { if(state.mapHandle){state.mapHandle.dispose();state.mapHandle=null;} }
function invalidate() { state.generation++; for(const c of state.controllers)c.abort(); state.controllers.clear(); disposeMap(); return state.generation; }
function errorText(e) { return e instanceof Error?e.message:"Request failed. Try again."; }
function spinner(label) { const n=el("div","loading"); add(n,el("span","spinner"),el("span","",label)); return n; }
function notice(text, className="notice") { return el("div",className,text); }
function errorPanel(text,retry) { const n=el("div","inline-error"); add(n,el("span","",text)); if(retry)add(n,button("Retry","outline-button",retry)); return n; }
function hasOmission(v) { if(!v||typeof v!=="object")return false; if(v.truncated===true)return true; return Object.values(v).some(hasOmission); }
function geometryLabel(value, name, geometryColumn) {
  const types={POINT:"Point",MULTIPOINT:"MultiPoint",LINESTRING:"LineString",MULTILINESTRING:"MultiLineString",POLYGON:"Polygon",MULTIPOLYGON:"MultiPolygon",GEOMETRYCOLLECTION:"GeometryCollection"};
  if(value&&typeof value==="object"&&types[String(value.type||"").toUpperCase()]&&(value.coordinates||value.geometries))return types[value.type.toUpperCase()];
  const text=typeof value==="string"?value.trim():"";
  const wkt=text.match(/^(?:SRID=\d+;)?\s*(POINT|MULTIPOINT|LINESTRING|MULTILINESTRING|POLYGON|MULTIPOLYGON|GEOMETRYCOLLECTION)(?:\s+(?:ZM|Z|M))?(?:\s*\(|\s+EMPTY\b)/i);
  if(wkt)return types[wkt[1].toUpperCase()];
  if(geometryColumn&&name===geometryColumn)return "Geometry";
  return null;
}

async function api(path,generation=state.generation,blob=false) {
  const c=new AbortController(); state.controllers.add(c);
  try {
    const response=await fetch(path,{headers:{Authorization:"Bearer "+state.token},signal:c.signal,cache:"no-store",credentials:"omit",mode:"same-origin"});
    if(generation!==state.generation)return null;
    if(response.status===401){signOut("The token was rejected or expired. Enter it again to reconnect.");return null;}
    if(!response.ok){let message=`Request failed (HTTP ${response.status}).`;try{const payload=await response.json();message=payload?.error?.message||message;}catch(_){}const error=new Error(message);error.status=response.status;throw error;}
    const result=blob?await response.blob():await response.json(); return generation===state.generation?result:null;
  } finally {state.controllers.delete(c);}
}
function signOut(note="") {
  invalidate(); state.token=null; state.datasets=[]; state.datasetId=null;state.versions=[];state.versionId=null;
  state.preview=null;state.mapData=null;state.mapError=null;state.selectedFeature=null;state.selectedFeatureIndex=-1;
  state.comparison=null;state.fromId=null;state.toId=null;state.busy=null;state.pageError=null;state.downloadError=null;state.listError=null;
  $("content").replaceChildren();$("inspector").replaceChildren();$("dataset-list").replaceChildren();$("search").value="";$("token").value="";
  $("app").hidden=true;$("signin").hidden=false;$("signin-error").textContent=note;$("signin-error").hidden=!note;$("signin-button").disabled=false;$("token").focus();
}
async function signIn(event) {
  event.preventDefault(); const token=$("token").value.trim();if(!token)return;
  state.token=token;$("token").value="";$("signin-button").disabled=true;$("signin-error").hidden=true;
  const gen=invalidate();
  try {const result=await api("/v1/datasets",gen);if(!result||gen!==state.generation)return;
    state.datasets=result.datasets||[];state.datasetId=state.datasets[0]?.dataset_id||null;
    $("signin").hidden=true;$("app").hidden=false;$("signin-button").disabled=false;
    renderCatalog();if(state.datasetId)await selectDataset(state.datasetId);else renderPage();
  } catch(error){if(gen!==state.generation)return;state.token=null;$("signin-button").disabled=false;$("signin-error").textContent=errorText(error);$("signin-error").hidden=false;$("token").focus();}
}
function toggleCatalog(force) {const open=force===undefined?$("catalog-menu").hidden:force;$("catalog-menu").hidden=!open;$("catalog-button").setAttribute("aria-expanded",String(open));$("dataset-picker").setAttribute("aria-expanded",String(open));if(open)$("search").focus();}
function renderCatalog() {
  $("picked-name").textContent=dataset()?.name||"Choose a dataset";
  const list=$("dataset-list"), focused=list.contains(document.activeElement)?document.activeElement.id:"";list.replaceChildren();
  const term=$("search").value.trim().toLowerCase(),matches=state.datasets.filter(d=>d.name.toLowerCase().includes(term));
  $("dataset-status").textContent=state.busy==="refresh"?"Refreshing…":state.listError||`${matches.length} ${matches.length===1?"dataset":"datasets"}`;
  $("refresh").disabled=state.busy==="refresh";
  if(!matches.length)add(list,el("div","catalog-status",state.datasets.length?"No matching datasets":"No accepted datasets yet"));
  for(const d of matches){const item=button("","dataset-item"+(d.dataset_id===state.datasetId?" selected":""),()=>{toggleCatalog(false);$("dataset-picker").focus();selectDataset(d.dataset_id);});item.id="dataset-"+d.dataset_id;item.disabled=state.busy==="refresh";if(d.dataset_id===state.datasetId)item.setAttribute("aria-current","page");add(item,el("strong","",d.name),el("small","",`${num(d.version_count)} accepted ${d.version_count===1?"version":"versions"}`));add(list,item);}
  if(focused)queueMicrotask(()=>{if(document.activeElement===document.body)$(focused)?.focus();});
}
async function refresh() {
  if(!state.token)return;const gen=invalidate(),previous=state.datasetId;state.listError=null;state.pageError=null;state.busy="refresh";renderCatalog();renderPage();
  try{const result=await api("/v1/datasets",gen);if(!result||gen!==state.generation)return;
    state.datasets=result.datasets||[];state.datasetId=state.datasets.some(d=>d.dataset_id===previous)?previous:state.datasets[0]?.dataset_id||null;
    if(state.datasetId)await selectDataset(state.datasetId);else{state.busy=null;state.versions=[];state.versionId=null;renderCatalog();renderPage();}
  }catch(error){if(gen!==state.generation)return;state.busy=null;state.listError=errorText(error);if(state.datasetId&&!state.versions.length)state.pageError=state.listError;renderCatalog();renderPage();}
}
async function selectDataset(id) {
  if(!state.datasets.some(d=>d.dataset_id===id))return;const gen=invalidate();state.datasetId=id;state.versions=[];state.versionId=null;
  state.preview=null;state.mapData=null;state.mapError=null;state.selectedFeature=null;state.selectedFeatureIndex=-1;state.comparison=null;state.pageError=null;state.downloadError=null;state.busy="versions";state.tab="Data";state.dataView="Table";
  renderCatalog();renderPage();
  try{const result=await api(`/v1/datasets/${id}/versions`,gen);if(!result||gen!==state.generation)return;
    state.versions=result.versions||[];const preferred=dataset()?.current_version_id;state.versionId=state.versions.some(v=>v.version_id===preferred)?preferred:sortedVersions()[0]?.version_id||null;
    state.fromId=sortedVersions()[1]?.version_id||sortedVersions()[0]?.version_id||null;state.toId=state.versionId;
    state.dataView=version()?.geometry_column?"Map":"Table";state.busy=null;renderPage();loadActive();
  }catch(error){if(gen===state.generation){state.busy=null;state.pageError=errorText(error);renderPage();}}
}
function selectVersion(id) {
  if(!state.versions.some(v=>v.version_id===id))return;invalidate();state.versionId=id;state.toId=id;state.preview=null;state.mapData=null;state.mapError=null;state.selectedFeature=null;state.selectedFeatureIndex=-1;state.comparison=null;state.pageError=null;state.downloadError=null;state.busy=null;
  renderPage();if(document.activeElement===document.body)$("version-choice")?.focus();loadActive();
}
function selectTab(tab) {if(state.tab===tab)return;invalidate();state.tab=tab;state.pageError=null;state.busy=null;renderPage();loadActive();}
function selectDataView(view) {if(state.dataView===view)return;invalidate();state.dataView=view;state.pageError=null;state.busy=null;renderPage();loadActive();}
function loadActive() {if(state.tab==="Data"){if(state.dataView==="Table"&&!state.preview)loadPreview();if(state.dataView==="Map"&&!state.mapData)loadMap();}if(state.tab==="Compare"&&state.fromId&&state.toId&&state.fromId!==state.toId)loadComparison();}
async function loadPreview() {
  if(!state.datasetId||!state.versionId)return;const gen=state.generation,id=state.datasetId,ver=state.versionId;
  state.busy="preview";state.pageError=null;renderPage();
  try{const result=await api(`/v1/datasets/${id}/versions/${ver}/preview?limit=25`,gen);if(!result||gen!==state.generation)return;state.preview=result;state.busy=null;renderPage();}
  catch(error){if(gen===state.generation){state.busy=null;state.pageError=errorText(error);renderPage();}}
}
async function loadMap() {
  if(!state.datasetId||!state.versionId)return;const gen=state.generation,id=state.datasetId,ver=state.versionId;
  state.busy="map";state.mapError=null;renderPage();
  try{const result=await api(`/v1/datasets/${id}/versions/${ver}/map?limit=500`,gen);if(!result||gen!==state.generation)return;state.mapData=result;state.busy=null;renderPage();}
  catch(error){if(gen!==state.generation)return;state.busy=null;state.mapError=errorText(error);if(error.status===422){state.dataView="Table";state.mapData=null;}renderPage();if(error.status===422&&!state.preview)loadPreview();}
}
async function loadComparison() {
  if(!state.datasetId||!state.fromId||!state.toId||state.fromId===state.toId)return;const gen=state.generation,id=state.datasetId;
  state.busy="compare";state.pageError=null;state.comparison=null;renderPage();
  try{const result=await api(`/v1/datasets/${id}/compare?from=${state.fromId}&to=${state.toId}`,gen);if(!result||gen!==state.generation)return;state.comparison=result;state.busy=null;renderPage();}
  catch(error){if(gen===state.generation){state.busy=null;state.pageError=errorText(error);renderPage();}}
}
function downloadState() {const b=$("download-version");if(b){b.disabled=Boolean(state.busy);b.lastChild.textContent=state.busy==="download"?"Downloading…":"Download Parquet";}const slot=$("download-error");if(slot){slot.replaceChildren();if(state.downloadError)add(slot,errorPanel("Download failed: "+state.downloadError,download));}}
async function download() {
  if(!state.datasetId||!state.versionId||state.busy)return;const gen=state.generation,id=state.datasetId,ver=state.versionId;
  state.busy="download";state.downloadError=null;downloadState();
  try{const blob=await api(`/v1/datasets/${id}/versions/${ver}/download`,gen,true);if(!blob||gen!==state.generation)return;const url=URL.createObjectURL(blob),link=document.createElement("a");link.href=url;link.download=ver+".parquet";document.body.append(link);link.click();link.remove();setTimeout(()=>URL.revokeObjectURL(url),60000);state.busy=null;downloadState();}
  catch(error){if(gen===state.generation){state.busy=null;state.downloadError=errorText(error);downloadState();}}
}

function table(headers,rows,className="") {
  const wrap=el("div","table-scroll"),t=el("table",className),head=el("thead"),tr=el("tr");
  for(const h of headers)add(tr,el("th","",h));
  add(head,tr);add(t,head);
  const body=el("tbody");
  for(const row of rows){
    const r=el("tr");
    for(const item of row){
      const value=String(item?.text??item??""),cell=el("td",item?.className||"");
      const compact=className==="data-table"&&(item?.geometryLabel||value.length>30||value.includes("\n"));
      if(compact){
        const details=el("details","cell-details");
        const label=item?.geometryLabel||value.slice(0,28)+"…";
        const full=el("div","cell-full",value);full.tabIndex=0;full.setAttribute("aria-label","Full cell value");
        add(details,el("summary","cell-summary",label),full);
        details.setAttribute("aria-label",item?.geometryLabel?`Show ${item.geometryLabel} value`:"Show full cell value");
        add(cell,details);
      }else add(cell,el("span","cell-value",value));
      add(r,cell);
    }
    add(body,r);
  }
  add(t,body);add(wrap,t);return wrap;
}
function versionSelect(selected,handler,label) {const s=el("select");s.setAttribute("aria-label",label);for(const v of sortedVersions()){const o=el("option","",versionLabel(v));o.value=v.version_id;o.title=v.version_id;o.selected=v.version_id===selected;add(s,o);}s.addEventListener("change",()=>handler(s.value));return s;}
function renderPage() {
  disposeMap();const root=$("content"),focusId=root.contains(document.activeElement)?document.activeElement.id:"";root.replaceChildren();if(focusId)queueMicrotask(()=>{if(document.activeElement===document.body)$(focusId)?.focus();});
  $("main").classList.toggle("inspector-hidden",!state.inspectorOpen);renderInspector();
  const d=dataset(),v=version();
  if(!state.inspectorOpen){const restore=button("Show details","outline-button restore-inspector",()=>{state.inspectorOpen=true;renderPage();$("hide-inspector")?.focus();});restore.id="show-inspector";add(root,restore);}
  if(!d){const empty=el("div","empty-state");add(empty,el("h2","","Your catalog is ready"),el("p","","Accepted datasets will appear here. To add one, use the Moses CLI load command, then refresh the catalog."),button("Browse catalog","outline-button",()=>toggleCatalog(true)));add(root,empty);return;}
  if(state.busy==="refresh"){add(root,spinner("Refreshing catalog…"));return;}
  if(state.busy==="versions"){add(root,spinner("Loading accepted versions…"));return;}
  if(state.pageError&&!v){add(root,errorPanel(state.pageError,()=>selectDataset(d.dataset_id)));return;}
  if(!v){add(root,notice("This dataset has no accepted versions yet."));return;}
  const tabs=el("div","tabs");tabs.setAttribute("role","tablist");tabs.setAttribute("aria-label","Dataset views");
  for(const [name,label] of [["Data","Data"],["Fields",`Fields (${num(v.schema?.length||0)})`],["History",`History (${num(state.versions.length)})`],["Compare","Compare"]]){
    const b=button(label,"tab"+(state.tab===name?" active":""),()=>selectTab(name));b.id="tab-"+name.toLowerCase();b.setAttribute("role","tab");b.setAttribute("aria-selected",String(state.tab===name));b.tabIndex=state.tab===name?0:-1;add(tabs,b);
  }
  tabs.addEventListener("keydown",event=>{if(!["ArrowLeft","ArrowRight","Home","End"].includes(event.key))return;event.preventDefault();const names=["Data","Fields","History","Compare"],i=names.indexOf(state.tab),n=event.key==="Home"?0:event.key==="End"?3:(i+(event.key==="ArrowRight"?1:3))%4;selectTab(names[n]);$("tab-"+names[n].toLowerCase())?.focus();});add(root,tabs);
  if(state.tab==="Data")renderData(root,v);else if(state.tab==="Fields")renderFields(root,v);else if(state.tab==="History")renderHistory(root);else renderCompare(root);
}
function renderToolbar(root) {
  const bar=el("div","data-toolbar"),seg=el("div","segmented");seg.setAttribute("aria-label","Data view");
  for(const name of ["Table","Map"]){const b=button(name,"segment"+(state.dataView===name?" active":""),()=>selectDataView(name));b.id="view-"+name.toLowerCase();b.setAttribute("aria-pressed",String(state.dataView===name));add(seg,b);}add(bar,seg,el("span","control-divider"));
  const ctrl=el("div","version-control"),label=el("label","","Version"),select=versionSelect(state.versionId,selectVersion,"Viewing version");label.htmlFor="version-choice";select.id="version-choice";add(ctrl,label,select);add(bar,ctrl);
  const dl=button("","dark-button download-button",download);dl.id="download-version";dl.disabled=Boolean(state.busy);dl.title=`Download exact version ${state.versionId}`;add(dl,icon("download"),el("span","",state.busy==="download"?"Downloading…":"Download Parquet"));add(bar,dl);
  add(root,bar);const errors=el("div");errors.id="download-error";if(state.downloadError)add(errors,errorPanel("Download failed: "+state.downloadError,download));add(root,errors);
}
function renderData(root,v) {
  renderToolbar(root);const note=el("div","data-note");
  if(state.dataView==="Table"){
    const p=state.preview;add(note,el("strong","","Table preview"),icon("info"),el("span","pipe"),el("span","note-copy",p?`Showing ${num(p.returned_rows)} of ${num(p.total_rows)} snapshot rows. Bounded to 25 rows and a 64 KB response.`:"Bounded to 25 rows and a 64 KB response."));
  }else{
    const m=state.mapData;add(note,el("strong","",m?`Map preview · ${num(m.returned_features)} features`:"Map preview"),icon("info"),el("span","pipe"),el("span","note-copy",m?`Scanned ${num(m.scanned_rows)} of ${num(m.total_rows)} snapshot rows. ${num(m.omitted_features)} rows omitted; ${num(m.unscanned_rows)} rows unscanned.`:"A bounded view of this accepted snapshot."));
  }add(root,note);const pane=el("div","view-content");pane.setAttribute("role","tabpanel");pane.setAttribute("aria-labelledby","tab-data");
  if(state.dataView==="Table")renderTable(pane,v);else renderMap(pane);add(root,pane);
}
function renderTable(root,v) {
  if(state.mapError)add(root,errorPanel("Map unavailable for this version: "+state.mapError));
  if(state.pageError){add(root,errorPanel(state.pageError,loadPreview));return;}
  if(state.busy==="preview"){add(root,spinner("Loading exact version preview…"));return;}
  if(!state.preview){add(root,button("Load preview","outline-button",loadPreview));return;}
  const p=state.preview,rows=p.rows||[];if(!rows.length){add(root,notice("No rows are available to preview."));return;}
  const columns=(v.schema||[]).map(f=>f.name),extra=[...new Set(rows.flatMap(r=>Object.keys(r)))].filter(k=>!columns.includes(k));columns.push(...extra);
  let omitted=false;const values=rows.map((row,i)=>[{text:String(i+1)},...columns.map(name=>{const value=row[name];if(value===null||value===undefined)return {text:"null",className:"empty-cell"};if(typeof value==="object"&&value.truncated&&value.byte_length!==undefined){omitted=true;return {text:`[cell omitted: ${num(value.byte_length)} bytes]`,className:"empty-cell"};}const label=geometryLabel(value,name,v.geometry_column);if(typeof value==="object"){if(value.base64)return {text:`[binary: ${value.base64.length} base64 characters]`,className:"empty-cell",geometryLabel:label};if(hasOmission(value))omitted=true;return {text:JSON.stringify(value),className:"code",geometryLabel:label};}return {text:String(value),geometryLabel:label};})]);
  if(omitted)add(root,notice("Some large cells or collection entries were omitted. Download the version for complete values."));add(root,table(["#",...columns],values,"data-table"));
}
function renderMap(root) {
  if(state.mapError){const wrap=el("div","map-error");add(wrap,errorPanel(state.mapError,loadMap),button("Return to table","outline-button",()=>selectDataView("Table")));add(root,wrap);return;}
  if(state.busy==="map"){add(root,spinner("Loading mapped features…"));return;}
  const data=state.mapData;if(!data){add(root,button("Load map","outline-button",loadMap));return;}
  const pane=el("div","map-pane"),tools=el("div","map-toolbar");
  add(tools,el("span","map-legend","Mapped features"));
  const featureLabel=el("label","","Feature"),featureSelect=el("select","feature-select");featureLabel.htmlFor="feature-choice";featureSelect.id="feature-choice";
  add(featureSelect,option("Choose a feature",-1));data.features.forEach((feature,i)=>add(featureSelect,option(featureLabelText(feature,i),i)));
  featureSelect.value=String(state.selectedFeatureIndex);featureSelect.addEventListener("change",()=>{const i=Number(featureSelect.value);if(i>=0)state.mapHandle?.select(i);else{state.mapHandle?.clearSelection();state.selectedFeature=null;state.selectedFeatureIndex=-1;renderInspector();}});
  add(tools,add(el("div","map-field"),featureLabel,featureSelect));
  const baseLabel=el("label","","Basemap"),base=el("select","basemap-select");base.id="basemap-choice";baseLabel.htmlFor=base.id;add(base,option("None (offline)","none"),option("OpenStreetMap (online)","osm"));base.addEventListener("change",()=>state.mapHandle?.basemap(base.value==="osm"));add(tools,add(el("div","map-field"),baseLabel,base));add(pane,tools);
  add(pane,el("div","map-disclosure","Choosing OpenStreetMap sends this page’s origin and viewport tile requests to OpenStreetMap."));
  const area=el("div","map-region"),canvas=el("div","map-canvas");canvas.id="map-canvas";canvas.setAttribute("aria-label",`Map of ${num(data.returned_features)} returned features`);add(area,canvas);
  const controls=el("div","map-controls");for(const [name,title,run] of [["plus","Zoom in",()=>state.mapHandle?.zoomIn()],["minus","Zoom out",()=>state.mapHandle?.zoomOut()]]){const b=button("","",run);b.setAttribute("aria-label",title);b.title=title;add(b,icon(name));add(controls,b);}const fit=button("","fit-button",()=>state.mapHandle?.fit());fit.setAttribute("aria-label","Fit mapped features");add(fit,icon("maximize"),el("span","","Fit features"));add(controls,fit);add(area,controls);add(pane,area);
  const footer=el("div","map-footer",`Display: ${display(data.display_crs)} · Source: ${display(data.source_crs)} · ${num(data.scanned_rows)} scanned · ${num(data.omitted_features)} rows omitted`);add(pane,footer);
  const reasons=Object.entries(data.omissions||{}).filter(([,count])=>count>0).map(([reason,count])=>`Geometry ${reason.replaceAll("_"," ")}: ${num(count)}`);
  const propertyReasons=Object.entries(data.property_omissions||{}).filter(([,count])=>count>0).map(([reason,count])=>`${reason.replaceAll("_"," ")}: ${num(count)}`);
  const warnings=(data.warnings||[]).filter(text=>!text.includes("property_omissions"));
  if(warnings.length||reasons.length||propertyReasons.length||data.truncated)add(pane,notice([...warnings,...reasons,propertyReasons.length?`Property omissions: ${propertyReasons.join(", ")}`:"",data.truncated?"This is a bounded map preview, not complete source coverage.":""].filter(Boolean).join(" · ")));
  if(!data.features.length)add(pane,notice("No mappable features were returned in this bounded preview."));
  add(root,pane);activateMap(canvas,data);
}
function option(label,value) {const o=el("option","",label);o.value=String(value);return o;}
function featureLabelText(feature,index) {
  const props=feature.properties||{},preferred=version()?.key;
  const match=preferred&&Object.hasOwn(props,preferred)?preferred:Object.keys(props).find(k=>["name","lm_name","title","label","display_name"].includes(k.toLowerCase()));
  const value=match?props[match]:undefined;
  if(value!==null&&value!==undefined&&typeof value!=="object"&&String(value).trim())return `Feature ${index+1} · ${match}: ${String(value).slice(0,45)}`;
  const row=Number.isInteger(feature.id)?feature.id+1:feature.id;
  return `Feature ${index+1} · source row ${display(row)}`;
}
async function activateMap(canvas,data) {
  const gen=state.generation;
  try{const module=await import("/assets/map.js");if(gen!==state.generation||!canvas.isConnected)return;
    const handle=await module.mountMap(canvas,data,(index,feature)=>{if(gen!==state.generation)return;state.selectedFeatureIndex=index;state.selectedFeature=feature;const choice=$("feature-choice");if(choice)choice.value=String(index);renderInspector();});
    if(gen!==state.generation||!canvas.isConnected){handle.dispose();return;}state.mapHandle=handle;handle.basemap($("basemap-choice")?.value==="osm");if(state.selectedFeatureIndex>=0)handle.select(state.selectedFeatureIndex);
  }catch(error){if(gen!==state.generation)return;state.mapError=errorText(error);state.mapData=null;renderPage();}
}
function renderFields(root,v) {const pane=el("div","view-content pane-padding");pane.setAttribute("role","tabpanel");pane.setAttribute("aria-labelledby","tab-fields");add(pane,el("h2","",`Fields · ${num(v.schema?.length||0)}`));const fields=v.schema||[];if(fields.length)add(pane,table(["Field","Type","Nullable"],fields.map(f=>[f.name,f.type,f.nullable?"Yes":"No"]),"schema-table"));else add(pane,notice("No fields are available for this version."));add(root,pane);}
function renderHistory(root) {const pane=el("div","view-content pane-padding");pane.setAttribute("role","tabpanel");pane.setAttribute("aria-labelledby","tab-history");add(pane,el("h2","",`Accepted version history · ${num(state.versions.length)}`),notice("Versions are ordered by acceptance time. Version IDs are opaque identifiers."));const list=el("div","history-list");for(const v of sortedVersions()){const item=el("div","history-item"),text=el("div"),title=el("strong","",date(v.created_at));if(v.version_id===dataset()?.current_version_id)add(title,el("span","badge","Current"));add(text,title,el("small","",`${v.version_id} · ${num(v.row_count)} rows`));const b=button(v.version_id===state.versionId?"Viewing":"View version","outline-button",()=>selectVersion(v.version_id));b.disabled=v.version_id===state.versionId;add(item,text,b);add(list,item);}add(pane,list);add(root,pane);}
function renderCompare(root) {const pane=el("div","view-content pane-padding");pane.setAttribute("role","tabpanel");pane.setAttribute("aria-labelledby","tab-compare");add(pane,el("h2","","Compare accepted versions"));if(state.versions.length<2){add(pane,notice("Accept another version of this dataset to compare releases."));add(root,pane);return;}
  const controls=el("div","compare-controls");for(const [label,key] of [["From","fromId"],["To","toId"]]){const group=el("div"),caption=el("label","",label),select=versionSelect(state[key],value=>{invalidate();state[key]=value;state.comparison=null;state.pageError=null;state.busy=null;renderPage();},label+" version");select.id="compare-"+key;caption.htmlFor=select.id;add(group,caption,select);add(controls,group);}const run=button("Compare","dark-button",loadComparison);run.disabled=!state.fromId||!state.toId||state.fromId===state.toId||state.busy==="compare";add(controls,run);add(pane,controls);
  if(state.fromId===state.toId)add(pane,notice("Choose two different accepted versions."));else if(state.pageError)add(pane,errorPanel(state.pageError,loadComparison));else if(state.busy==="compare")add(pane,spinner("Comparing accepted snapshots…"));else if(state.comparison){const r=state.comparison,figures=el("div","compare-summary");for(const [name,value] of [["Added",num(r.added)],["Removed",num(r.removed)],["Changed",r.key?num(r.changed):"N/A"]]){const box=el("div","count-box");add(box,el("small","",name),el("strong","",value));add(figures,box);}add(pane,figures,notice(`Key: ${display(r.key)} · Schema ${r.schema_changed?"changed":"unchanged"} · CRS ${r.crs_changed?"changed":"unchanged"}.`));if(r.crs_changed)add(pane,notice(`CRS: ${display(r.old_crs)} to ${display(r.new_crs)}`));if(!r.key)add(pane,notice("Without a key, changed rows cannot be identified as updates. Added and removed counts compare row values."));if(r.schema_changed){for(const [title,fields] of [["From schema",r.old_schema],["To schema",r.new_schema]]){add(pane,el("h3","",title),table(["Field","Type","Nullable"],(fields||[]).map(f=>[f.name,f.type,f.nullable?"Yes":"No"]),"schema-table"));}}}
  add(root,pane);
}
function detailList(items) {const dl=el("dl","detail-list");for(const [name,value,cls] of items){const row=el("div","detail-row");add(row,el("dt","",name),el("dd",cls||"",display(value)));add(dl,row);}return dl;}
function geometryType(feature) {return feature?.geometry?.type||"—";}
function renderInspector() {const side=$("inspector");side.replaceChildren();if(!state.inspectorOpen)return;const d=dataset(),v=version();
  const head=el("div","inspector-head");add(head,el("h2","","Dataset details"));const close=button("","inspector-close",()=>{state.inspectorOpen=false;renderPage();$("show-inspector")?.focus();});close.id="hide-inspector";close.setAttribute("aria-label","Hide dataset details");add(close,icon("x"));add(head,close);add(side,head);
  if(!d){add(side,el("div","inspector-body","Choose a dataset to inspect its accepted releases."));return;}
  const body=el("div","inspector-body");add(body,el("h2","inspector-title",humanize(d.name)),el("p","inspector-id",d.name));
  if(v){add(body,detailList([["Rows",num(v.row_count)],["Fields",num(v.schema?.length||0)],["Format",v.format],["Source CRS",v.crs],["Geometry column",v.geometry_column],["Current version",date(state.versions.find(item=>item.version_id===d.current_version_id)?.created_at)]]));
    const sample=el("section","inspector-section");add(sample,el("h3","","Preview scope"),el("p","","Counts describe accepted warehouse snapshots. A bounded preview does not establish coverage of the original source."));add(body,sample);
    const props=el("section","inspector-section");add(props,el("h3","","Feature properties"));if(state.selectedFeature){const feature=state.selectedFeature,fields=Object.entries(feature.properties||{}).map(([name,value])=>[name,typeof value==="object"?JSON.stringify(value):value]);add(props,detailList([["Geometry",geometryType(feature)],...fields]));}else{const empty=el("div","feature-empty");add(empty,el("strong","","Select a feature on the map"),el("span","","Click a feature, or use the feature selector above the map, to inspect its returned properties."));add(props,empty);}add(body,props);
    const technical=el("details","technical");add(technical,el("summary","","Technical details"),detailList([["Dataset ID",d.dataset_id,"code"],["Version ID",v.version_id,"code"],["Accepted",date(v.created_at)],["Key field",v.key],["CRS source",v.crs_source],["Layer",v.layer],["Source SHA-256",v.source_sha256,"hash"],["Content SHA-256",v.content_sha256,"hash"]]));add(body,technical);
  }else add(body,notice("Loading version details…"));add(side,body);
}

$("signin-form").addEventListener("submit",signIn);$("signout").addEventListener("click",()=>signOut());$("catalog-button").addEventListener("click",()=>toggleCatalog());$("dataset-picker").addEventListener("click",()=>toggleCatalog());$("refresh").addEventListener("click",refresh);$("search").addEventListener("input",renderCatalog);
document.addEventListener("click",event=>{if(!$("catalog-menu").hidden&&!event.target.closest(".catalog-picker")&&!event.target.closest("#catalog-button"))toggleCatalog(false);});document.addEventListener("keydown",event=>{if(event.key==="Escape"&&!$("catalog-menu").hidden){toggleCatalog(false);$("dataset-picker").focus();}});
