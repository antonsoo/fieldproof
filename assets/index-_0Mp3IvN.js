(function(){const t=document.createElement("link").relList;if(t&&t.supports&&t.supports("modulepreload"))return;for(const o of document.querySelectorAll('link[rel="modulepreload"]'))r(o);new MutationObserver(o=>{for(const s of o)if(s.type==="childList")for(const i of s.addedNodes)i.tagName==="LINK"&&i.rel==="modulepreload"&&r(i)}).observe(document,{childList:!0,subtree:!0});function n(o){const s={};return o.integrity&&(s.integrity=o.integrity),o.referrerPolicy&&(s.referrerPolicy=o.referrerPolicy),o.crossOrigin==="use-credentials"?s.credentials="include":o.crossOrigin==="anonymous"?s.credentials="omit":s.credentials="same-origin",s}function r(o){if(o.ep)return;o.ep=!0;const s=n(o);fetch(o.href,s)}})();async function $(e){if(!e.ok){const t=await e.json().catch(()=>({detail:e.statusText}));throw new Error(typeof t.detail=="string"?t.detail:e.statusText)}return await e.json()}class C{kind="demo";cache=new Map;storageKey(t){return`fieldproof-demo-review:${t}`}loadReviewOverlay(t){try{const n=localStorage.getItem(this.storageKey(t));return n?JSON.parse(n):{}}catch{return{}}}saveReviewOverlay(t,n){try{localStorage.setItem(this.storageKey(t),JSON.stringify(n))}catch{}}async listSamples(){const t=await fetch("/fieldproof/demo-data/index.json");return $(t)}async fetchSample(t){const n=this.cache.get(t);if(n)return n;const r=await fetch(`/fieldproof/demo-data/${t}/data.json`),o=await $(r);return this.cache.set(t,o),o}async loadSample(t){const n=await this.fetchSample(t),r=this.loadReviewOverlay(t);return{document:n.document,extraction:{...n.extraction,review:{...n.extraction.review,...r}}}}async listSchemas(){return["invoice","receipt","contract"]}async uploadDocument(){throw new Error("Uploading isn't available in the static demo - see the README to run fieldproof locally.")}pageImageUrl(t,n){return`/fieldproof/demo-data/${t}/page-${n}.png`}async extract(){throw new Error("Re-extracting isn't available in the static demo.")}async review(t,n,r,o){const s=this.loadReviewOverlay(t),i={status:r==="approve"?"approved":r==="edit"?"edited":r==="reject"?"rejected":"pending",edited_value:r==="edit"?o??null:null};return s[n]=i,this.saveReviewOverlay(t,s),i}exportUrl(){return""}}function D(){return new C}function H(e){const t=[];for(const n of e.report.fields){const r=e.review[n.path]??{status:"pending",edited_value:null};r.status!=="rejected"&&t.push({field:n.path,value:r.status==="edited"?r.edited_value:n.value,verification_status:n.status,review_status:r.status,page:n.page})}return t}function U(e){const t="field,value,verification_status,review_status,page",n=o=>{const s=o==null?"":String(o);return/[",\n]/.test(s)?`"${s.replace(/"/g,'""')}"`:s},r=e.map(o=>[o.field,o.value,o.verification_status,o.review_status,o.page].map(n).join(","));return[t,...r].join(`\r
`)+`\r
`}function E(e,t,n){const r=new Blob([t],{type:n}),o=URL.createObjectURL(r),s=document.createElement("a");s.href=o,s.download=e,document.body.appendChild(s),s.click(),s.remove(),URL.revokeObjectURL(o)}const B=["invoice","receipt","contract"],M=2,d=D(),a={document:null,extraction:null,currentPage:1,zoom:1,zoomIsAuto:!0,selectedPath:null,statusFilter:"all",searchQuery:"",editingPath:null,schemaName:"invoice",provider:"fixture",fixtureFile:null,busy:!1,samples:[]},A=document.getElementById("app");function c(e){return String(e).replace(/&/g,"&amp;").replace(/</g,"&lt;").replace(/>/g,"&gt;").replace(/"/g,"&quot;")}function J(e){return e==="needs_review"?"needs review":e}const V=new Set(["amount","subtotal","tax","total","unit_price","total_contract_value"]);function K(e){const t=e.split(".").pop()??"";return V.has(t.replace(/\[\d+\]$/,""))}function Q(e,t){if(K(e)){const n=typeof t=="number"?t:Number(t);if(Number.isFinite(n))return n.toLocaleString("en-US",{minimumFractionDigits:2,maximumFractionDigits:2})}return String(t)}let S;function h(e){let t=document.getElementById("toast");t||(t=document.createElement("div"),t.id="toast",t.className="toast",t.setAttribute("role","status"),t.setAttribute("aria-live","polite"),document.body.appendChild(t)),t.textContent=e,t.classList.add("is-visible"),window.clearTimeout(S),S=window.setTimeout(()=>t?.classList.remove("is-visible"),2600)}function F(){const e=document.documentElement.getAttribute("data-theme");return e==="light"||e==="dark"?e:window.matchMedia("(prefers-color-scheme: dark)").matches?"dark":"light"}function W(){const e=F()==="dark"?"light":"dark";document.documentElement.setAttribute("data-theme",e);try{localStorage.setItem("fieldproof-theme",e)}catch{}m()}function m(){let e=document.querySelector(".topbar");e||(e=document.createElement("header"),e.className="topbar",A.prepend(e));const t=a.extraction?.report.counts,n=t?`<span class="brand-tag" aria-hidden="true">${t.verified}&nbsp;verified&ensp;${t.needs_review}&nbsp;review&ensp;${t.unsupported}&nbsp;unsupported</span>`:`<span class="brand-tag">${d.kind==="demo"?"static demo - fixture data":"grounded document review"}</span>`;e.innerHTML=`
    <div class="brand">
      <span class="brand-mark">fieldproof</span>
      ${n}
    </div>
    <div class="topbar-controls">
      ${a.extraction?Z():""}
      <button class="btn" id="theme-toggle" type="button" aria-label="Toggle dark mode">
        ${F()==="dark"?"☀️ Light":"☽ Dark"}
      </button>
    </div>
  `,e.querySelector("#theme-toggle")?.addEventListener("click",W),e.querySelector("#export-json")?.addEventListener("click",()=>L("json")),e.querySelector("#export-csv")?.addEventListener("click",()=>L("csv"))}function Z(){return`
    <button class="btn" id="export-json" type="button">Export JSON</button>
    <button class="btn" id="export-csv" type="button">Export CSV</button>
  `}async function L(e){if(!a.document||!a.extraction)return;const t=a.document.filename.replace(/\.pdf$/i,"");if(d.kind==="live"){window.open(d.exportUrl(a.document.id,e),"_blank");return}const n=H(a.extraction);e==="json"?E(`${t}.fieldproof.json`,JSON.stringify(n,null,2),"application/json"):E(`${t}.fieldproof.csv`,U(n),"text/csv"),h(`Exported ${n.length} field${n.length===1?"":"s"}`)}async function j(){const e=y();if(d.kind==="demo"){a.samples.length===0&&(a.samples=await d.listSamples?.()??[]),e.innerHTML=`
      <div class="start-state">
        <div class="proof-ticks" aria-hidden="true">
          <span class="proof-tick"><span class="proof-dot" style="background:var(--color-verified)"></span>verified</span>
          <span class="proof-tick"><span class="proof-dot" style="background:var(--color-review)"></span>needs review</span>
          <span class="proof-tick"><span class="proof-dot" style="background:var(--color-unsupported)"></span>unsupported</span>
        </div>
        <h1>Every field, traced to its source</h1>
        <p>
          Three synthetic sample documents, grounded and verified by fieldproof's real pipeline.
          The candidate extractions are hand-written fixtures with planted errors, to show what the verifier catches -
          a hallucinated PO number, a total that doesn't match its line items, and a misread date.
        </p>
        <div class="sample-grid">
          ${a.samples.map(r=>`<button class="btn btn-primary" type="button" data-sample="${c(r.id)}">${c(r.label)}</button>`).join("")}
        </div>
      </div>
    `,e.querySelectorAll("[data-sample]").forEach(r=>{r.addEventListener("click",()=>Y(r.dataset.sample))});return}e.innerHTML=`
    <div class="start-state">
      <h1>Upload a document</h1>
      <p>PDF with a text layer. Extraction runs against the fixture provider or Claude, then every field is grounded and verified against the page.</p>
      <label class="dropzone" id="dropzone" for="file-input">
        Drop a PDF here, or click to choose one
      </label>
      <input type="file" id="file-input" accept="application/pdf" class="visually-hidden" />
    </div>
  `;const t=e.querySelector("#file-input"),n=e.querySelector("#dropzone");t.addEventListener("change",()=>{t.files?.[0]&&k(t.files[0])}),n.addEventListener("dragover",r=>{r.preventDefault(),n.classList.add("dragover")}),n.addEventListener("dragleave",()=>n.classList.remove("dragover")),n.addEventListener("drop",r=>{r.preventDefault(),n.classList.remove("dragover");const o=r.dataTransfer?.files?.[0];o&&k(o)})}async function Y(e){if(!d.loadSample)return;const{document:t,extraction:n}=await d.loadSample(e);a.document=t,a.extraction=n,a.currentPage=1,a.zoomIsAuto=!0,a.selectedPath=null,a.statusFilter="all",a.searchQuery="",m(),u()}async function k(e){try{a.document=await d.uploadDocument(e),a.extraction=null,a.currentPage=1,a.zoomIsAuto=!0,m(),u()}catch(t){h(t instanceof Error?t.message:"Upload failed")}}function z(){const e=y();e.innerHTML=`
    <div class="start-state">
      <h1>${c(a.document.filename)}</h1>
      <p>${a.document.page_count} page${a.document.page_count===1?"":"s"} loaded. Choose a schema and a provider to extract.</p>
      <div style="display:flex; flex-direction:column; gap:12px; text-align:left; max-width:360px; margin:0 auto;">
        <label>
          Schema
          <select class="select" id="schema-select" style="width:100%">
            ${B.map(s=>`<option value="${s}" ${s===a.schemaName?"selected":""}>${s}</option>`).join("")}
          </select>
        </label>
        <label>
          Provider
          <select class="select" id="provider-select" style="width:100%">
            <option value="fixture" ${a.provider==="fixture"?"selected":""}>fixture (replay stored JSON)</option>
            <option value="anthropic" ${a.provider==="anthropic"?"selected":""}>anthropic (needs ANTHROPIC_API_KEY on the server)</option>
          </select>
        </label>
        <label id="fixture-label" ${a.provider==="fixture"?"":"hidden"}>
          Fixture JSON
          <input type="file" class="text-input" id="fixture-input" accept="application/json" style="width:100%" />
        </label>
        <button class="btn btn-primary" id="run-extract" type="button" ${a.busy?"disabled":""}>
          ${a.busy?"Extracting…":"Run extraction"}
        </button>
      </div>
    </div>
  `;const t=e.querySelector("#schema-select"),n=e.querySelector("#provider-select"),r=e.querySelector("#fixture-label"),o=e.querySelector("#fixture-input");t.addEventListener("change",()=>{a.schemaName=t.value}),n.addEventListener("change",()=>{a.provider=n.value,r.hidden=a.provider!=="fixture"}),o.addEventListener("change",()=>{a.fixtureFile=o.files?.[0]??null}),e.querySelector("#run-extract").addEventListener("click",G)}async function G(){if(a.document){if(a.provider==="fixture"&&!a.fixtureFile){h("Choose a fixture JSON file first");return}a.busy=!0,z();try{a.extraction=await d.extract(a.document.id,a.schemaName,a.provider,a.fixtureFile),a.currentPage=1,a.zoomIsAuto=!0,m()}catch(e){h(e instanceof Error?e.message:"Extraction failed")}finally{a.busy=!1,u()}}}function y(){let e=document.querySelector(".workbench");return e||(e=document.createElement("main"),e.className="workbench",A.appendChild(e)),e}const P={unsupported:0,needs_review:1,verified:2};function I(){const e=a.extraction?.report.fields??[],t=a.searchQuery.trim().toLowerCase(),n=e.filter(r=>a.statusFilter!=="all"&&r.status!==a.statusFilter?!1:t?r.path.toLowerCase().includes(t)||String(r.value).toLowerCase().includes(t):!0);return a.statusFilter!=="all"?n:[...n].sort((r,o)=>P[r.status]-P[o.status])}function u(){if(!a.document){j();return}if(!a.extraction){z();return}const e=y();e.innerHTML=`
    <section class="viewer-pane" aria-label="Document page">
      <div class="viewer-toolbar">
        <button class="btn" id="prev-page" type="button" ${a.currentPage<=1?"disabled":""}>←</button>
        <span>Page ${a.currentPage} / ${a.document.page_count}</span>
        <button class="btn" id="next-page" type="button" ${a.currentPage>=a.document.page_count?"disabled":""}>→</button>
        <span style="flex:1"></span>
        <button class="btn" id="zoom-out" type="button" aria-label="Zoom out">−</button>
        <span id="zoom-label">${Math.round(a.zoom*100)}%</span>
        <button class="btn" id="zoom-in" type="button" aria-label="Zoom in">+</button>
      </div>
      <div class="viewer-scroll" id="viewer-scroll">
        ${q()}
      </div>
    </section>
    <section class="field-pane" aria-label="Extracted fields">
      ${X()}
      <ul class="field-list" id="field-list" tabindex="0" aria-label="Fields (arrow keys to navigate, a to approve, r to reject)">
        ${N()}
      </ul>
    </section>
  `,te(),a.zoomIsAuto&&T()}function T(){const e=document.getElementById("viewer-scroll"),t=a.document?.pages.find(l=>l.number===a.currentPage);if(!e||!t)return;const n=t.width*M,r=e.clientWidth-48,o=Math.min(1,Math.max(.35,r/n)),s=Math.round(o*100)/100;if(s===a.zoom)return;a.zoom=s,e.innerHTML=q(),e.scrollLeft=0,e.scrollTop=0,O();const i=document.getElementById("zoom-label");i&&(i.textContent=`${Math.round(a.zoom*100)}%`)}window.addEventListener("resize",()=>{a.zoomIsAuto&&T()});function q(){const e=a.document.pages.find(i=>i.number===a.currentPage),t=M*a.zoom,n=Math.round(e.width*t),r=Math.round(e.height*t),s=(a.extraction?.report.fields??[]).filter(i=>i.page===a.currentPage).flatMap(i=>i.rects.map(l=>({rect:l,field:i}))).map(({rect:i,field:l})=>{const p=i.x0*t,v=i.top*t,w=(i.x1-i.x0)*t,R=(i.bottom-i.top)*t;return`<div class="highlight-rect ${l.path===a.selectedPath?"is-active":""}" data-status="${l.status}" data-path="${c(l.path)}"
        style="left:${p}px; top:${v}px; width:${w}px; height:${R}px"
        title="${c(l.path)}"></div>`}).join("");return`
    <div class="page-frame" id="page-frame" style="width:${n}px; height:${r}px;">
      <img src="${d.pageImageUrl(a.document.id,a.currentPage)}" width="${n}" height="${r}" alt="Page ${a.currentPage} of ${c(a.document.filename)}" />
      ${s}
    </div>
  `}function X(){const e=a.extraction.report.counts,t=(n,r,o)=>`
    <button class="count-chip ${a.statusFilter===n?"is-active":""}" data-status-filter="${n}"
      data-status="${n==="all"?"":n}" type="button">
      ${c(r)} ${o}
    </button>
  `;return`
    <div class="field-pane-header">
      <div class="counts-strip">
        ${t("all","All",a.extraction.report.fields.length)}
        ${t("verified","Verified",e.verified)}
        ${t("needs_review","Needs review",e.needs_review)}
        ${t("unsupported","Unsupported",e.unsupported)}
      </div>
      <div class="filter-row">
        <input class="text-input" id="search-input" type="search" placeholder="Search fields…" value="${c(a.searchQuery)}" />
      </div>
    </div>
  `}function N(){const e=I();return e.length===0?'<li class="empty-filtered">No fields match this filter.</li>':e.map(t=>ee(t)).join("")}function ee(e){const t=a.extraction.review[e.path]??{status:"pending",edited_value:null},n=e.path===a.selectedPath,r=t.status==="edited"?t.edited_value:e.value,o=a.editingPath===e.path,s=e.reasons.length>0?`<ul class="field-reasons">${e.reasons.map(p=>`<li>${c(p)}</li>`).join("")}</ul>`:"",i=e.matched_text?`<div class="field-evidence">“${c(e.matched_text)}”${e.match_score!==null&&e.match_score<100?` <span style="opacity:.7">(${Math.round(e.match_score)}% match)</span>`:""}</div>`:"",l=o?`<div class="edit-row">
        <input class="text-input" id="edit-input-${c(e.path)}" value="${c(r)}" />
        <button class="btn btn-primary" type="button" data-save="${c(e.path)}">Save</button>
        <button class="btn" type="button" data-cancel-edit>Cancel</button>
      </div>`:"";return`
    <li class="field-row ${n?"is-selected":""}" data-path="${c(e.path)}" aria-current="${n?"true":"false"}">
      <div class="field-row-top">
        <span class="field-path">${c(e.path)}</span>
        <span class="status-chip" data-status="${e.status}">${J(e.status)}</span>
      </div>
      <div class="field-value ${t.status==="edited"?"is-edited":""}">${c(Q(e.path,r))}</div>
      ${t.status!=="pending"?`<span class="review-badge">${t.status}</span>`:""}
      ${s}
      ${i}
      ${o?l:`<div class="field-actions">
              <button class="btn" type="button" data-approve="${c(e.path)}">Approve</button>
              <button class="btn" type="button" data-edit="${c(e.path)}">Edit</button>
              <button class="btn" type="button" data-reject="${c(e.path)}">Reject</button>
              ${t.status!=="pending"?`<button class="btn" type="button" data-reset="${c(e.path)}">Reset</button>`:""}
            </div>`}
    </li>
  `}function O(){document.querySelectorAll(".highlight-rect").forEach(e=>{e.addEventListener("click",()=>g(e.dataset.path,{pulse:!0})),e.addEventListener("mouseenter",()=>_(e.dataset.path,!0)),e.addEventListener("mouseleave",()=>_(e.dataset.path,!1))})}function te(){const e=y();e.querySelector("#prev-page")?.addEventListener("click",()=>{a.currentPage=Math.max(1,a.currentPage-1),u()}),e.querySelector("#next-page")?.addEventListener("click",()=>{a.currentPage=Math.min(a.document.page_count,a.currentPage+1),u()}),e.querySelector("#zoom-in")?.addEventListener("click",()=>{a.zoomIsAuto=!1,a.zoom=Math.min(3,Math.round((a.zoom+.25)*100)/100),u()}),e.querySelector("#zoom-out")?.addEventListener("click",()=>{a.zoomIsAuto=!1,a.zoom=Math.max(.35,Math.round((a.zoom-.25)*100)/100),u()}),O(),e.querySelectorAll(".count-chip").forEach(r=>{r.addEventListener("click",()=>{a.statusFilter=r.dataset.statusFilter??"all",u()})});const t=e.querySelector("#search-input");t?.addEventListener("input",()=>{a.searchQuery=t.value,b()});const n=e.querySelector("#field-list");n.addEventListener("click",r=>ae(r)),n.addEventListener("keydown",r=>re(r))}function ae(e){const t=e.target,n=t.closest("[data-approve]"),r=t.closest("[data-edit]"),o=t.closest("[data-reject]"),s=t.closest("[data-reset]"),i=t.closest("[data-save]"),l=t.closest("[data-cancel-edit]"),p=t.closest(".field-row");if(n)return void f(n.dataset.approve,"approve");if(o)return void f(o.dataset.reject,"reject");if(s)return void f(s.dataset.reset,"reset");if(r){a.editingPath=r.dataset.edit,b();return}if(l){a.editingPath=null,b();return}if(i){const v=i.dataset.save,w=document.getElementById(`edit-input-${ne(v)}`);f(v,"edit",w?.value??""),a.editingPath=null;return}p&&g(p.dataset.path,{pulse:!0})}function ne(e){return e.replace(/[^a-zA-Z0-9_-]/g,"_")}function re(e){if(e.target.tagName==="INPUT")return;const n=I();if(n.length===0)return;const r=n.findIndex(o=>o.path===a.selectedPath);if(e.key==="ArrowDown"||e.key==="j"){e.preventDefault();const o=n[Math.min(n.length-1,r+1)]??n[0];g(o.path,{pulse:!0})}else if(e.key==="ArrowUp"||e.key==="k"){e.preventDefault();const o=n[Math.max(0,r-1)]??n[0];g(o.path,{pulse:!0})}else e.key==="a"&&a.selectedPath?f(a.selectedPath,"approve"):e.key==="r"&&a.selectedPath&&f(a.selectedPath,"reject")}function g(e,t={}){const n=a.extraction.report.fields.find(o=>o.path===e);a.selectedPath=e,n?.page&&(a.currentPage=n.page),u();const r=document.querySelector(`.highlight-rect[data-path="${x(e)}"]`);r?.scrollIntoView({block:"center",inline:"center",behavior:"smooth"}),t.pulse&&r&&(window.matchMedia("(prefers-reduced-motion: reduce)").matches||(r.classList.add("is-pulsing"),window.setTimeout(()=>r.classList.remove("is-pulsing"),1900))),document.querySelector(`.field-row[data-path="${x(e)}"]`)?.scrollIntoView({block:"nearest"})}function x(e){return e.replace(/"/g,'\\"')}function _(e,t){document.querySelector(`.field-row[data-path="${x(e)}"]`)?.classList.toggle("is-hovered",t)}async function f(e,t,n){if(a.document)try{const r=await d.review(a.document.id,e,t,n);a.extraction.review[e]=r,b()}catch(r){h(r instanceof Error?r.message:"Couldn't update review status")}}function b(){const e=document.getElementById("field-list");e&&(e.innerHTML=N())}m();j();
//# sourceMappingURL=index-_0Mp3IvN.js.map
