import streamlit as st
import streamlit.components.v1 as components
import requests, uuid, datetime, base64, os, tempfile, json, time
from new_dictionary import ISSUE_TEMPLATES

SUPABASE_URL = "https://vzuzeymvyftmfuaxrvtb.supabase.co"
SUPABASE_KEY = "sb_publishable_2y-rvfayu8BYs0oo-UOzGA_EQTBYLxm"
HEADERS = {"apikey": SUPABASE_KEY, "Authorization": f"Bearer {SUPABASE_KEY}", "Content-Type": "application/json", "Prefer": "return=minimal"}
DELETE_PASSWORD = "5963"

if "db_cache" not in st.session_state: st.session_state.db_cache = {}
if "last_cache_clear_date" not in st.session_state: st.session_state.last_cache_clear_date = None
if "pending_records" not in st.session_state: st.session_state.pending_records = []

def check_and_clear_am3_cache():
    now = datetime.datetime.now(); today_str = now.strftime("%Y-%m-%d")
    if now.hour >= 3 and st.session_state.last_cache_clear_date != today_str:
        st.session_state.db_cache = {}; st.session_state.last_cache_clear_date = today_str

def get_cached_data(cache_key, fetch_func, *args, **kwargs):
    check_and_clear_am3_cache()
    if cache_key in st.session_state.db_cache: return st.session_state.db_cache[cache_key]
    data = fetch_func(*args, **kwargs); st.session_state.db_cache[cache_key] = data; return data

def clear_specific_cache(target_prefix):
    keys_to_del = [k for k in st.session_state.db_cache.keys() if k.startswith(target_prefix)]
    for k in keys_to_del: del st.session_state.db_cache[k]

def _raw_db_get(table, params):
    try:
        res = requests.get(f"{SUPABASE_URL}/rest/v1/{table}?{params}", headers=HEADERS)
        if res.status_code == 200:
            d = res.json()
            if isinstance(d, list): return [x for x in d if isinstance(x, dict)]
            elif isinstance(d, dict): return [d]
        return []
    except: return []

def db_get(table, params=""): return get_cached_data(f"{table}_{params}", _raw_db_get, table, params)

def db_post(table, data): 
    try:
        res = requests.post(f"{SUPABASE_URL}/rest/v1/{table}", headers=HEADERS, json=data)
        clear_specific_cache(table); return res.status_code in [200, 201, 204]
    except: return False

def db_patch(table, record_id, data): 
    try:
        res = requests.patch(f"{SUPABASE_URL}/rest/v1/{table}?record_id=eq.{record_id}", headers=HEADERS, json=data)
        clear_specific_cache(table); return res.status_code in [200, 204]
    except: return False

def db_patch_property(prop_id, data): 
    requests.patch(f"{SUPABASE_URL}/rest/v1/properties?property_id=eq.{prop_id}", headers=HEADERS, json=data); clear_specific_cache("properties")

def db_patch_inspections_by_prop(prop_id, new_name):
    requests.patch(f"{SUPABASE_URL}/rest/v1/inspections?property_id=eq.{prop_id}", headers=HEADERS, json={"property_name": new_name})
    clear_specific_cache("inspections")

def db_patch_inspection(ins_id, data):
    try:
        res = requests.patch(f"{SUPABASE_URL}/rest/v1/inspections?inspection_id=eq.{ins_id}", headers=HEADERS, json=data)
        clear_specific_cache("inspections"); return res.status_code in [200, 204]
    except: return False

def db_delete_record(record_id): 
    requests.delete(f"{SUPABASE_URL}/rest/v1/inspection_records?record_id=eq.{record_id}", headers=HEADERS); clear_specific_cache("inspection_records")

def db_delete_property(prop_id):
    requests.delete(f"{SUPABASE_URL}/rest/v1/inspection_records?property_id=eq.{prop_id}", headers=HEADERS)
    requests.delete(f"{SUPABASE_URL}/rest/v1/inspections?property_id=eq.{prop_id}", headers=HEADERS)
    requests.delete(f"{SUPABASE_URL}/rest/v1/properties?property_id=eq.{prop_id}", headers=HEADERS)
    clear_specific_cache("inspection_records"); clear_specific_cache("inspections"); clear_specific_cache("properties")

def upload_to_storage(base64_str):
    if not base64_str or not isinstance(base64_str, str): return None
    if base64_str.startswith("http"): return base64_str
    try:
        encoded = base64_str.split(",", 1)[1] if "," in base64_str else base64_str
        file_data = base64.b64decode(encoded); filename = f"{uuid.uuid4()}.jpg"
        res = requests.post(f"{SUPABASE_URL}/storage/v1/object/photos/{filename}", headers={"apikey": SUPABASE_KEY, "Authorization": f"Bearer {SUPABASE_KEY}", "Content-Type": "image/jpeg"}, data=file_data)
        if res.status_code not in [200, 201]: return base64_str
        return f"{SUPABASE_URL}/storage/v1/object/public/photos/{filename}"
    except: return base64_str

AREA_ORDER = ["玄関", "トイレ", "キッチン", "バルコニー", "LDK", "洋室", "洗面室", "UB", "廊下・階段・ENT", "外部", "フリー項目"]
WORK_ORDER = ["A.リペア", "B.清掃", "C.クロス", "D.造作", "E.水道", "F.電気", "G.キッチン", "H.サッシ", "I.外壁", "J.外構", "K.コーキング", "L.ガス", "板金", "Z.その他"]
def sort_records(records):
    return sorted(records, key=lambda r: (AREA_ORDER.index(r.get('area', '')) if r.get('area', '') in AREA_ORDER else 999, WORK_ORDER.index(r.get('work_type', '')) if r.get('work_type', '') in WORK_ORDER else 999))
def sort_properties_by_handover(props_list):
    return sorted(props_list or [], key=lambda p: (0, p.get('handover_date')) if p.get('handover_date') and p.get('handover_date').strip() else (1, "9999-12-31"))

SMART_CAMERA_HTML = """<!DOCTYPE html><html lang="ja"><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no"><style>body { margin: 0; padding: 5px; font-family: sans-serif; display: flex; flex-direction: column; align-items: center; background-color: transparent;} .btn-group { display: flex; gap: 10px; width: 100%; max-width: 400px; } .upload-btn { flex: 1; padding: 15px 5px; color: white; border-radius: 8px; font-size: 14px; font-weight: bold; text-align: center; cursor: pointer; box-sizing: border-box; box-shadow: 0 4px 6px rgba(0,0,0,0.1); display: flex; justify-content: center; align-items: center;} input[type="file"] { display: none; }</style></head><body><div class="btn-group"><label class="upload-btn" id="lbl-lib" style="background-color: #27AE60;"><span id="txt-lib">📁 ライブラリ</span><input type="file" accept="image/*" id="file-lib"></label><label class="upload-btn" id="lbl-cam" style="background-color: #2980B9;"><span id="txt-cam">📷 カメラ起動</span><input type="file" accept="image/*" capture="environment" id="file-cam"></label></div><script>const isMobile = /Android|webOS|iPhone|iPad|iPod|BlackBerry|IEMobile|Opera Mini/i.test(navigator.userAgent) || (navigator.platform === 'MacIntel' && navigator.maxTouchPoints > 1); if (!isMobile) { document.getElementById('lbl-cam').style.display = 'none'; } let b = { propName: "", inspType: "", inspDate: "", locationText: "", issueDetail: "", mode: "insp" }; window.addEventListener("message", function(e) { if (e.data.type === "streamlit:render" && e.data.args) { Object.assign(b, e.data.args); }}); function wrapTextAndReturnY(context, text, x, y, maxWidth, lineHeight, maxLines) { if (!text) return y; var words = text.split(''); var line = ''; var lineCount = 0; for(var n = 0; n < words.length; n++) { var testLine = line + words[n]; if (context.measureText(testLine).width > maxWidth && n > 0) { context.fillText(line, x, y); line = words[n]; y += lineHeight; lineCount++; if (lineCount >= maxLines) return y; } else { line = testLine; } } context.fillText(line, x, y); return y + lineHeight; } function sendToStreamlit(val) { window.parent.postMessage({isStreamlitMessage: true, type: "streamlit:setComponentValue", value: val}, "*"); } function handleFile(e) { const file = e.target.files[0]; if (!file) return; document.getElementById('lbl-lib').style.backgroundColor = '#f39c12'; document.getElementById('lbl-cam').style.backgroundColor = '#f39c12'; document.getElementById('txt-lib').innerHTML = '合成中...'; document.getElementById('txt-cam').innerHTML = 'お待ちを'; const reader = new FileReader(); reader.onload = function(event) { const img = new Image(); img.onload = function() { const MAX_SIZE = 800; let w = img.width, h = img.height; if (w > h) { if (w > MAX_SIZE) { h *= MAX_SIZE / w; w = MAX_SIZE; } } else { if (h > MAX_SIZE) { w *= MAX_SIZE / h; h = MAX_SIZE; } } const canvas = document.createElement('canvas'); canvas.width = w; canvas.height = h; const ctx = canvas.getContext('2d'); ctx.drawImage(img, 0, 0, w, h); const bw = w * 0.40, bh = h * 0.32; const sx = w - bw - 10, sy = h - bh - 10; ctx.fillStyle = (b.mode === 'fix') ? "rgba(0, 40, 80, 0.9)" : "rgba(0, 50, 0, 0.85)"; ctx.fillRect(sx, sy, bw, bh); ctx.strokeStyle = "white"; ctx.lineWidth = 2; ctx.strokeRect(sx+5, sy+5, bw-10, bh-10); ctx.fillStyle = "white"; const fs = Math.floor(w * 0.022); ctx.font = fs + "px 'Yu Gothic Medium', 'Hiragino Kaku Gothic ProN', sans-serif"; let ty = sy + fs + 12; const ls = fs * 1.4; const textX = sx + 10; const dw = bw - 20; ty = wrapTextAndReturnY(ctx, b.propName, textX, ty, dw, ls, 2); ty = wrapTextAndReturnY(ctx, b.inspType + "  " + b.inspDate, textX, ty, dw, ls, 2); ty = wrapTextAndReturnY(ctx, b.locationText, textX, ty, dw, ls, 2); ctx.fillStyle = "#ffdddd"; wrapTextAndReturnY(ctx, b.issueDetail, textX, ty, dw, ls, 3); sendToStreamlit(canvas.toDataURL('image/jpeg', 0.6)); document.getElementById('lbl-lib').style.backgroundColor = '#2ecc71'; document.getElementById('lbl-cam').style.backgroundColor = '#2ecc71'; document.getElementById('txt-lib').innerHTML = '✅ 完了'; document.getElementById('txt-cam').innerHTML = '✅ 完了'; }; img.src = event.target.result; }; reader.readAsDataURL(file); } document.getElementById('file-lib').addEventListener('change', handleFile); document.getElementById('file-cam').addEventListener('change', handleFile); window.onload = function() { window.parent.postMessage({isStreamlitMessage: true, type: "streamlit:componentReady", apiVersion: 1}, "*"); window.parent.postMessage({isStreamlitMessage: true, type: "streamlit:setFrameHeight", height: 75}, "*"); };</script></body></html>"""
temp_dir = os.path.join(tempfile.gettempdir(), "felix_comp"); os.makedirs(temp_dir, exist_ok=True)
with open(os.path.join(temp_dir, "index.html"), "w", encoding="utf-8") as f: f.write(SMART_CAMERA_HTML)
_smart_camera = components.declare_component("smart_cam", path=temp_dir)

st.set_page_config(page_title="Felix検査App", layout="wide", initial_sidebar_state="collapsed")
st.markdown("""<style>[data-testid="collapsedControl"], [data-testid="stSidebar"], footer, [data-testid="stStatusWidget"] { display: none !important; } div.stButton > button { border-radius: 6px; height: 50px; font-weight: bold; width: 100%; margin-bottom: 5px; } .record-box { border-bottom: 2px solid #EEEEEE; padding-bottom: 20px; margin-bottom: 20px; } .badge-wrap { display: inline-flex; align-items: center; gap: 8px; font-size: 13px; font-weight: bold; margin-left: 5px; color: #d93025; } div[data-testid="column"] button { height: 35px !important; font-size: 12px !important; font-weight: normal !important; padding: 0 !important; } .floating-back-btn { position: fixed !important; top: 15px !important; left: 15px !important; z-index: 999999 !important; width: auto !important; } .floating-back-btn button { background-color: #34495e !important; color: white !important; border-radius: 30px !important; padding: 5px 20px !important; box-shadow: 0 4px 6px rgba(0,0,0,0.3) !important; border: 2px solid white !important; font-size: 14px !important; font-weight: bold !important; height: auto !important; min-height: 40px !important; } .floating-back-btn button p { color: white !important; margin: 0 !important; } .report-img { width: 100%; max-height: 250px; object-fit: contain; border-radius: 4px; } @media print { .stButton, .stTextInput, .stRadio, .stSelectbox, .stCheckbox, [data-testid="stExpander"], .floating-back-btn, .admin-delete-box, hr { display: none !important; } .main .block-container { padding: 0 !important; margin: 0 !important; max-width: 100% !important; } .report-img { max-height: 400px !important; } .report-item { page-break-inside: avoid !important; break-inside: avoid !important; padding-bottom: 25px !important; } .page-break { page-break-before: always !important; break-before: page !important; height: 0 !important; margin: 0 !important; padding: 0 !important; } }</style>""", unsafe_allow_html=True)

FLOOR_OPTS = ["-- 選択 --", "101","102","103","201","202","203","301","302","303","共用部","外部"]
AREA_OPTS_STANDARD = ["-- 選択 --", "玄関", "廊下・階段・ENT", "LDK", "キッチン", "洋室", "洗面室", "UB", "トイレ", "バルコニー", "外部", "フリー項目"]
AREA_OPTS_SHANAI = ["-- 選択 --", "玄関", "トイレ", "キッチン", "LDK", "バルコニー", "洋室", "洗面室", "UB", "廊下・階段・ENT", "外部", "フリー項目"]
WORK_OPTS_STANDARD = ["-- 選択 --", "基礎工事(鉄筋)", "基礎工事(型枠)", "フレーミング", "FM", "造作", "内装", "電気", "設備", "ガス", "清掃", "サッシ", "外壁", "外構", "コーキング", "リペア", "その他"]
WORK_OPTS_HAIKIN = ["-- 選択 --", "基礎工事(鉄筋)", "水道", "ガス", "その他"]
WORK_OPTS_KUTAI = ["-- 選択 --", "フレーミング", "電気", "水道", "防水", "その他"]
WORK_OPTS_DANNETSU = ["-- 選択 --", "断熱", "造作", "電気", "設備", "その他"]
WORK_OPTS_CHUKAN = ["-- 選択 --", "造作", "電気", "水道", "外壁", "ガス", "足場", "その他"]
WORK_OPTS_SHANAI = ["-- 選択 --", "A.リペア", "B.清掃", "C.クロス", "D.造作", "E.水道", "F.電気", "G.キッチン", "H.サッシ", "I.外壁", "J.外構", "K.コーキング", "L.ガス", "板金", "Z.その他"]
WORK_OPTS_KIKAN = ["基礎工事", "フレーミング", "防水", "造作", "内装", "電気", "設備", "ガス", "サッシ", "外壁", "足場", "外構", "その他"]
INSP_OPTS = ["-- 選択 --", "配筋検査", "躯体検査", "断熱検査", "中間検査", "社内検査(設計)", "社内検査(建設)", "社内検査(マーケ)", "社内検査(不動産)", "【検査機関】配筋検査", "【検査機関】躯体検査", "【検査機関】断熱検査", "【検査機関】中間検査", "【検査機関】完了検査"]
SHANAI_KENSA_TYPES = ["社内検査(設計)", "社内検査(建設)", "社内検査(マーケ)", "社内検査(不動産)"]
INSPECTOR_OPTS = ["工事監理チーム", "建設部", "不動産事業部", "マーケティング部", "検査機関"]

for k in ["role", "active_menu", "pre_selected_prop", "delete_target", "edit_prop_target", "skip_render_ids", "show_bulk_confirm", "edit_saved_records", "cached_records", "cached_target_id", "temp_photo", "prev_floor", "prev_area", "splash_done", "logout_triggered"]:
    if k not in st.session_state: st.session_state[k] = None
if st.session_state.skip_render_ids is None: st.session_state.skip_render_ids = []
if "issue_saved" not in st.session_state: st.session_state.issue_saved = False
if "drill_target" not in st.session_state or not isinstance(st.session_state.drill_target, dict): st.session_state.drill_target = None
if "current_box" not in st.session_state or not isinstance(st.session_state.current_box, dict): st.session_state.current_box = None
if st.session_state.splash_done is None: st.session_state.splash_done = False
if "target_area" not in st.session_state: st.session_state.target_area = None

def jump_to_menu(menu_name, prop_id=None):
    st.session_state.active_menu = menu_name; st.session_state.pre_selected_prop = prop_id
    st.session_state.drill_target = None; st.session_state.current_box = None; st.session_state.delete_target = None; st.session_state.edit_prop_target = None; st.session_state.issue_saved = False; st.session_state.skip_render_ids = []; st.session_state.show_bulk_confirm = False; st.session_state.edit_saved_records = False; st.session_state.cached_records = None; st.session_state.cached_target_id = None; st.session_state.temp_photo = None; st.session_state.prev_floor = None; st.session_state.prev_area = None; st.rerun()

def main():
    components.html("""<script>function floatBackButton() { const doc = window.parent.document; const buttons = Array.from(doc.querySelectorAll('button')); buttons.forEach(b => { if(b.innerText.includes('⬅ 戻る')) { const container = b.closest('div.stButton'); if(container && !container.classList.contains('floating-back-btn')) { container.classList.add('floating-back-btn'); } } }); } floatBackButton(); const observer = new MutationObserver(floatBackButton); observer.observe(window.parent.document.body, {childList: true, subtree: true});</script>""", height=0)

    if st.session_state.logout_triggered:
        components.html("<script>localStorage.removeItem('felix_user_auth');</script>", height=0); time.sleep(0.5); st.session_state.clear(); st.rerun()

    if st.session_state.role is None:
        role_html = """<!DOCTYPE html><html><head><style>body { font-family: sans-serif; padding: 20px; display: flex; flex-direction: column; align-items: center; justify-content: center; height: 100vh; margin: 0; background: #f8f9fa; } .btn { display: block; width: 100%; max-width: 320px; padding: 18px; margin: 12px 0; font-size: 16px; font-weight: bold; color: white; border: none; border-radius: 8px; cursor: pointer; text-align: center; box-shadow: 0 4px 6px rgba(0,0,0,0.1); } .btn-admin { background-color: #2C3E50; } .btn-partner-tokai { background-color: #27AE60; } .btn-partner-kanto { background-color: #2980B9; }</style></head><body><div id="loading"><h3>認証情報を確認中...</h3></div><div id="selector" style="display: none; width: 100%; text-align: center;"><h2>ログインアカウントの選択</h2><p>※一度選択すると次回以降はスキップ</p><button class="btn btn-admin" onclick="setRole('admin', '')">💻 管理者として入室</button><button class="btn btn-partner-tokai" onclick="setRole('partner', '東海エリア')">🛠️ 協力業者 (東海)</button><button class="btn btn-partner-kanto" onclick="setRole('partner', '関東エリア')">🛠️ 協力業者 (関東)</button></div><script>function sendToStreamlit(data) { window.parent.postMessage({isStreamlitMessage: true, type: "streamlit:setComponentValue", value: data}, "*"); } function setRole(role, area) { const data = {role: role, area: area}; localStorage.setItem('felix_user_auth', JSON.stringify(data)); sendToStreamlit(data); } window.onload = function() { window.parent.postMessage({isStreamlitMessage: true, type: "streamlit:componentReady", apiVersion: 1}, "*"); window.parent.postMessage({isStreamlitMessage: true, type: "streamlit:setFrameHeight", height: 500}, "*"); const saved = localStorage.getItem('felix_user_auth'); if (saved) { try { const data = JSON.parse(saved); if (data.role) { sendToStreamlit(data); return; } } catch(e) {} } document.getElementById('loading').style.display = 'none'; document.getElementById('selector').style.display = 'block'; };</script></body></html>"""
        temp_dir_auth = os.path.join(tempfile.gettempdir(), "felix_auth_comp"); os.makedirs(temp_dir_auth, exist_ok=True)
        with open(os.path.join(temp_dir_auth, "index.html"), "w", encoding="utf-8") as f: f.write(role_html)
        auth_res = components.declare_component("auth_menu", path=temp_dir_auth)(key="auth_comp")
        if auth_res: st.session_state.role = auth_res.get("role"); st.session_state.target_area = auth_res.get("area"); st.session_state.active_menu = "ホーム"; st.session_state.splash_done = False; st.rerun()
        st.stop()

    confirm_cnt = len(db_get("inspection_records", "select=record_id&progress_status=eq.確認待ち")) if st.session_state.role == "admin" else 0
    menu_opts = ["ホーム", "物件登録（管理者）", "検査実施（管理者）", "検査内容確認（管理者）", "是正ダッシュボード（管理者用）", "完了分一覧（共通）"] if st.session_state.role == "admin" else ["ホーム", "是正実施（協力業者）", "完了分一覧（共通）"]
    if st.session_state.active_menu not in menu_opts: st.session_state.active_menu = menu_opts[0]
    
    with st.expander(f"メニューを開く (現在のユーザー: {st.session_state.role})", expanded=False):
        selected_menu = st.radio("移動先を選択", menu_opts, index=menu_opts.index(st.session_state.active_menu), format_func=lambda m: f"{m} (未確認{confirm_cnt}件)" if m == "検査内容確認（管理者）" and confirm_cnt > 0 else m, label_visibility="collapsed")
        st.markdown("<br>", unsafe_allow_html=True)
        if st.button("ログアウト / アカウントの切り替え"): st.session_state.logout_triggered = True; st.rerun()
    if selected_menu != st.session_state.active_menu: jump_to_menu(selected_menu, st.session_state.pre_selected_prop)

    # 0. ホーム
    if st.session_state.active_menu == "ホーム":
        if not st.session_state.splash_done:
            st.markdown("""<style>.splash { display: flex; justify-content: center; align-items: center; height: 100vh; font-size: 16px; color: #555; position: fixed; top: 0; left: 0; width: 100vw; background: white; z-index: 999999; letter-spacing: 2px; font-family: sans-serif; }</style><div class="splash">FELIX Inspection System...</div>""", unsafe_allow_html=True); time.sleep(1.5); st.session_state.splash_done = True; st.rerun()
        else:
            role = st.session_state.role; ls_key = "felix_session" if role == "admin" else "felix_partner_session"
            menu_html = f"""<!DOCTYPE html><html><head><style>body {{ margin:0; font-family: sans-serif; display: flex; flex-direction: column; height: 100vh; background: transparent; }} .menu-item {{ font-size: 16px; color: #333; cursor: pointer; margin: 24px 0; text-align: center; }} .menu-item:hover {{ color: #888; }} .container {{ position: absolute; top: 38.2%; left: 50%; transform: translate(-50%, -50%); width: 100%; }}</style></head><body><div class="container"><div class="menu-item" onclick="sendVal('new')">{'新規検査を開始する' if role=='admin' else '新規是正を開始する'}</div><div class="menu-item" id="resume-btn" style="display:none;" onclick="sendVal('resume')"></div></div><script>function sendVal(action) {{ let val = {{ action: action }}; if(action === 'resume') {{ val.data = JSON.parse(localStorage.getItem('{ls_key}')); }} window.parent.postMessage({{isStreamlitMessage: true, type: "streamlit:setComponentValue", value: val}}, "*"); }} const saved = localStorage.getItem('{ls_key}'); if(saved) {{ try {{ const data = JSON.parse(saved); let text = ''; if('{role}' === 'admin' && data.name && data.type) {{ text = '前回の続きから再開する（' + data.name + ' / ' + data.type + '）'; }} else if ('{role}' === 'partner' && data.prop && data.type) {{ text = '前回の続きから再開する（' + data.prop + ' / ' + data.type + '）'; }} if(text) {{ const btn = document.getElementById('resume-btn'); btn.style.display = 'block'; btn.innerText = text; }} }} catch(e) {{}} }} window.onload = function() {{ window.parent.postMessage({{isStreamlitMessage: true, type: "streamlit:componentReady", apiVersion: 1}}, "*"); window.parent.postMessage({{isStreamlitMessage: true, type: "streamlit:setFrameHeight", height: 500}}, "*"); }};</script></body></html>"""
            temp_dir_menu = os.path.join(tempfile.gettempdir(), f"felix_home_{role}"); os.makedirs(temp_dir_menu, exist_ok=True)
            with open(os.path.join(temp_dir_menu, "index.html"), "w", encoding="utf-8") as f: f.write(menu_html)
            res = components.declare_component(f"home_{role}", path=temp_dir_menu)(key=f"hc_{role}")
            if res:
                if res.get('action') == 'new': st.session_state.active_menu = "検査実施（管理者）" if role == "admin" else "是正実施（協力業者）"; st.session_state.current_box = None; st.session_state.drill_target = None; st.rerun()
                elif res.get('action') == 'resume' and res.get('data'):
                    d = res['data']
                    if role == "admin": st.session_state.active_menu = "検査実施（管理者）"; st.session_state.current_box = {"id": d.get('id', str(uuid.uuid4())), "prop_id": d.get('prop_id'), "name": d.get('name'), "type": d.get('type'), "inspector": d.get('inspector')}; st.session_state.prev_floor = d.get('prev_floor'); st.session_state.prev_area = d.get('prev_area')
                    else: st.session_state.active_menu = "是正実施（協力業者）"; st.session_state.drill_target = {"prop": d.get('prop'), "type": d.get('type')}
                    st.rerun()

    # 1. 物件登録（管理者）
    elif st.session_state.active_menu == "物件登録（管理者）":
        st.header("物件登録")
        input_area = st.selectbox("エリア", ["東海エリア", "関東エリア"]); name = st.text_input("新規物件名"); set_h = st.checkbox("引渡し日設定")
        h_date = st.date_input("引渡し日", datetime.date.today()) if set_h else None
        if st.button("登録"):
            if name: db_post("properties", {"property_id": str(uuid.uuid4()), "property_name": name, "area": input_area, "handover_date": str(h_date) if h_date else None}); st.success("登録完了"); st.rerun()
        st.markdown("---")
        st.subheader("物件一覧")
        filter_area = st.radio("絞り込み", ["すべて表示", "東海エリア", "関東エリア"], horizontal=True)
        props = sort_properties_by_handover(db_get("properties", "select=*")); ins_counts = {i.get('property_id'): 0 for i in db_get("inspections", "select=property_id")}
        for i in db_get("inspections", "select=property_id"): ins_counts[i.get('property_id')] = ins_counts.get(i.get('property_id'), 0) + 1
        
        for idx, p in enumerate(props):
            p_id = p.get('property_id')
            if not p_id or (filter_area != "すべて表示" and p.get('area') != filter_area): continue
            p_name = p.get('property_name', '不明'); p_hdate = p.get('handover_date')
            btn_txt = f"[{p.get('area')}] {p_name} (引渡し:{p_hdate or '未設定'}) ({ins_counts.get(p_id, 0)}件) 検査へ"
            c1, c2, c3 = st.columns([6, 2, 2])
            if c1.button(btn_txt, key=f"p_{p_id}"): jump_to_menu("検査実施（管理者）", p_id)
            if c2.button("変更", key=f"e_{p_id}"): st.session_state.edit_prop_target = p_id; st.session_state.delete_target = None; st.rerun()
            if c3.button("削除", key=f"d_{p_id}"): st.session_state.delete_target = p_id; st.session_state.edit_prop_target = None; st.rerun()
            
            if st.session_state.edit_prop_target == p_id:
                st.warning("変更します")
                new_n = st.text_input("物件名", value=p_name, key=f"n_{p_id}")
                init_d = datetime.datetime.strptime(p_hdate, "%Y-%m-%d").date() if p_hdate else datetime.date.today()
                edit_h = st.checkbox("引渡し日設定", value=bool(p_hdate), key=f"cb_{p_id}"); new_h = st.date_input("日付", value=init_d, key=f"h_{p_id}") if edit_h else None
                c_y, c_n = st.columns(2)
                if c_y.button("保存", key=f"s_{p_id}", type="primary"):
                    db_patch_property(p_id, {"property_name": new_n, "handover_date": str(new_h) if new_h else None})
                    if new_n != p_name: db_patch_inspections_by_prop(p_id, new_n)
                    st.session_state.edit_prop_target = None; st.rerun()
                if c_n.button("キャンセル", key=f"c_{p_id}"): st.session_state.edit_prop_target = None; st.rerun()
                
            if st.session_state.delete_target == p_id:
                st.warning("削除しますか？")
                del_pw = st.text_input("パスワード (5963)", type="password", key=f"pw_{p_id}", placeholder="5963")
                c_y, c_n = st.columns(2)
                if c_y.button("Yes (削除)", key=f"sy_{p_id}"):
                    if del_pw == DELETE_PASSWORD: db_delete_property(p_id); st.session_state.delete_target = None; st.rerun()
                    else: st.error("パスワードエラー")
                if c_n.button("キャンセル", key=f"sn_{p_id}"): st.session_state.delete_target = None; st.rerun()

    # 2. 検査実施（管理者）
    elif st.session_state.active_menu == "検査実施（管理者）":
        if not st.session_state.current_box:
            props = sort_properties_by_handover(db_get("properties", "select=*"))
            if not st.session_state.pre_selected_prop and props: st.session_state.pre_selected_prop = props[0].get("property_id")
            area_opts = ["-- 選択 --", "東海エリア", "関東エリア"]; sel_area = st.selectbox("エリア", area_opts)
            sq = st.text_input("検索"); f_props = [p for p in props if p.get('area')==sel_area] if sel_area!="-- 選択 --" else []
            if sq: f_props = [p for p in f_props if sq in p.get('property_name', '')]
            opts = [{"property_id": None, "property_name": "-- 選択 --"}] + f_props
            idx = next((i for i, p in enumerate(opts) if p.get('property_id') == st.session_state.pre_selected_prop), 0)
            target = st.selectbox("物件", opts, index=idx, format_func=lambda x: f"{x.get('property_name')} ({x.get('handover_date') or '未設定'})")
            ins_type = st.selectbox("種類", INSP_OPTS); c1, c2 = st.columns(2); ins_date = c1.date_input("日時", datetime.date.today()); inspector = c2.selectbox("検査員", INSPECTOR_OPTS)
            
            if st.button("スタート"):
                if target.get('property_name') != "-- 選択 --" and ins_type != "-- 選択 --":
                    nid = str(uuid.uuid4())
                    if db_post("inspections", {"inspection_id": nid, "property_id": target.get('property_id'), "property_name": target.get('property_name'), "inspection_type": ins_type, "inspection_date": str(ins_date), "inspector": inspector}):
                        st.session_state.current_box = {"id": nid, "prop_id": target.get('property_id'), "name": target.get('property_name'), "type": ins_type, "inspector": inspector}
                        st.session_state.pre_selected_prop = target.get('property_id'); st.session_state.pending_records = []; st.rerun()
                else: st.error("物件と種類を選択してください")
        else:
            cb = st.session_state.current_box; c_name, c_type, c_id, c_prop_id, c_insp = cb.get('name',''), cb.get('type',''), cb.get('id',''), cb.get('prop_id',''), cb.get('inspector','')
            if st.button("⬅ 戻る"): st.session_state.current_box = None; st.session_state.pending_records = []; st.rerun()
            st.subheader(f"{c_name} / {c_type}"); components.html(f"<script>localStorage.setItem('felix_session', JSON.stringify({json.dumps(cb)}));</script>", height=0)
            
            if st.session_state.get("edit_saved_records"):
                if st.button("⬅ 戻る"): st.session_state.edit_saved_records = False; st.rerun()
                for rec in st.session_state.pending_records:
                    st.markdown(f"**未送信: {rec['floor_level']} {rec['area']} {rec['issue_detail']}**")
                    if st.button("未送信削除", key=f"dp_{rec['temp_id']}"): st.session_state.pending_records = [r for r in st.session_state.pending_records if r['temp_id'] != rec['temp_id']]; st.rerun()
                
                saved_recs = sort_records(db_get("inspection_records", f"inspection_id=eq.{c_id}"))
                edit_w_opts = WORK_OPTS_KIKAN if c_type.startswith("【検査機関】") else WORK_OPTS_SHANAI if c_type in SHANAI_KENSA_TYPES else WORK_OPTS_STANDARD
                for r in saved_recs:
                    with st.expander(f"【{r.get('floor_level')} {r.get('area')}】 {r.get('issue_detail')}"):
                        new_f = st.radio("階", FLOOR_OPTS[1:], horizontal=True, key=f"f_{r['record_id']}")
                        new_a = st.radio("部", AREA_OPTS_SHANAI[1:] if c_type in SHANAI_KENSA_TYPES else AREA_OPTS_STANDARD[1:], horizontal=True, key=f"a_{r['record_id']}")
                        new_d = st.text_area("詳細", value=r.get('issue_detail'), key=f"d_{r['record_id']}")
                        new_w = st.radio("工種", edit_w_opts[1:], horizontal=True, key=f"w_{r['record_id']}")
                        np = _smart_camera(propName=c_name, inspType=c_type, inspDate=str(datetime.date.today()), locationText=f"{new_f} {new_a}", issueDetail=new_d, mode="insp", key=f"c_{r['record_id']}")
                        cy, cn = st.columns(2)
                        if cy.button("上書き", key=f"sy_{r['record_id']}", type="primary"):
                            up_data = {"floor_level": new_f, "area": new_a, "work_type": new_w, "issue_detail": new_d, "line_notified": True}
                            if np: url = upload_to_storage(np); up_data["issue_photo_url"] = url if url else np
                            db_patch("inspection_records", r['record_id'], up_data); st.rerun()
                        if cn.button("削除", key=f"sn_{r['record_id']}"): db_delete_record(r['record_id']); st.rerun()
            elif not st.session_state.issue_saved:
                prev_f = st.session_state.prev_floor; prev_a = st.session_state.prev_area
                w_opts = WORK_OPTS_KIKAN if c_type.startswith("【検査機関】") else WORK_OPTS_SHANAI if c_type in SHANAI_KENSA_TYPES else WORK_OPTS_STANDARD
                a_opts = AREA_OPTS_SHANAI if c_type in SHANAI_KENSA_TYPES else AREA_OPTS_STANDARD
                f = st.radio("階", FLOOR_OPTS[1:], horizontal=True) if not c_type.startswith("【検査機関】") else "一式"
                a = st.radio("部", a_opts[1:], horizontal=True) if not c_type.startswith("【検査機関】") else "全体"
                desc = st.text_area("詳細")
                w = st.radio("工種", w_opts[1:], horizontal=True)
                cam = _smart_camera(propName=c_name, inspType=c_type, inspDate=str(datetime.date.today()), locationText=f"{f} {a}", issueDetail=desc, mode="insp", key="cam_new")
                if cam: st.session_state.temp_photo = cam
                if st.button("一時保存", type="primary"):
                    if w and desc and st.session_state.temp_photo:
                        st.session_state.pending_records.append({"temp_id": str(uuid.uuid4()), "floor_level": f, "area": a, "work_type": w, "issue_detail": desc, "photo_b64": st.session_state.temp_photo})
                        st.session_state.issue_saved = True; st.session_state.temp_photo = None; st.session_state.prev_floor = f; st.session_state.prev_area = a; st.rerun()
                    else: st.error("全て必須です")
            else:
                st.success("一時保存完了")
                if st.button("続けて次を登録"): st.session_state.issue_saved = False; st.rerun()
                if st.button("保存データを確認"): st.session_state.edit_saved_records = True; st.rerun()
                if st.button("サーバーへ送信して終了"):
                    if not st.session_state.pending_records: st.session_state.current_box = None; st.rerun()
                    with st.spinner("送信中..."):
                        errs = 0
                        for rec in st.session_state.pending_records:
                            url = upload_to_storage(rec["photo_b64"])
                            if url and url != rec["photo_b64"]:
                                res = requests.post(f"{SUPABASE_URL}/rest/v1/inspection_records", headers=HEADERS, json={"record_id": str(uuid.uuid4()), "inspection_id": c_id, "property_id": c_prop_id, "floor_level": rec["floor_level"], "area": rec["area"], "work_type": rec["work_type"], "issue_detail": rec["issue_detail"], "progress_status": "確認待ち" if c_insp in ["工事監理チーム", "検査機関"] else "是正待ち", "line_notified": True, "issue_photo_url": url})
                                if res.status_code not in [200, 201, 204]: errs += 1
                            else: errs += 1
                        if errs == 0: clear_specific_cache("inspection_records"); st.session_state.pending_records=[]; st.session_state.current_box=None; st.session_state.issue_saved=False; st.rerun()
                        else: st.error("一部失敗しました")

    # 3. 検査内容確認（管理者）
    elif st.session_state.active_menu == "検査内容確認（管理者）":
        st.header("検査内容確認 ＆ 最終修正")
        sel_area = st.radio("絞り込み", ["すべて表示", "東海エリア", "関東エリア"], horizontal=True)
        sq = st.text_input("検索")
        recs = db_get("inspection_records", "select=inspection_id,progress_status&progress_status=eq.確認待ち")
        ins = {i.get('inspection_id'): i for i in db_get("inspections", "select=*") if isinstance(i, dict)}
        props = {p.get('property_id'): p for p in db_get("properties", "select=*") if isinstance(p, dict)}
        tree = {}
        for r in recs:
            if not isinstance(r, dict): continue
            i = ins.get(r.get('inspection_id'))
            if i:
                pid = i.get('property_id'); p = props.get(pid, {})
                if sel_area != "すべて表示" and p.get('area') != sel_area: continue
                pname = i.get('property_name', '不明'); tname = i.get('inspection_type', '不明')
                if pname not in tree: tree[pname] = {"types": {}, "pid": pid}
                tree[pname]["types"][tname] = tree[pname]["types"].get(tname, 0) + 1
        if sq: tree = {k: v for k, v in tree.items() if sq in k}
        
        if not st.session_state.drill_target:
            for p_name, v in tree.items():
                p_hdate = props.get(v['pid'], {}).get('handover_date', '')
                with st.expander(f"{p_name} (引渡し: {p_hdate or '未設定'})"):
                    for t_name, cnt in v["types"].items():
                        if st.button(f"{t_name} ({cnt}件)", key=f"f_{p_name}_{t_name}"): st.session_state.drill_target = {"prop": p_name, "type": t_name}; st.rerun()
            if not tree: st.info("確認待ちなし")
        else:
            sel = st.session_state.drill_target; prop_val, type_val = sel.get('prop'), sel.get('type')
            if st.button("⬅ 戻る"): st.session_state.drill_target = None; st.session_state.cached_records = None; st.rerun()
            t_ids = [str(i.get('inspection_id')) for i in ins.values() if i.get('property_name') == prop_val and i.get('inspection_type') == type_val]
            
            # 物件変更機能
            with st.expander("🔄 この検査の物件を変更する（間違えて登録した場合）"):
                p_opts = [p for p in props.values() if p.get('property_name') != prop_val]
                if p_opts:
                    new_p = st.selectbox("正しい物件", p_opts, format_func=lambda x: f"[{x.get('area')}] {x.get('property_name')}")
                    if st.button("移動", type="primary"):
                        success = True
                        for iid in t_ids:
                            if not db_patch_inspection(iid, {"property_id": new_p['property_id'], "property_name": new_p['property_name']}) or not db_patch("inspection_records", iid, {"property_id": new_p['property_id']}): success = False # Quick patch wrapper issue here, manual fix below
                            requests.patch(f"{SUPABASE_URL}/rest/v1/inspections?inspection_id=eq.{iid}", headers=HEADERS, json={"property_id": new_p['property_id'], "property_name": new_p['property_name']})
                            requests.patch(f"{SUPABASE_URL}/rest/v1/inspection_records?inspection_id=eq.{iid}", headers=HEADERS, json={"property_id": new_p['property_id']})
                        clear_specific_cache("inspections"); clear_specific_cache("inspection_records"); st.success("移動完了"); st.session_state.drill_target=None; time.sleep(1); st.rerun()

            if t_ids:
                recs_detail = sort_records(db_get("inspection_records", f"inspection_id=in.({','.join(t_ids)})&progress_status=eq.確認待ち"))
                if st.button("すべて承認して業者へ送る", type="primary"):
                    for r in recs_detail: requests.patch(f"{SUPABASE_URL}/rest/v1/inspection_records?record_id=eq.{r['record_id']}", headers=HEADERS, json={"progress_status": "是正待ち", "line_notified": True})
                    clear_specific_cache("inspection_records"); st.success("一括承認完了"); st.session_state.drill_target=None; time.sleep(1); st.rerun()
                for r in recs_detail:
                    with st.expander(f"【{r.get('floor_level')} {r.get('area')}】 {r.get('issue_detail')}"):
                        new_d = st.text_area("詳細", value=r.get('issue_detail'), key=f"dd_{r['record_id']}")
                        c_ok, c_del = st.columns(2)
                        if c_ok.button("承認", key=f"ok_{r['record_id']}"): db_patch("inspection_records", r['record_id'], {"progress_status": "是正待ち", "issue_detail": new_d}); st.rerun()
                        if c_del.button("削除", key=f"del_{r['record_id']}"): db_delete_record(r['record_id']); st.rerun()

    # 4-A. 是正実施（協力業者専用）＆ 4-B. ダッシュボード（管理者用）
    elif st.session_state.active_menu in ["是正実施（協力業者）", "是正ダッシュボード（管理者用）"]:
        is_admin = (st.session_state.active_menu == "是正ダッシュボード（管理者用）")
        st.header("是正ダッシュボード（確認・実施）" if is_admin else "是正実施")
        t_area = st.radio("表示エリア", ["すべて表示", "東海エリア", "関東エリア"], horizontal=True) if is_admin else st.session_state.target_area
        t_area = None if t_area == "すべて表示" else t_area
        
        status_filter = "in.(是正待ち,是正確認中)" if is_admin else ""
        recs = db_get("inspection_records", f"select=inspection_id,progress_status,record_id,area,floor_level,work_type,issue_detail" + (f"&progress_status={status_filter}" if status_filter else ""))
        ins = {i.get('inspection_id'): i for i in db_get("inspections", "select=*") if isinstance(i, dict)}
        props = {p.get('property_id'): p for p in db_get("properties", "select=*") if isinstance(p, dict)}
        
        tree = {}; counts = {}
        for r in recs:
            if not isinstance(r, dict): continue
            i = ins.get(r.get('inspection_id'))
            if i:
                pid = i.get('property_id'); p = props.get(pid, {})
                if t_area and p.get('area') != t_area: continue
                pname = i.get('property_name', '不明'); tname = i.get('inspection_type', '不明'); stat = r.get('progress_status')
                if pname not in tree: tree[pname] = {"types": set(), "pid": pid}
                tree[pname]["types"].add(tname)
                if pname not in counts: counts[pname] = {}
                if tname not in counts[pname]: counts[pname][tname] = {"wait_fix": 0, "wait_conf": 0, "total": 0, "done": 0, "unres": 0}
                counts[pname][tname]["total"] += 1
                if stat == "完了": counts[pname][tname]["done"] += 1
                elif stat == "是正確認中": counts[pname][tname]["wait_conf"] += 1; counts[pname][tname]["unres"] += 1
                elif stat == "是正待ち": counts[pname][tname]["wait_fix"] += 1; counts[pname][tname]["unres"] += 1
                else: counts[pname][tname]["unres"] += 1

        if not st.session_state.drill_target:
            for p_name, v in tree.items():
                p_hdate = props.get(v['pid'], {}).get('handover_date', '')
                with st.expander(f"{p_name} (引渡し: {p_hdate or '未設定'})"):
                    for t_name in sorted(list(v["types"])):
                        c = counts[p_name][t_name]
                        if not is_admin and c["wait_fix"] == 0: continue
                        btn_txt = t_name
                        badge = f"是正写真待ち:{c['wait_fix']} / 管理者確認待ち:{c['wait_conf']}" if is_admin else f"全{c['total']}件 [完了:{c['done']} / 未完了:{c['unres']}]"
                        col1, col2 = st.columns([3, 7])
                        if col1.button(btn_txt, key=f"f_{p_name}_{t_name}", use_container_width=True): st.session_state.drill_target = {"prop": p_name, "type": t_name}; st.rerun()
                        col2.markdown(f"<div class='badge-wrap' style='margin-top:15px;'><span style='color:#E74C3C;'>{badge}</span></div>", unsafe_allow_html=True)
        else:
            sel = st.session_state.drill_target; prop_val, type_val = sel.get('prop'), sel.get('type')
            if st.button("⬅ 戻る"): st.session_state.drill_target = None; st.session_state.skip_render_ids = []; st.rerun()
            
            t_ids = [str(i.get('inspection_id')) for i in ins.values() if i.get('property_name') == prop_val and i.get('inspection_type') == type_val]
            
            if is_admin:
                with st.expander("🔄 物件を変更する（間違えて登録した場合）"):
                    p_opts = [p for p in props.values() if p.get('property_name') != prop_val]
                    new_p = st.selectbox("正しい物件", p_opts, format_func=lambda x: f"[{x.get('area')}] {x.get('property_name')}")
                    if st.button("移動", type="primary"):
                        for iid in t_ids:
                            requests.patch(f"{SUPABASE_URL}/rest/v1/inspections?inspection_id=eq.{iid}", headers=HEADERS, json={"property_id": new_p['property_id'], "property_name": new_p['property_name']})
                            requests.patch(f"{SUPABASE_URL}/rest/v1/inspection_records?inspection_id=eq.{iid}", headers=HEADERS, json={"property_id": new_p['property_id']})
                        clear_specific_cache("inspections"); clear_specific_cache("inspection_records"); st.success("移動完了"); st.session_state.drill_target=None; time.sleep(1); st.rerun()
            
            recs_detail = sort_records(db_get("inspection_records", f"inspection_id=in.({','.join(t_ids)})" + ("&progress_status=in.(是正待ち,是正確認中)" if is_admin else "&progress_status=eq.是正待ち")))
            
            issue_count = 1
            for r in recs_detail:
                rid = r['record_id']; stat = r['progress_status']
                if rid in st.session_state.skip_render_ids: continue
                if is_admin and (issue_count == 4 or (issue_count > 4 and (issue_count - 4) % 4 == 0)): st.markdown('<div class="page-break"></div>', unsafe_allow_html=True)
                
                with st.container():
                    st.markdown(f'<div class="record-box {"report-item" if is_admin else ""}">', unsafe_allow_html=True)
                    st.markdown(f"**【{r.get('floor_level')} {r.get('area')}】 {r.get('issue_detail')}** <span style='color:red;'>[{stat}]</span>", unsafe_allow_html=True)
                    c1, c2 = st.columns(2)
                    with c1:
                        st.markdown("**Before**")
                        if r.get('issue_photo_url'): st.markdown(f'<img src="{r["issue_photo_url"]}" class="report-img">', unsafe_allow_html=True)
                    with c2:
                        if stat == "是正待ち":
                            st.markdown("**After 撮影**")
                            up = _smart_camera(propName=prop_val, inspType=type_val, inspDate=str(datetime.date.today()), locationText=f"{r.get('floor_level')} {r.get('area')}", issueDetail=r.get('issue_detail'), mode="fix", key=f"cam_{rid}")
                            if st.button("完了報告", key=f"s_{rid}", type="primary"):
                                if up: db_patch("inspection_records", rid, {"progress_status": "是正確認中", "fix_photo_url": upload_to_storage(up), "line_notified": True}); st.session_state.skip_render_ids.append(rid); st.rerun()
                        elif stat == "是正確認中" and is_admin:
                            st.markdown("**After**")
                            if r.get('fix_photo_url'): st.markdown(f'<img src="{r["fix_photo_url"]}" class="report-img">', unsafe_allow_html=True)
                            ca, cb = st.columns(2)
                            if ca.button("承認（完了）", key=f"ok_{rid}", type="primary"):
                                db_patch("inspection_records", rid, {"progress_status": "完了", "approved_date": str(datetime.date.today())}); st.session_state.skip_render_ids.append(rid); st.rerun()
                            if cb.button("否認", key=f"ng_{rid}"):
                                db_patch("inspection_records", rid, {"progress_status": "是正待ち"}); st.session_state.skip_render_ids.append(rid); st.rerun()
                    st.markdown('</div>', unsafe_allow_html=True)
                    issue_count += 1
            
            if is_admin and [r for r in recs_detail if r['progress_status'] == '是正確認中' and r['record_id'] not in st.session_state.skip_render_ids]:
                if st.button("写真提出済みの全項目を一括で承認する", type="primary", use_container_width=True):
                    for r in [r for r in recs_detail if r['progress_status'] == '是正確認中']:
                        requests.patch(f"{SUPABASE_URL}/rest/v1/inspection_records?record_id=eq.{r['record_id']}", headers=HEADERS, json={"progress_status": "完了", "approved_date": str(datetime.date.today())})
                    clear_specific_cache("inspection_records"); st.success("一括承認完了"); st.session_state.drill_target=None; time.sleep(1); st.rerun()

    # 5. 完了分一覧（共通）
    elif st.session_state.active_menu == "完了分一覧（共通）":
        st.header("完了分一覧")
        if not st.session_state.drill_target:
            recs = db_get("inspection_records", "select=inspection_id&progress_status=eq.完了")
            ins = {i.get('inspection_id'): i for i in db_get("inspections", "select=*") if isinstance(i, dict)}
            props = {p.get('property_id'): p for p in db_get("properties", "select=*") if isinstance(p, dict)}
            tree = {}
            for r in recs:
                i = ins.get(r.get('inspection_id'))
                if i:
                    pname = i.get('property_name', '不明'); tname = i.get('inspection_type', '不明'); pid = i.get('property_id')
                    if pname not in tree: tree[pname] = {"types": {}, "pid": pid}
                    tree[pname]["types"][tname] = tree[pname]["types"].get(tname, 0) + 1
            for p_name, v in tree.items():
                with st.expander(p_name):
                    for t_name, cnt in v["types"].items():
                        if st.button(f"{t_name} (完了: {cnt}件)", key=f"d_{p_name}_{t_name}"): st.session_state.drill_target = {"prop": p_name, "type": t_name}; st.rerun()
        else:
            sel = st.session_state.drill_target; prop_val, type_val = sel.get('prop'), sel.get('type')
            if st.button("⬅ 戻る"): st.session_state.drill_target = None; st.rerun()
            t_ids = [str(i.get('inspection_id')) for i in db_get("inspections", "select=*") if i.get('property_name') == prop_val and i.get('inspection_type') == type_val]
            
            if st.session_state.role == "admin":
                del_pass = st.text_input("削除用パスワードを入力 (5963)", type="password")
                if st.button(f"この検査データを完全に削除する", type="primary"):
                    if del_pass == DELETE_PASSWORD:
                        with st.spinner("削除中..."):
                            for iid in t_ids:
                                requests.delete(f"{SUPABASE_URL}/rest/v1/inspection_records?inspection_id=eq.{iid}", headers=HEADERS)
                                requests.delete(f"{SUPABASE_URL}/rest/v1/inspections?inspection_id=eq.{iid}", headers=HEADERS)
                            clear_specific_cache("inspection_records"); clear_specific_cache("inspections")
                        st.success("削除完了"); st.session_state.drill_target = None; time.sleep(1); st.rerun()
                    else: st.error("パスワードエラー")
                    
            recs_detail = sort_records(db_get("inspection_records", f"inspection_id=in.({','.join(t_ids)})&progress_status=eq.完了"))
            for idx, r in enumerate(recs_detail):
                st.markdown(f"**{idx+1}. 【{r.get('floor_level')} {r.get('area')}】 {r.get('issue_detail')}** (承認日: {r.get('approved_date', '')})")
                c1, c2 = st.columns(2)
                if r.get('issue_photo_url'): c1.image(r['issue_photo_url'], caption="Before", width=200)
                if r.get('fix_photo_url'): c2.image(r['fix_photo_url'], caption="After", width=200)
                st.markdown("---")

if __name__ == "__main__":
    try: main()
    except Exception as e:
        st.error("システムエラーが発生しました。電波の良い場所でやり直してください。")
        if st.button("システム復旧"): st.session_state.clear(); st.rerun()
