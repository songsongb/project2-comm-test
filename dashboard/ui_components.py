from html import escape
import json
import streamlit as st
import streamlit.components.v1 as components
from .presentation import RenderCache

CSS = """<style>
:root{--lg-navy:#102a43;--lg-accent:#236f82;--lg-muted:#52667a}
.block-container{padding-top:1.6rem;padding-bottom:2rem;max-width:1700px}
h1,h2,h3{letter-spacing:-.025em}h1{font-size:2rem!important}
[data-testid="stMetricValue"]{font-size:1.55rem}
.lg-brand{font-size:13px;font-weight:750;letter-spacing:.18em;color:#236f82;margin-bottom:.4rem}
.lg-status{border-left:6px solid var(--state);background:var(--bg);border-radius:12px;padding:22px 26px;margin:12px 0 18px;color:#102a43}
.lg-status strong{font-size:32px;display:block;line-height:1.3}.lg-status p{margin:.4rem 0 0}
.lg-cards{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:14px;margin-bottom:20px}
.lg-card{border:1px solid #d8e2ec;border-radius:12px;padding:18px;background:var(--secondary-background-color,#f5f8fb);min-width:0}
.lg-card h3{font-size:17px!important;margin:0 0 6px}.lg-card .lg-kicker{color:var(--lg-muted);font-size:12px;margin-bottom:10px}
.lg-card p{font-size:14px;margin:7px 0;overflow-wrap:anywhere}.lg-card small{display:block;color:var(--lg-muted);font-size:11px;overflow-wrap:anywhere}
.lg-card .lg-fault{color:#b42318;font-weight:700}.lg-card .lg-ready{color:#16704a;font-weight:700}
.lg-event{border-left:3px solid #c6d5df;padding:10px 14px;margin-bottom:7px;border-radius:0 6px 6px 0;background:var(--secondary-background-color,#f5f8fb);font-size:14px}
.lg-event.alarm{border-color:#d83a3a;background:#fff1f0;color:#7f1d1d}.lg-event small{display:block;font-size:11px;opacity:.75;margin-top:3px}
@media(max-width:1100px){.lg-cards{grid-template-columns:repeat(2,minmax(0,1fr))}}
@media(max-width:850px){.st-key-lab-grid [data-testid="stHorizontalBlock"]{flex-wrap:wrap}.st-key-lab-grid [data-testid="stColumn"]{min-width:100%!important}}
@media(max-width:600px){.lg-cards{grid-template-columns:1fr}.block-container{padding-left:1rem;padding-right:1rem}.lg-status strong{font-size:25px}}
</style>"""


def cache():
    if "render_cache" not in st.session_state:
        st.session_state.render_cache = RenderCache()
    return st.session_state.render_cache


def lazy_panel(label, key):
    return st.expander(label, key=key, on_change="rerun")


def copy_button(value, label):
    encoded = json.dumps(str(value), ensure_ascii=False).replace("<", "\\u003c")
    components.html(f"""<style>button{{background:#eef4f7;border:1px solid #bdccd7;border-radius:7px;padding:9px 14px;cursor:pointer;font-size:14px;color:#143049}}span{{font:12px sans-serif;margin-left:8px}}</style>
<button id="copy">{escape(label)}</button><span id="result" role="status"></span>
<script>const value={encoded};document.getElementById('copy').onclick=async()=>{{
try{{await navigator.clipboard.writeText(value);document.getElementById('result').textContent='복사했습니다';}}
catch(e){{let t=document.createElement('textarea');t.value=value;document.body.appendChild(t);t.select();const ok=document.execCommand('copy');t.remove();document.getElementById('result').textContent=ok?'복사했습니다':'아래 내용을 직접 선택해 복사하세요';}}
}};</script>""", height=48)
