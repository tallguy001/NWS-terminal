#!/usr/bin/env python3
"""ncaaf_css — the NCAAF-only rules appended after assets/hub-template.html (which carries the NFL League Hub's stylesheet
verbatim). Selectors here are new; nothing in the template is overridden except where a comment says so."""
import sys

sys.dont_write_bytecode = True

NCAAF_CSS = r'''
  /* ===================== NCAAF additions (ncaaf-hub v1, 2026-10-26) ===================== */
  /* FCS opponents: a neutral chip (no team colors exist for them in the FBS registry) */
  .chip.fcs{--tm-bg:#6b6d72;--tm-fg:#ffffff;--tm-edge:#a9abb0}
  .rkn{display:inline-block;min-width:1.4em;font-family:var(--disp);font-stretch:72%;font-weight:800;font-style:italic;font-size:.82em;
    color:var(--ink3);text-align:right;margin-right:3px}
  .sb-r .rkn,.wm-n .rkn{color:var(--ink3)}
  .hero .rkn,.gb .rkn,.snap .rkn{color:var(--c-ink3)}
  .lg-team .rkn{color:var(--c-ink3);min-width:1.2em}
  td.rkc{font-family:var(--disp);font-stretch:72%;font-weight:800;font-style:italic;color:var(--ink3);text-align:right}
  .tm .nm2{display:flex;flex-direction:column;line-height:1.2}
  .tm .nm2 small{font-size:11px;color:var(--ink3);font-weight:400}
  a.tl2{color:inherit;text-decoration:none}
  a.tl2:hover b,a.tl2:focus-visible b{text-decoration:underline;text-underline-offset:3px}
  .kx{color:var(--ink3);font-size:11.5px}
  .kx b{color:var(--ink2)}
  /* the house team (owner, 2026-10-26: Wisconsin): landing card, highlighted rows, header link, two-number line */
  .hs-card{display:grid;grid-template-columns:minmax(0,1.1fr) minmax(0,1fr) minmax(0,1fr);gap:0;background:var(--sf);border:1px solid var(--ln);
    box-shadow:inset 5px 0 0 var(--tm-bg),var(--shadow)}
  .hs-card>div{padding:14px 16px;min-width:0}
  .hs-card>div+div{border-left:1px solid var(--ln)}
  .hs-id{display:flex;gap:12px;align-items:flex-start}
  .hs-id .chip{font-size:15px;margin-top:4px}
  .hs-nm{display:block;font-family:var(--disp);font-stretch:66%;font-weight:900;font-style:italic;text-transform:uppercase;font-size:30px;
    line-height:.95;color:var(--ink);text-decoration:none}
  .hs-nm span{color:var(--acc)}
  .hs-nm:hover,.hs-nm:focus-visible{text-decoration:underline;text-underline-offset:3px}
  .hs-rec{font-size:13px;color:var(--ink2);margin:6px 0 8px}
  .hs-rec b{color:var(--ink);font-family:var(--disp);font-stretch:72%;font-style:italic;font-size:22px}
  .hs-k{font-size:10.5px;font-weight:800;letter-spacing:.08em;text-transform:uppercase;color:var(--ink3);margin-bottom:5px}
  .hs-g{font-family:var(--disp);font-stretch:72%;font-weight:800;font-style:italic;font-size:19px;color:var(--ink);text-transform:uppercase;line-height:1.15}
  .hs-g .chip{font-size:11px;font-style:normal}
  .hs-s{font-size:12.5px;color:var(--ink2);margin-top:4px;line-height:1.45}
  .hs-s b{color:var(--ink)}
  .hs-o{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:8px 12px}
  .hs-o span{font-size:11.5px;color:var(--ink3);line-height:1.25}
  .hs-o b{display:block;font-family:var(--disp);font-stretch:72%;font-weight:800;font-style:italic;font-size:20px;color:var(--ink)}
  .hs-card>.hs-two{grid-column:1/-1;border-left:0;border-top:1px solid var(--ln);background:var(--sf2);font-size:13px;color:var(--ink2);padding:10px 16px}
  .hs-two b{color:var(--ink)}
  @media (max-width:900px){ .hs-card{grid-template-columns:minmax(0,1fr)} .hs-card>div+div{border-left:0;border-top:1px solid var(--ln)} }
  table.rb tr.hs-row td:first-child{box-shadow:inset 4px 0 0 var(--tm-hs,var(--gold-l)),1px 0 0 var(--ln)}
  .lg-wk.lg-hs{gap:7px}
  .lg-wk.lg-hs .chip{font-size:10px;min-width:2.4em}
  @media (max-width:1100px){ .lg-wk.lg-hs{display:none} }
  .tn-p{margin:12px 0 0;padding:10px 16px}
  .tn-line{margin:0;font-size:13.5px;color:var(--ink2)}
  .tn-line b{color:var(--ink)}
  .tn-sep{color:var(--ink3);margin:0 4px}
  /* conference index in the picker */
  .lg-confs{grid-column:1/-1;display:flex;flex-wrap:wrap;gap:6px 8px;padding:2px 0 8px;border-bottom:1px solid var(--c-ln)}
  .lg-confs button{appearance:none;font:inherit;font-size:12px;font-weight:700;border:1px solid var(--c-ln);background:transparent;color:var(--c-ink);
    padding:4px 10px;cursor:pointer}
  .lg-confs button:hover,.lg-confs button:focus-visible{background:rgba(255,255,255,.08);outline:none}
  .lg-confs button[aria-current="true"]{background:rgba(255,255,255,.14)}
  .lg-sheet-in.ncaaf{grid-template-columns:repeat(4,minmax(0,1fr))}
  .lg-div.big{grid-row:span 2}
  /* conference race cards (league home) */
  .cr-g{display:grid;grid-template-columns:repeat(auto-fill,minmax(min(340px,100%),1fr));gap:14px}
  .cr{background:var(--sf);border:1px solid var(--ln);box-shadow:var(--shadow);min-width:0;overflow-x:auto}
  .cr-h{display:flex;align-items:baseline;justify-content:space-between;gap:10px;padding:9px 12px 7px;background:var(--navy2);color:var(--c-ink)}
  .cr-h a{color:var(--c-ink);text-decoration:none;font-family:var(--disp);font-stretch:72%;font-weight:800;font-style:italic;text-transform:uppercase;font-size:16px}
  .cr-h a:hover,.cr-h a:focus-visible{text-decoration:underline;text-underline-offset:3px}
  .cr-h small{font-size:11px;color:var(--c-ink3)}
  .cr table{width:100%;border-collapse:collapse;font-size:12.5px}
  .cr th{font-size:10.5px;font-weight:600;color:var(--ink3);text-align:right;padding:6px 5px 4px;border-bottom:1px solid var(--ln);white-space:nowrap}
  .cr th:first-child,.cr td:first-child{text-align:left}
  .cr td{padding:6px 5px;border-bottom:1px solid var(--ln);text-align:right;white-space:nowrap;color:var(--ink2)}
  .cr th:first-child,.cr td:first-child{padding-left:10px}
  .cr td:first-child .tm a{display:inline-block;max-width:9.5em;overflow:hidden;text-overflow:ellipsis;vertical-align:bottom}
  .cr tr:last-child td{border-bottom:0}
  .cr td:first-child{color:var(--ink);font-weight:600}
  .cr .tm{display:inline-flex;align-items:center;gap:7px}
  .cr .chip{font-size:10.5px;min-width:2.6em}
  .cr-f{padding:6px 12px 8px;font-size:11.5px;color:var(--ink3);border-top:1px solid var(--ln)}
  /* CFP bracket */
  .bk{display:grid;grid-template-columns:minmax(0,1fr) minmax(0,1fr);gap:14px}
  @media (max-width:900px){ .bk{grid-template-columns:minmax(0,1fr)} }
  .bk-col h5{margin:0 0 6px;font-size:11px;font-weight:700;letter-spacing:.1em;text-transform:uppercase;color:var(--ink3)}
  .bk-m{background:var(--sf);border:1px solid var(--ln);box-shadow:var(--shadow);margin-bottom:10px}
  .bk-t{display:grid;grid-template-columns:2.2em auto minmax(0,1fr) auto;align-items:center;gap:8px;padding:7px 10px;border-bottom:1px solid var(--ln)}
  .bk-t:last-child{border-bottom:0}
  .bk-t .sd{font-family:var(--disp);font-stretch:72%;font-weight:900;font-style:italic;font-size:19px;color:var(--ink3);text-align:right}
  .bk-t .nm{min-width:0}
  .bk-t .nm b{display:block;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
  .bk-t .nm small{display:block;font-size:11px;color:var(--ink3)}
  .bk-t .pr{text-align:right;font-size:12px;color:var(--ink2)}
  .bk-t .pr b{display:block;font-family:var(--disp);font-stretch:74%;font-weight:800;font-style:italic;font-size:16px;color:var(--ink)}
  .bk-t.aq .nm b::after{content:"AQ";font-family:var(--body);font-style:normal;font-size:9.5px;font-weight:800;letter-spacing:.06em;
    margin-left:6px;padding:1px 5px;border:1px solid var(--ln2);color:var(--ink3);vertical-align:2px}
  .bk-host{font-size:11px;color:var(--ink3);padding:5px 10px;background:var(--sf2);border-bottom:1px solid var(--ln)}
  .bk-out{display:flex;flex-wrap:wrap;gap:6px 14px;font-size:12.5px;color:var(--ink2)}
  .bk-out span{display:inline-flex;align-items:center;gap:6px}
  /* week view: days, rank numbers, kalshi */
  .wm-n b .rkn{margin-right:4px}
  .wm-t .chip i{color:var(--tm-fg,#fff);font-size:inherit;text-align:center}   /* the NFL rule .wm-t i greys the chip text too */
  .cr td:first-child .tm a{max-width:8.5em}
  table.wkb td .kxv{display:block;font-size:11.5px;color:var(--ink3)}
  table.rb.wkb td .wm{max-width:360px}
  table.rb.wkb td .wm .l2,table.rb.wkb td.wres .l2,table.rb.sched td .l2{white-space:normal}
  table.rb.wkb td.wres{white-space:normal;min-width:150px;max-width:230px}
  /* team page */
  .tp-conf{font-size:12px;color:var(--ink3)}
  .sch-res{font-weight:800}
  .sch-res.w{color:var(--up)}.sch-res.l{color:var(--down)}
  .rc-g{display:grid;grid-template-columns:repeat(auto-fill,minmax(min(230px,100%),1fr));gap:0;border-top:1px solid var(--ln);border-left:1px solid var(--ln)}
  .rc-g .rt{min-height:100%}
  .idx-g{display:grid;grid-template-columns:repeat(auto-fill,minmax(min(260px,100%),1fr));gap:12px}
  .idx{background:var(--sf);border:1px solid var(--ln);padding:8px 10px 10px}
  .idx h5{margin:0 0 6px;font-size:11px;font-weight:700;letter-spacing:.1em;text-transform:uppercase;color:var(--ink3)}
  .idx h5 a{color:inherit}
  .idx ul{list-style:none;margin:0;padding:0;display:grid;grid-template-columns:1fr 1fr;gap:4px 10px}
  .idx li a{display:inline-flex;align-items:center;gap:6px;text-decoration:none;color:var(--ink);font-size:12.5px;white-space:nowrap}
  .idx li a:hover span,.idx li a:focus-visible span{text-decoration:underline;text-underline-offset:3px}
  .idx .chip{font-size:10px;min-width:2.5em}
  .cal-l{list-style:none;margin:0;padding:0}
  .cal-l li{display:grid;grid-template-columns:7.5em minmax(0,1fr) auto;gap:10px;padding:7px 0;border-bottom:1px solid var(--ln);font-size:13px;color:var(--ink2)}
  .cal-l li:last-child{border-bottom:0}
  .cal-l li b{color:var(--ink)}
  .cal-l li.past{opacity:.6}
  .tag{display:inline-block;font-size:10px;font-weight:800;padding:1px 6px;border-radius:2px;background:var(--flat-bg);color:var(--ink2)}
  .tag.C{background:var(--up-bg);color:var(--up)}.tag.R{background:var(--warn-bg);color:var(--warn)}.tag.U{background:var(--down-bg);color:var(--down)}
  /* game page */
  .gx-hero{background:var(--navy);color:var(--c-ink);box-shadow:var(--shadow);position:relative;overflow:hidden}
  .gx-hero::before{content:"";position:absolute;left:0;top:0;bottom:0;width:6px;background:var(--gold)}
  .gx-k{padding:14px 22px 0 30px;font-size:11px;font-weight:700;letter-spacing:.12em;text-transform:uppercase;color:var(--c-ink3)}
  .gx-rows{padding:6px 22px 10px 30px}
  .gx-row{display:grid;grid-template-columns:auto minmax(0,1fr) auto;align-items:center;gap:14px;padding:9px 0;border-bottom:1px solid var(--c-ln)}
  .gx-row:last-child{border-bottom:0}
  .gx-row .chip{font-size:15px}
  .gx-nm{min-width:0}
  .gx-nm a{color:var(--c-ink);text-decoration:none}
  .gx-nm a:hover,.gx-nm a:focus-visible{text-decoration:underline;text-underline-offset:3px}
  .gx-nm b{display:block;font-family:var(--disp);font-stretch:66%;font-weight:900;font-style:italic;text-transform:uppercase;
    font-size:clamp(24px,4.4vw,42px);line-height:.95;overflow-wrap:anywhere;color:var(--c-ink)}
  .gx-nm b .brew{color:var(--acc-c)}
  .gx-nm small{display:block;font-size:12px;color:var(--c-ink2);margin-top:5px}
  .gx-sc{font-family:var(--disp);font-stretch:66%;font-weight:900;font-style:italic;font-size:clamp(40px,7vw,68px);line-height:.9;color:var(--c-ink)}
  .gx-sc.dim{color:var(--c-ink3)}
  .gx-meta{display:flex;flex-wrap:wrap;gap:4px 18px;padding:9px 22px 12px 30px;border-top:1px solid var(--c-ln);font-size:12.5px;color:var(--c-ink2)}
  .gx-meta b{color:var(--c-ink)}
  .gx-meta .hm{color:var(--acc-c)}
  .sc-pt.sc-dot circle{fill:var(--tm-bg,#888);stroke:var(--tm-edge,transparent);stroke-width:2}
  .tp-track .bub{position:absolute;top:50%;margin:0}
  table.ls{border-collapse:collapse;font-size:13px;min-width:280px}
  table.ls th{font-size:11px;font-weight:600;color:var(--ink3);padding:5px 10px;text-align:center;border-bottom:1px solid var(--ln2)}
  table.ls td{padding:6px 10px;text-align:center;border-bottom:1px solid var(--ln);color:var(--ink2)}
  table.ls td:first-child,table.ls th:first-child{text-align:left}
  table.ls td.t{font-weight:800;color:var(--ink)}
  table.ls tr:last-child td{border-bottom:0}
  .bx{display:grid;grid-template-columns:minmax(0,1fr) 9.5em minmax(0,1fr);gap:4px 12px;align-items:center;font-size:12.5px}
  .bx .k{text-align:center;color:var(--ink3);font-weight:600;font-size:11.5px}
  .bx .v{display:flex;align-items:center;gap:8px}
  .bx .v.l{flex-direction:row-reverse}
  .bx .v b{min-width:4.5em;font-variant-numeric:tabular-nums;color:var(--ink)}
  .bx .v.l b{text-align:right}
  .bx .v i{display:block;height:8px;background:var(--tm-bg,var(--ink3));box-shadow:inset 0 0 0 1px var(--tm-edge,transparent)}
  .bx .v.win b{font-weight:800}
  .bx-h{display:grid;grid-template-columns:minmax(0,1fr) 9.5em minmax(0,1fr);gap:12px;margin-bottom:8px;font-size:12px;font-weight:700;color:var(--ink2)}
  .bx-h span:last-child{text-align:right}
  .bx-h span{display:inline-flex;align-items:center;gap:6px}
  .bx-h span:last-child{justify-content:flex-end}
  @media (max-width:560px){ .bx,.bx-h{grid-template-columns:minmax(0,1fr) 7em minmax(0,1fr)} .bx .v b{min-width:3.4em} }
  .spl{list-style:none;margin:0;padding:0}
  .spl li{display:grid;grid-template-columns:4.6em auto minmax(0,1fr) 4.2em;gap:10px;align-items:start;padding:7px 0;border-bottom:1px solid var(--ln);font-size:12.5px;color:var(--ink2)}
  .spl li:last-child{border-bottom:0}
  .spl li .q{font-weight:700;color:var(--ink3);white-space:nowrap}
  .spl li .s{text-align:right;font-weight:800;color:var(--ink);white-space:nowrap}
  .wp-svg{width:100%;height:auto;display:block}
  .wp-svg .ax{stroke:var(--ln2);stroke-width:1}
  .wp-svg .mid{stroke:var(--ink3);stroke-dasharray:3 4;stroke-width:1}
  .wp-svg .ln{fill:none;stroke:var(--acc);stroke-width:2.2}
  .wp-svg text{fill:var(--ink3);font-size:11px;font-family:var(--body)}
  .fc-g{display:grid;grid-template-columns:repeat(auto-fill,minmax(min(230px,100%),1fr));gap:12px}
  .muted-c{color:var(--ink3)}
  @media (max-width:720px){
    .gx-k,.gx-meta,.gx-rows{padding-left:20px;padding-right:14px}
  }
'''
