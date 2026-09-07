"""Visual system for the full-width, instrument-centered workspace."""
CUSTOM_CSS = """
<style>
:root { --ink:#17212b; --muted:#657381; --line:#e4e9ee; --accent:#2563eb; }
html,body,.stApp { background:#fff; color:var(--ink); }
[data-testid="stHeader"] { display:none; }
[data-testid="stMainBlockContainer"] { max-width:1440px; padding:1.8rem 3rem 1.4rem; }
[data-testid="stMainBlockContainer"] > [data-testid="stVerticalBlock"] { gap:.75rem; }
.appbar { display:flex; align-items:center; justify-content:space-between; gap:24px; margin:0 0 18px; }
.wordmark { display:flex; align-items:center; gap:10px; font-size:21px; font-weight:750; letter-spacing:-.035em; }
.wordmark-icon { width:30px; height:30px; display:grid; place-items:center; background:#17212b; color:white; font-size:18px; border-radius:50%; font-weight:600; }
.wordmark-sub { font-size:12px; font-weight:400; color:var(--muted); margin-left:12px; border-left:1px solid #ccd4de; padding-left:20px; letter-spacing:0; }
.market-label { font-size:11px; color:var(--muted); letter-spacing:.04em; }
.st-key-workspace-toolbar { border-bottom:1px solid var(--line); padding-bottom:13px; margin-bottom:12px; }
.st-key-workspace_nav button { border:0 !important; border-radius:0 !important; background:transparent !important; padding:10px 14px; min-height:41px; color:#697783; box-shadow:none !important; transition:color .18s,background .18s; }
.st-key-workspace_nav button[aria-pressed="true"], .st-key-workspace_nav button[kind="segmented_controlActive"] { color:#17212b; border-bottom:2px solid #17212b !important; font-weight:700; }
.st-key-workspace_nav button:hover { background:#f6f8fa !important; color:#17212b; }
.st-key-workspace-toolbar [data-testid="stPopover"] button, .st-key-workspace_refresh button { font-size:12px; min-height:36px; border:1px solid transparent; background:#f6f8fa; }
.st-key-instrument-switcher { margin:5px 0 4px; }
.st-key-instrument-switcher [role="radiogroup"] { gap:5px; }
.st-key-instrument-switcher [data-baseweb="radio"] { padding:7px 12px; margin:0; border-radius:4px; transition:background .18s; }
.st-key-instrument-switcher [data-baseweb="radio"] > div:first-child { position:absolute; opacity:0; width:1px; }
.st-key-instrument-switcher [data-baseweb="radio"]:has(input:checked) { background:#f0f4f8; font-weight:650; }
.st-key-instrument-switcher [data-baseweb="radio"]:focus-within { outline:2px solid var(--accent); outline-offset:2px; }
.st-key-instrument-switcher p { font-size:12px; }
.instrument-head { display:grid; grid-template-columns:1.35fr 1.25fr 1fr .7fr; align-items:center; gap:28px; padding:17px 0 25px; }
.eyebrow { display:block; font-size:10px; font-weight:500; color:var(--muted); letter-spacing:.07em; margin-bottom:8px; }
.instrument-name h1 { font-size:32px; letter-spacing:-.04em; margin:0; padding:0; line-height:1.25; }
.instrument-name p { font-size:11px; color:var(--muted); margin:8px 0 0; }
.instrument-price { font-size:46px; font-weight:550; letter-spacing:-.05em; font-variant-numeric:tabular-nums; line-height:1.2; }
.instrument-price small { display:block; margin-top:10px; color:var(--muted); font-size:11px; font-weight:400; letter-spacing:0; }
.instrument-state, .instrument-target { border-left:1px solid var(--line); padding-left:24px; }
.instrument-state strong { font-size:18px; font-weight:550; }
.instrument-target strong { font-size:25px; font-weight:550; font-variant-numeric:tabular-nums; }
.st-key-market-canvas { border-top:1px solid var(--line); border-bottom:1px solid var(--line); padding:12px 0 3px; animation:canvas-enter .22s ease-out; }
.analysis-heading { display:flex; align-items:baseline; justify-content:space-between; gap:20px; margin:27px 0 15px; }
.analysis-heading h2 { font-size:19px; font-weight:650; margin:0; padding:0; }
.analysis-heading span { color:var(--muted); font-size:11px; }
.decision-grid { display:grid; grid-template-columns:1fr 1.2fr 1fr; gap:30px; padding-bottom:25px; }
.decision-grid section { border-top:2px solid #233447; padding:17px 0 0; }
.decision-grid h3 { font-size:20px !important; font-weight:550; margin:15px 0 10px; padding:0 !important; }
.decision-grid h3 span { font-size:12px; color:var(--muted); margin-left:10px; }
.decision-grid p, .decision-foot { font-size:12px; color:var(--muted); line-height:1.8; margin:10px 0; }
.decision-foot strong { color:var(--ink); margin-left:8px; }
.band-values { display:flex; justify-content:space-between; gap:18px; margin:15px 0 10px; }
.band-values small { display:block; color:var(--muted); font-size:11px; margin-bottom:7px; }
.band-values strong { font-size:24px; font-weight:500; font-variant-numeric:tabular-nums; }
.workspace-title { display:flex; align-items:baseline; gap:25px; margin:22px 0 25px; }
.workspace-title h1 { font-size:30px; margin:0; padding:0; letter-spacing:-.04em; }
.workspace-title p { color:var(--muted); font-size:13px; margin:0; }
h2,h3,h4 { color:var(--ink); border:0; }
h3 { font-size:18px !important; } h4 { font-size:16px !important; }
[data-testid="stCaptionContainer"], [data-testid="stCaptionContainer"] p { color:var(--muted); font-size:11px; }
[data-testid="stMetric"] { background:transparent; border:0; box-shadow:none; padding:10px 0; }
[data-testid="stMetricValue"] { font-size:29px; font-weight:550; color:var(--ink); font-variant-numeric:tabular-nums; }
[data-testid="stMetricLabel"] { font-size:12px; color:var(--muted); }
button { transition:background .15s ease,border-color .15s ease; }
button:focus-visible,a:focus-visible { outline:2px solid var(--accent) !important; outline-offset:3px; }
[data-testid="stButton"] button,[data-testid="stDownloadButton"] button { border-radius:5px; box-shadow:none; }
[data-testid="stButton"] button[kind="primary"] { background:#17212b; border-color:#17212b; color:#fff; }
[data-testid="stExpander"] details { border-color:var(--line); border-radius:5px; }
[data-testid="stDataFrame"] { border-radius:4px; overflow:hidden; }
[data-testid="stTextInput"] input,[data-testid="stNumberInput"] input { font-variant-numeric:tabular-nums; }
.empty-state { padding:40px 0; border-top:1px solid var(--line); margin:12px 0; }
.empty-state strong { font-size:24px; font-weight:500; display:block; margin-bottom:10px; }
.empty-state p { color:var(--muted); font-size:13px; }
.workspace-footer { display:flex; justify-content:space-between; gap:20px; border-top:1px solid var(--line); margin-top:16px; padding-top:20px; font-size:10px; color:var(--muted); }
@keyframes canvas-enter { from { opacity:.6; transform:translateY(4px); } to { opacity:1; transform:translateY(0); } }
@media(max-width:900px) { [data-testid="stMainBlockContainer"] { padding:1.5rem; } .instrument-head { gap:20px; } .instrument-name h1 { font-size:27px; } .instrument-price { font-size:38px; } }
@media(max-width:640px) {
 [data-testid="stMainBlockContainer"] { padding:1rem; }
 .wordmark-sub,.market-label { display:none; } .appbar { margin-bottom:12px; }
 .st-key-workspace_nav button { padding:10px 12px; }
 .instrument-head { grid-template-columns:1fr 1fr; gap:22px 12px; padding:17px 0 22px; }
 .instrument-price { text-align:right; } .instrument-state,.instrument-target { border-left:0; padding-left:0; border-top:1px solid var(--line); padding-top:14px; }
 .instrument-target { text-align:right; } .instrument-name h1 { font-size:28px; }
 .decision-grid { grid-template-columns:1fr; gap:18px; } .analysis-heading { align-items:flex-start; flex-direction:column; gap:7px; }
 .workspace-title { display:block; } .workspace-title p { margin-top:10px; }
 .workspace-footer { flex-direction:column; gap:5px; }
}
@media(prefers-reduced-motion:reduce) { *,*::before,*::after { animation:none !important; transition:none !important; scroll-behavior:auto !important; } }
#MainMenu { visibility:hidden; }
</style>
"""
