#!/usr/bin/env python3
"""league_shell.py — the NCAAF League Hub shell's JS (the NFL / EPL League Hubs' design, ported).

Router: no hash or #NCAAF = the league home; #<TEAM KEY> (OSU, TAM, MOH …) a team page; #C-<CONF> a conference page
(#C-SEC, #C-B1G …); #W<n> a week of the league schedule (#WP = the postseason); #G<ESPN event id> a game page. Every view is a
fragment fetched from the published files (league/NCAAF.json, teams/<KEY>.json, confs/<CONF>.json, weeks/W<n>.json,
games/<bundle>.json) and cached; the theme (team colors) swaps per view. The picker groups the 138 teams by conference.
Delegated listeners (fragments arrive by innerHTML, so their own scripts would not run): segmented tabs, click-to-sort
boards (button.srt, data-v cells, rank cells .rkc renumbered), chart tooltips (data-tip), the back trail (crumbs-v1:
the views this reader opened, League at the root, at most 6, sessionStorage per tab), scroll memory per view, and the
fit-to-width contract for boards (FIT_JS: columns with data-d drop in order while a table is wider than its panel).
Nothing here holds data or authored text.
"""
import sys

sys.dont_write_bytecode = True

TRAIL_HTML = ('  <nav class="lg-tr" id="lg-tr" aria-label="Breadcrumb" hidden><div class="lg-tr-in"><a class="lg-back lg-cr" id="lg-back" '
              'href="#NCAAF"><i aria-hidden="true"></i><span>Back</span></a><ol id="lg-tr-ol"></ol></div></nav>\n')

FIT_JS = r'''<script>
/* boards: fit-to-width (the What-If contract) — columns with data-d drop in ascending order while the table is wider than its
   panel; group headers re-span. Per view only; nothing stored. */
(function(){
  function fit(t){
    var wrap = t.parentNode, max = +t.getAttribute("data-max") || 0, hr = t.tHead.rows[t.tHead.rows.length - 1].cells;
    function apply(l){
      t.querySelectorAll("[data-d]").forEach(function(el){ el.hidden = +el.getAttribute("data-d") <= l; });
      var vis = [], cnt = {}, total = 0;
      for(var i = 0; i < hr.length; i++){ if(!hr[i].hidden){ vis.push(i); var g = hr[i].getAttribute("data-gi"); cnt[g] = (cnt[g] || 0) + 1; total++; } }
      [].forEach.call(t.tHead.rows[0].cells, function(th){
        var g = th.getAttribute("data-gi"), n = cnt[g] || 0, s = th.getAttribute("data-short");
        th.hidden = !n; th.colSpan = Math.max(1, n);
        th.innerHTML = (n < 3 && s) ? s : th.getAttribute("data-full");
      });
      [].forEach.call(t.rows, function(row){
        if(row.classList.contains("grp")){ row.cells[0].colSpan = total; return; }
        if(row.classList.contains("ghr")) return;
        var prev = null;
        vis.forEach(function(i, k){ var g = hr[i].getAttribute("data-gi"); if(row.cells[i]) row.cells[i].classList.toggle("gx", k > 0 && g !== prev); prev = g; });
      });
    }
    var l = 0; apply(0);
    while(t.scrollWidth > wrap.clientWidth + 1 && l < max){ l++; apply(l); }
  }
  function fitAll(root){ (root || document).querySelectorAll("table.rb.lg").forEach(function(t){ if(t.offsetParent !== null) fit(t); }); }
  window.ncaafFit = fitAll;
  var tm = null; window.addEventListener("resize", function(){ clearTimeout(tm); tm = setTimeout(function(){ fitAll(); }, 80); });
  if(document.fonts && document.fonts.ready) document.fonts.ready.then(function(){ fitAll(); });
})();
</script>
'''

LEAGUE_JS = r'''<script>
(function(){
  var D = JSON.parse(document.getElementById("lg-data").textContent);
  var cache = {}, pending = {}, HOME = D.landing;
  if(D.frags){ Object.keys(D.frags).forEach(function(k){ cache[k] = D.frags[k]; }); }
  var box = document.getElementById("club"), nav = document.getElementById("lg-nav"), themeEl = document.getElementById("lg-theme");
  var pick = document.getElementById("lg-pick"), sheet = document.getElementById("lg-sheet"), st = document.getElementById("lg-st");
  var cur = null, pos = {}, fresh = false;
  function esc(s){ return String(s == null ? "" : s).replace(/[&<>"']/g, function(c){ return {"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]; }); }
  function isG(h){ return /^G[0-9]{6,12}$/.test(h || ""); }
  function known(h){ return !!(D.meta[h] || (isG(h) && D.games && D.games[h.slice(1)])); }
  function path(k){
    if(isG(k)){ var g = D.games[k.slice(1)]; return "games/" + g[2] + ".json"; }
    var m = D.meta[k]; return m.file;
  }
  try{ if("scrollRestoration" in history) history.scrollRestoration = "manual"; }catch(e){}
  function savePos(){ if(cur) pos[cur] = window.scrollY; }
  function jump(y){ try{ window.scrollTo({top: y, left: 0, behavior: "instant"}); }catch(e){ window.scrollTo(0, y); } }
  /* ---------- crumbs-v1: the back trail ---------- */
  var TRMAX = 6, tr = [], trFirst = null, trRest = false, trEl = document.getElementById("lg-tr"),
      trOl = document.getElementById("lg-tr-ol"), trBack = document.getElementById("lg-back");
  function trLabel(k){
    if(isG(k)){ var g = D.games[k.slice(1)]; return g ? g[0] : "Game"; }
    return k === HOME ? "League" : ((D.meta[k] || {}).crumb || (D.meta[k] || {}).nick || k);
  }
  function trSave(){ try{ sessionStorage.setItem("ncaaf_trail", JSON.stringify(tr)); }catch(e){} }
  function trLoad(start){
    try{
      var s = JSON.parse(sessionStorage.getItem("ncaaf_trail") || "null");
      if(s && s.length && s.length <= TRMAX && s[0].k === HOME && s[s.length - 1].k === start
         && s.every(function(c){ return c && known(c.k) && typeof c.t === "string"; })){ tr = s; trRest = true; }
    }catch(e){}
  }
  function trDraw(){
    if(!trEl) return;
    var n = tr.length, on = n > 1;
    trEl.hidden = !on; document.documentElement.classList.toggle("lg-has-tr", on);
    if(!on){ trOl.innerHTML = ""; return; }
    var pv = tr[n - 2];
    trBack.setAttribute("href", "#" + pv.k); trBack.setAttribute("aria-label", "Back to " + pv.t); trBack.title = "Back to " + pv.t;
    trOl.innerHTML = tr.map(function(c, i){
      return i === n - 1 ? '<li aria-current="page"><span>' + esc(c.t) + "</span></li>"
        : '<li><a class="lg-cr" href="#' + c.k + '">' + esc(c.t) + "</a></li>";
    }).join("");
    trOl.scrollLeft = trOl.scrollWidth;
  }
  function trPush(k){
    if(trFirst === null) trFirst = k;
    var i = -1; for(var j = 0; j < tr.length; j++){ if(tr[j].k === k){ i = j; break; } }
    if(i >= 0) tr = tr.slice(0, i + 1);
    else {
      if(!tr.length || tr[0].k !== HOME) tr.unshift({k: HOME, t: trLabel(HOME)});
      if(k !== HOME) tr.push({k: k, t: trLabel(k)});
      if(tr.length > TRMAX) tr = [tr[0]].concat(tr.slice(tr.length - TRMAX + 1));
    }
    trDraw(); trSave();
  }
  function setTheme(css){ if(themeEl.textContent !== css) themeEl.textContent = css; }
  function openSheet(open){
    sheet.hidden = !open; pick.setAttribute("aria-expanded", open ? "true" : "false");
    if(open){ var c = sheet.querySelector('[aria-current="true"]') || sheet.querySelector("button"); if(c) c.focus(); }
  }
  function load(k){
    if(cache[k]) return Promise.resolve(cache[k]);
    if(isG(k)){
      var b = D.games[k.slice(1)][2];
      if(!pending["gb:" + b]) pending["gb:" + b] = fetch("games/" + b + ".json").then(function(r){ if(!r.ok) throw new Error("HTTP " + r.status); return r.json(); })
        .then(function(bun){ Object.keys(bun).forEach(function(eid){ cache["G" + eid] = bun[eid]; }); delete pending["gb:" + b]; return bun; },
              function(err){ delete pending["gb:" + b]; throw err; });
      return pending["gb:" + b].then(function(){ if(!cache[k]) throw new Error("game not in bundle"); return cache[k]; });
    }
    if(!pending[k]) pending[k] = fetch(path(k)).then(function(r){
      if(!r.ok) throw new Error("HTTP " + r.status); return r.json();
    }).then(function(f){ cache[k] = f; delete pending[k]; return f; }, function(err){ delete pending[k]; throw err; });
    return pending[k];
  }
  function render(key, f, how){
    box.innerHTML = f.html; box.setAttribute("data-ab", key);
    nav.innerHTML = (f.nav || []).map(function(n){ return '<a href="#' + n[0] + '" data-sec="' + n[0] + '">' + n[1] + "</a>"; }).join("");
    if(window.ncaafFit) window.ncaafFit(box);
    if(how === "nav" || how === "hash"){ var y = (!fresh && pos[key] != null) ? pos[key] : 0; fresh = false; jump(y); }
    else if(how === "pick") jump(0);
  }
  function show(k, how){
    var m;
    if(isG(k)){
      var g = D.games && D.games[k.slice(1)]; if(!g) return false;
      m = D.meta[g[1]] || D.meta[HOME];
      m = {theme: m.theme, nick: g[0], chip: m.chip, status: g[3] || ""};
    } else {
      m = D.meta[k]; if(!m) return false;
    }
    savePos(); cur = k; trPush(k);
    setTheme(m.theme);
    pick.querySelector(".bug-name").textContent = m.nick;
    var oc = pick.querySelector(".chip"); if(oc) oc.outerHTML = m.chip;
    st.textContent = m.status || "";
    sheet.querySelectorAll("[data-ab]").forEach(function(b){ b.setAttribute("aria-current", b.getAttribute("data-ab") === k ? "true" : "false"); });
    document.title = k === HOME ? "NCAAF League Hub" : m.nick + " · NCAAF League Hub";
    if(how !== "hash" && how !== "nav"){ try{ history.replaceState(null, "", "#" + k); }catch(e){} }
    if(cache[k]){ render(k, cache[k], how); return true; }
    box.innerHTML = ""; box.removeAttribute("data-ab"); nav.innerHTML = "";
    if(how === "pick" || how === "nav") jump(0);
    load(k).then(function(f){ if(cur === k) render(k, f, how); }, function(){
      if(cur !== k) return;
      box.innerHTML = '<div class="paper lg-err"><p>This page did not load.<button type="button" class="lg-retry" data-ab="' + esc(k) + '">Try again</button></p></div>';
      box.setAttribute("data-ab", "error");
    });
    return true;
  }
  /* ---------- delegated listeners ---------- */
  pick.addEventListener("click", function(){ openSheet(sheet.hidden); });
  sheet.addEventListener("click", function(ev){
    var b = ev.target.closest("[data-ab]"); if(!b) return;
    openSheet(false); fresh = true; show(b.getAttribute("data-ab"), "pick");
  });
  document.addEventListener("keydown", function(ev){ if(ev.key === "Escape" && !sheet.hidden){ openSheet(false); pick.focus(); } });
  document.addEventListener("click", function(ev){
    if(!sheet.hidden && !ev.target.closest("#lg-sheet") && !ev.target.closest("#lg-pick")) openSheet(false);
    var a = ev.target.closest('a[href^="#"]');
    if(a){
      var h = a.getAttribute("href").slice(1);
      if(known(h) || h.toUpperCase() === HOME){
        ev.preventDefault();
        if(h === cur){ jump(0); return; }
        if(!a.classList.contains("lg-cr")) fresh = true;
        try{ history.pushState(null, "", "#" + h); }catch(e){ location.hash = h; }
        show(h, "nav");
        return;
      }
    }
    var r = ev.target.closest(".lg-retry"); if(r){ show(r.getAttribute("data-ab"), "pick"); return; }
    var tab = ev.target.closest('.lp-tabs [role="tab"]');
    if(tab){
      var grp = tab.getAttribute("data-grp"), id = tab.getAttribute("data-tab");
      tab.parentNode.querySelectorAll('[role="tab"]').forEach(function(t){ var on = t === tab; t.classList.toggle("on", on); t.setAttribute("aria-selected", on ? "true" : "false"); t.tabIndex = on ? 0 : -1; });
      box.querySelectorAll('[data-pane-grp="' + grp + '"]').forEach(function(p){ p.hidden = p.id !== id; });
      if(window.ncaafFit) window.ncaafFit(box);
      return;
    }
    var sb = ev.target.closest("button.srt");
    if(sb){ sortBy(sb); return; }
  });
  function sortBy(btn){
    var th = btn.closest("th"), table = btn.closest("table"), tb = table.tBodies[0];
    var idx = [].indexOf.call(th.parentNode.cells, th);
    var dir = th.getAttribute("aria-sort") === "descending" ? "asc" : (th.getAttribute("aria-sort") === "ascending" ? "desc" : btn.getAttribute("data-dir"));
    th.parentNode.querySelectorAll("th").forEach(function(x){ x.removeAttribute("aria-sort"); });
    th.setAttribute("aria-sort", dir === "asc" ? "ascending" : "descending");
    var rows = [].slice.call(tb.rows).filter(function(r){ return !r.classList.contains("grp"); });
    tb.querySelectorAll("tr.grp").forEach(function(g){ g.remove(); });
    rows.sort(function(a, b){
      var va = a.cells[idx] ? a.cells[idx].getAttribute("data-v") : "", vb = b.cells[idx] ? b.cells[idx].getAttribute("data-v") : "";
      var na = va === "" || va == null, nb = vb === "" || vb == null;
      if(na && nb) return 0; if(na) return 1; if(nb) return -1;
      return dir === "asc" ? (+va - +vb) : (+vb - +va);
    });
    rows.forEach(function(r, i){ tb.appendChild(r); var rk = r.querySelector(".rkc"); if(rk) rk.textContent = i + 1; });
  }
  /* chart tooltips */
  var tip = document.createElement("div"); tip.className = "sc-tip"; tip.hidden = true; document.body.appendChild(tip);
  function tipShow(el, x, y){ tip.innerHTML = el.getAttribute("data-tip"); tip.hidden = false;
    var w = tip.offsetWidth, h = tip.offsetHeight; tip.style.left = Math.max(6, Math.min(window.innerWidth - w - 6, x - w / 2)) + "px";
    tip.style.top = Math.max(6, y - h - 12) + window.scrollY + "px"; }
  document.addEventListener("mouseover", function(ev){ var p = ev.target.closest("[data-tip]"); if(p) tipShow(p, ev.clientX, ev.clientY); });
  document.addEventListener("mouseout", function(ev){ if(ev.target.closest("[data-tip]")) tip.hidden = true; });
  document.addEventListener("focusin", function(ev){ var p = ev.target.closest("[data-tip]"); if(p){ var r = p.getBoundingClientRect(); tipShow(p, r.left + r.width / 2, r.top); } });
  document.addEventListener("focusout", function(ev){ if(ev.target.closest("[data-tip]")) tip.hidden = true; });
  window.addEventListener("hashchange", function(){
    var h = (location.hash || "").slice(1); if(!h) h = HOME;
    if(known(h) && h !== cur){ openSheet(false); show(h, "nav"); }
  });
  window.addEventListener("popstate", function(){
    var h = (location.hash || "").slice(1) || HOME;
    if(known(h) && h !== cur){ show(h, "nav"); }
  });
  var start = (location.hash || "").slice(1);
  if(!known(start)) start = HOME;
  trLoad(start);
  window.ncaafHub = {show: show, cache: cache, D: D, trail: function(){ return tr.map(function(c){ return c.t; }); }};
  show(start, "hash");
})();
</script>
'''
