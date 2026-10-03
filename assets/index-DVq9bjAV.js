(function(){const t=document.createElement("link").relList;if(t&&t.supports&&t.supports("modulepreload"))return;for(const o of document.querySelectorAll('link[rel="modulepreload"]'))r(o);new MutationObserver(o=>{for(const i of o)if(i.type==="childList")for(const s of i.addedNodes)s.tagName==="LINK"&&s.rel==="modulepreload"&&r(s)}).observe(document,{childList:!0,subtree:!0});function n(o){const i={};return o.integrity&&(i.integrity=o.integrity),o.referrerPolicy&&(i.referrerPolicy=o.referrerPolicy),o.crossOrigin==="use-credentials"?i.credentials="include":o.crossOrigin==="anonymous"?i.credentials="omit":i.credentials="same-origin",i}function r(o){if(o.ep)return;o.ep=!0;const i=n(o);fetch(o.href,i)}})();async function L(e){if(!e.ok){const t=await e.json().catch(()=>({detail:e.statusText}));throw new Error(typeof t.detail=="string"?t.detail:e.statusText)}return await e.json()}class D{kind="demo";cache=new Map;storageKey(t){return`fieldproof-demo-review:${t}`}loadReviewOverlay(t){try{const n=localStorage.getItem(this.storageKey(t));return n?JSON.parse(n):{}}catch{return{}}}saveReviewOverlay(t,n){try{localStorage.setItem(this.storageKey(t),JSON.stringify(n))}catch{}}async listSamples(){const t=await fetch("/fieldproof/demo-data/index.json");return L(t)}async fetchSample(t){const n=this.cache.get(t);if(n)return n;const r=await fetch(`/fieldproof/demo-data/${t}/data.json`),o=await L(r);return this.cache.set(t,o),o}async loadSample(t){const n=await this.fetchSample(t),r=this.loadReviewOverlay(t);return{document:n.document,extraction:{...n.extraction,review:{...n.extraction.review,...r}}}}async listSchemas(){return["invoice","receipt","contract"]}async uploadDocument(){throw new Error("Uploading isn't available in the static demo - see the README to run fieldproof locally.")}pageImageUrl(t,n){return`/fieldproof/demo-data/${t}/page-${n}.png`}async extract(){throw new Error("Re-extracting isn't available in the static demo.")}async review(t,n,r,o){const i=this.loadReviewOverlay(t),s={status:r==="approve"?"approved":r==="edit"?"edited":r==="reject"?"rejected":"pending",edited_value:r==="edit"?o??null:null};return i[n]=s,this.saveReviewOverlay(t,i),s}exportUrl(){return""}}function H(){return new D}function U(e){const t=[];for(const n of e.report.fields){const r=e.review[n.path]??{status:"pending",edited_value:null};r.status!=="rejected"&&t.push({field:n.path,value:r.status==="edited"?r.edited_value:n.value,verification_status:n.status,review_status:r.status,page:n.page})}return t}function B(e){const t="field,value,verification_status,review_status,page",n=o=>{const i=o==null?"":String(o);return/[",\n]/.test(i)?`"${i.replace(/"/g,'""')}"`:i},r=e.map(o=>[o.field,o.value,o.verification_status,o.review_status,o.page].map(n).join(","));return[t,...r].join(`\r
`)+`\r
`}function k(e,t,n){const r=new Blob([t],{type:n}),o=URL.createObjectURL(r),i=document.createElement("a");i.href=o,i.download=e,document.body.appendChild(i),i.click(),i.remove(),setTimeout(()=>URL.revokeObjectURL(o),1e3)}const J=["invoice","receipt","contract"],j=2,l=H(),a={document:null,extraction:null,currentPage:1,zoom:1,zoomIsAuto:!0,selectedPath:null,statusFilter:"all",searchQuery:"",editingPath:null,schemaName:"invoice",provider:"fixture",fixtureFile:null,busy:!1,samples:[]},I=document.getElementById("app");function c(e){return String(e).replace(/&/g,"&amp;").replace(/</g,"&lt;").replace(/>/g,"&gt;").replace(/"/g,"&quot;")}function V(e){return e==="needs_review"?"needs review":e}const K=new Set(["amount","subtotal","tax","total","unit_price","total_contract_value"]);function Q(e){const t=e.split(".").pop()??"";return K.has(t.replace(/\[\d+\]$/,""))}function W(e,t){if(Q(e)){const n=typeof t=="number"?t:Number(t);if(Number.isFinite(n))return n.toLocaleString("en-US",{minimumFractionDigits:2,maximumFractionDigits:2})}return String(t)}let P;function f(e){let t=document.getElementById("toast");t||(t=document.createElement("div"),t.id="toast",t.className="toast",t.setAttribute("role","status"),t.setAttribute("aria-live","polite"),document.body.appendChild(t)),t.textContent=e,t.classList.add("is-visible"),window.clearTimeout(P),P=window.setTimeout(()=>t?.classList.remove("is-visible"),2600)}function z(){const e=document.documentElement.getAttribute("data-theme");return e==="light"||e==="dark"?e:window.matchMedia("(prefers-color-scheme: dark)").matches?"dark":"light"}function Z(){const e=z()==="dark"?"light":"dark";document.documentElement.setAttribute("data-theme",e);try{localStorage.setItem("fieldproof-theme",e)}catch{}h()}function h(){let e=document.querySelector(".topbar");e||(e=document.createElement("header"),e.className="topbar",I.prepend(e));const t=a.extraction?.report.counts,n=t?`<span class="brand-tag" aria-hidden="true">${t.verified}&nbsp;verified&ensp;${t.needs_review}&nbsp;review&ensp;${t.unsupported}&nbsp;unsupported</span>`:`<span class="brand-tag">${l.kind==="demo"?"static demo - fixture data":"grounded document review"}</span>`;e.innerHTML=`
    <div class="brand">
      <h1 class="brand-mark">fieldproof</h1>
      ${n}
    </div>
    ${Y()}
    <div class="topbar-controls">
      ${l.kind==="live"&&a.document?'<button class="btn" id="new-document" type="button">New document</button>':""}
      ${a.extraction?X():""}
      <button class="btn" id="theme-toggle" type="button" aria-label="Toggle dark mode">
        ${z()==="dark"?"☀️ Light":"☽ Dark"}
      </button>
    </div>
  `,e.querySelector("#theme-toggle")?.addEventListener("click",Z),e.querySelector("#export-json")?.addEventListener("click",()=>_("json")),e.querySelector("#export-csv")?.addEventListener("click",()=>_("csv")),e.querySelector("#new-document")?.addEventListener("click",G),e.querySelectorAll("[data-switch-sample]").forEach(r=>{r.addEventListener("click",()=>{window.location.hash=r.dataset.switchSample})})}function Y(){if(l.kind!=="demo"||a.samples.length===0)return"";const e=a.document?.id;return`
    <nav class="sample-switch" aria-label="Sample documents">
      ${a.samples.map(t=>`<button class="sample-switch-btn ${t.id===e?"is-active":""}" type="button" data-switch-sample="${c(t.id)}" ${t.id===e?'aria-current="page"':""}>${c(t.label)}</button>`).join("")}
    </nav>
  `}function G(){a.document=null,a.extraction=null,a.selectedPath=null,a.fixtureFile=null,h(),u()}function X(){return`
    <button class="btn" id="export-json" type="button">Export JSON</button>
    <button class="btn" id="export-csv" type="button">Export CSV</button>
  `}async function _(e){if(!a.document||!a.extraction)return;const t=a.document.filename.replace(/\.pdf$/i,"");if(l.kind==="live"){window.open(l.exportUrl(a.document.id,e),"_blank");return}const n=U(a.extraction);e==="json"?k(`${t}.fieldproof.json`,JSON.stringify(n,null,2),"application/json"):k(`${t}.fieldproof.csv`,B(n),"text/csv"),f(`Exported ${n.length} field${n.length===1?"":"s"}`)}async function $(){const e=y();if(l.kind==="demo"){a.samples.length===0&&(a.samples=await l.listSamples?.()??[]),e.innerHTML=`
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
    `,e.querySelectorAll("[data-sample]").forEach(r=>{r.addEventListener("click",()=>E(r.dataset.sample))});return}e.innerHTML=`
    <div class="start-state">
      <h1>Upload a document</h1>
      <p>PDF with a text layer. Extraction runs against the fixture provider or Claude, then every field is grounded and verified against the page.</p>
      <label class="dropzone" id="dropzone" for="file-input">
        Drop a PDF here, or click to choose one
      </label>
      <input type="file" id="file-input" accept="application/pdf" class="visually-hidden" />
    </div>
  `;const t=e.querySelector("#file-input"),n=e.querySelector("#dropzone");t.addEventListener("change",()=>{t.files?.[0]&&M(t.files[0])}),n.addEventListener("dragover",r=>{r.preventDefault(),n.classList.add("dragover")}),n.addEventListener("dragleave",()=>n.classList.remove("dragover")),n.addEventListener("drop",r=>{r.preventDefault(),n.classList.remove("dragover");const o=r.dataTransfer?.files?.[0];o&&M(o)})}async function E(e){if(!l.loadSample)return;let t;try{t=await l.loadSample(e)}catch(r){f(r instanceof Error?`Could not load ${e}: ${r.message}`:`Could not load ${e}`);return}a.document=t.document,a.extraction=t.extraction,a.currentPage=1,a.zoomIsAuto=!0,a.selectedPath=null,a.statusFilter="all",a.searchQuery="",h();const n=S().find(r=>r.status!=="verified");n?v(n.path,{scroll:!1}):u()}async function ee(){a.samples=await l.listSamples?.().catch(()=>[])??[];const e=decodeURIComponent(window.location.hash.slice(1)),t=a.samples.find(n=>n.id===e)??a.samples[0];if(!t){$();return}await E(t.id)}window.addEventListener("hashchange",()=>{if(l.kind!=="demo")return;const e=decodeURIComponent(window.location.hash.slice(1))||a.samples[0]?.id;e&&a.samples.some(t=>t.id===e)&&e!==a.document?.id&&E(e)});async function M(e){try{a.document=await l.uploadDocument(e),a.extraction=null,a.currentPage=1,a.zoomIsAuto=!0,h(),u()}catch(t){f(t instanceof Error?t.message:"Upload failed")}}function T(){const e=y();e.innerHTML=`
    <div class="start-state">
      <h1>${c(a.document.filename)}</h1>
      <p>${a.document.page_count} page${a.document.page_count===1?"":"s"} loaded. Choose a schema and a provider to extract.</p>
      <div style="display:flex; flex-direction:column; gap:12px; text-align:left; max-width:360px; margin:0 auto;">
        <label>
          Schema
          <select class="select" id="schema-select" style="width:100%">
            ${J.map(i=>`<option value="${i}" ${i===a.schemaName?"selected":""}>${i}</option>`).join("")}
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
  `;const t=e.querySelector("#schema-select"),n=e.querySelector("#provider-select"),r=e.querySelector("#fixture-label"),o=e.querySelector("#fixture-input");t.addEventListener("change",()=>{a.schemaName=t.value}),n.addEventListener("change",()=>{a.provider=n.value,r.hidden=a.provider!=="fixture"}),o.addEventListener("change",()=>{a.fixtureFile=o.files?.[0]??null}),e.querySelector("#run-extract").addEventListener("click",te)}async function te(){if(a.document){if(a.provider==="fixture"&&!a.fixtureFile){f("Choose a fixture JSON file first");return}a.busy=!0,T();try{a.extraction=await l.extract(a.document.id,a.schemaName,a.provider,a.fixtureFile),a.currentPage=1,a.zoomIsAuto=!0,h()}catch(e){f(e instanceof Error?e.message:"Extraction failed")}finally{a.busy=!1,u()}}}function y(){let e=document.querySelector(".workbench");return e||(e=document.createElement("main"),e.className="workbench",I.appendChild(e)),e}const A={unsupported:0,needs_review:1,verified:2};function S(){const e=a.extraction?.report.fields??[],t=a.searchQuery.trim().toLowerCase(),n=e.filter(r=>a.statusFilter!=="all"&&r.status!==a.statusFilter?!1:t?r.path.toLowerCase().includes(t)||String(r.value).toLowerCase().includes(t):!0);return a.statusFilter!=="all"?n:[...n].sort((r,o)=>A[r.status]-A[o.status])}function u(){if(!a.document){$();return}if(!a.extraction){T();return}const e=y();e.innerHTML=`
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
      <div class="viewer-scroll" id="viewer-scroll" tabindex="0" role="group" aria-label="Document page">
        ${N()}
      </div>
    </section>
    <section class="field-pane" aria-label="Extracted fields">
      ${ae()}
      <ul class="field-list" id="field-list" tabindex="0" aria-label="Fields (arrow keys to navigate, a to approve, r to reject)">
        ${R()}
      </ul>
    </section>
  `,re(),a.zoomIsAuto&&q()}function q(){const e=document.getElementById("viewer-scroll"),t=a.document?.pages.find(d=>d.number===a.currentPage);if(!e||!t)return;const n=t.width*j,r=e.clientWidth-48,o=Math.min(1,Math.max(.35,r/n)),i=Math.round(o*100)/100;if(i===a.zoom)return;a.zoom=i,e.innerHTML=N(),e.scrollLeft=0,e.scrollTop=0,O();const s=document.getElementById("zoom-label");s&&(s.textContent=`${Math.round(a.zoom*100)}%`)}window.addEventListener("resize",()=>{a.zoomIsAuto&&q()});function N(){const e=a.document.pages.find(s=>s.number===a.currentPage),t=j*a.zoom,n=Math.round(e.width*t),r=Math.round(e.height*t),i=(a.extraction?.report.fields??[]).filter(s=>s.page===a.currentPage).flatMap(s=>s.rects.map(d=>({rect:d,field:s}))).map(({rect:s,field:d})=>{const p=s.x0*t,g=s.top*t,w=(s.x1-s.x0)*t,C=(s.bottom-s.top)*t;return`<div class="highlight-rect ${d.path===a.selectedPath?"is-active":""}" data-status="${d.status}" data-path="${c(d.path)}"
        style="left:${p}px; top:${g}px; width:${w}px; height:${C}px"
        title="${c(d.path)}"></div>`}).join("");return`
    <div class="page-frame" id="page-frame" style="width:${n}px; height:${r}px;">
      <img src="${l.pageImageUrl(a.document.id,a.currentPage)}" width="${n}" height="${r}" alt="Page ${a.currentPage} of ${c(a.document.filename)}" />
      ${i}
    </div>
  `}function ae(){const e=a.extraction.report.counts,t=(n,r,o)=>`
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
      ${l.kind==="demo"?'<p class="demo-note">Synthetic document. The extraction is a hand-written fixture with planted errors, grounded and verified by the real pipeline. Flagged fields come first; select one to see its evidence on the page.</p>':""}
    </div>
  `}function R(){const e=S();return e.length===0?'<li class="empty-filtered">No fields match this filter.</li>':e.map(t=>ne(t)).join("")}function ne(e){const t=a.extraction.review[e.path]??{status:"pending",edited_value:null},n=e.path===a.selectedPath,r=t.status==="edited"?t.edited_value:e.value,o=a.editingPath===e.path,i=e.reasons.length>0?`<ul class="field-reasons">${e.reasons.map(p=>`<li>${c(p)}</li>`).join("")}</ul>`:"",s=e.matched_text?`<div class="field-evidence">“${c(e.matched_text)}”${e.match_score!==null&&e.match_score<100?` <span style="opacity:.7">(${Math.round(e.match_score)}% match)</span>`:""}</div>`:"",d=o?`<div class="edit-row">
        <input class="text-input" id="edit-input-${c(e.path)}" value="${c(r)}" />
        <button class="btn btn-primary" type="button" data-save="${c(e.path)}">Save</button>
        <button class="btn" type="button" data-cancel-edit>Cancel</button>
      </div>`:"";return`
    <li class="field-row ${n?"is-selected":""}" data-path="${c(e.path)}" aria-current="${n?"true":"false"}">
      <div class="field-row-top">
        <span class="field-path">${c(e.path)}</span>
        <span class="status-chip" data-status="${e.status}">${V(e.status)}</span>
      </div>
      <div class="field-value ${t.status==="edited"?"is-edited":""}">${c(W(e.path,r))}</div>
      ${t.status!=="pending"?`<span class="review-badge">${t.status}</span>`:""}
      ${i}
      ${s}
      ${o?d:`<div class="field-actions">
              <button class="btn" type="button" data-approve="${c(e.path)}">Approve</button>
              <button class="btn" type="button" data-edit="${c(e.path)}">Edit</button>
              <button class="btn" type="button" data-reject="${c(e.path)}">Reject</button>
              ${t.status!=="pending"?`<button class="btn" type="button" data-reset="${c(e.path)}">Reset</button>`:""}
            </div>`}
    </li>
  `}function O(){document.querySelectorAll(".highlight-rect").forEach(e=>{e.addEventListener("click",()=>v(e.dataset.path,{pulse:!0})),e.addEventListener("mouseenter",()=>F(e.dataset.path,!0)),e.addEventListener("mouseleave",()=>F(e.dataset.path,!1))})}function re(){const e=y();e.querySelector("#prev-page")?.addEventListener("click",()=>{a.currentPage=Math.max(1,a.currentPage-1),u()}),e.querySelector("#next-page")?.addEventListener("click",()=>{a.currentPage=Math.min(a.document.page_count,a.currentPage+1),u()}),e.querySelector("#zoom-in")?.addEventListener("click",()=>{a.zoomIsAuto=!1,a.zoom=Math.min(3,Math.round((a.zoom+.25)*100)/100),u()}),e.querySelector("#zoom-out")?.addEventListener("click",()=>{a.zoomIsAuto=!1,a.zoom=Math.max(.35,Math.round((a.zoom-.25)*100)/100),u()}),O(),e.querySelectorAll(".count-chip").forEach(r=>{r.addEventListener("click",()=>{a.statusFilter=r.dataset.statusFilter??"all",u()})});const t=e.querySelector("#search-input");t?.addEventListener("input",()=>{a.searchQuery=t.value,b()});const n=e.querySelector("#field-list");n.addEventListener("click",r=>oe(r)),n.addEventListener("keydown",r=>se(r))}function oe(e){const t=e.target,n=t.closest("[data-approve]"),r=t.closest("[data-edit]"),o=t.closest("[data-reject]"),i=t.closest("[data-reset]"),s=t.closest("[data-save]"),d=t.closest("[data-cancel-edit]"),p=t.closest(".field-row");if(n)return void m(n.dataset.approve,"approve");if(o)return void m(o.dataset.reject,"reject");if(i)return void m(i.dataset.reset,"reset");if(r){a.editingPath=r.dataset.edit,b();return}if(d){a.editingPath=null,b();return}if(s){const g=s.dataset.save,w=document.getElementById(`edit-input-${ie(g)}`);m(g,"edit",w?.value??""),a.editingPath=null;return}p&&v(p.dataset.path,{pulse:!0})}function ie(e){return e.replace(/[^a-zA-Z0-9_-]/g,"_")}function se(e){if(e.target.tagName==="INPUT")return;const n=S();if(n.length===0)return;const r=n.findIndex(o=>o.path===a.selectedPath);if(e.key==="ArrowDown"||e.key==="j"){e.preventDefault();const o=n[Math.min(n.length-1,r+1)]??n[0];v(o.path,{pulse:!0})}else if(e.key==="ArrowUp"||e.key==="k"){e.preventDefault();const o=n[Math.max(0,r-1)]??n[0];v(o.path,{pulse:!0})}else e.key==="a"&&a.selectedPath?m(a.selectedPath,"approve"):e.key==="r"&&a.selectedPath&&m(a.selectedPath,"reject")}function v(e,t={}){const n=a.extraction.report.fields.find(o=>o.path===e);if(a.selectedPath=e,n?.page&&(a.currentPage=n.page),u(),t.scroll===!1)return;const r=document.querySelector(`.highlight-rect[data-path="${x(e)}"]`);r?.scrollIntoView({block:"center",inline:"center",behavior:"smooth"}),t.pulse&&r&&(window.matchMedia("(prefers-reduced-motion: reduce)").matches||(r.classList.add("is-pulsing"),window.setTimeout(()=>r.classList.remove("is-pulsing"),1900))),document.querySelector(`.field-row[data-path="${x(e)}"]`)?.scrollIntoView({block:"nearest"})}function x(e){return e.replace(/"/g,'\\"')}function F(e,t){document.querySelector(`.field-row[data-path="${x(e)}"]`)?.classList.toggle("is-hovered",t)}async function m(e,t,n){if(a.document)try{const r=await l.review(a.document.id,e,t,n);a.extraction.review[e]=r,b()}catch(r){f(r instanceof Error?r.message:"Couldn't update review status")}}function b(){const e=document.getElementById("field-list");e&&(e.innerHTML=R())}h();l.kind==="demo"?ee():$();
//# sourceMappingURL=index-DVq9bjAV.js.map
