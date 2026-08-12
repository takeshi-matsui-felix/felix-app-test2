import streamlit as st
import streamlit.components.v1 as components
import requests
import uuid
import datetime
import base64
import io
import os
import tempfile
import threading
import json
import time

# 外部辞書ファイルの読み込み
from new_dictionary import ISSUE_TEMPLATES
# ===== 安全検証用：迷子写真の炙り出しとテスト =====
        if st.session_state.role == "admin":
            st.markdown("---")
            st.subheader("🔍 迷子写真の検証（Dry Run）")
            
            if st.button("1. 迷子写真を炙り出す（※ここでは削除されません）"):
                with st.spinner("照合中..."):
                    # DBの有効な写真リストを取得
                    valid_recs = db_get("inspection_records", "select=issue_photo_url,fix_photo_url")
                    valid_filenames = set()
                    for r in valid_recs:
                        if r.get('issue_photo_url'): valid_filenames.add(r['issue_photo_url'].split('/')[-1])
                        if r.get('fix_photo_url'): valid_filenames.add(r['fix_photo_url'].split('/')[-1])
                    
                    # Storageから全ファイルを取得して比較
                    orphans = []
                    for offset in range(0, 10000, 1000):
                        res = requests.post(f"{SUPABASE_URL}/storage/v1/object/list/photos", headers=HEADERS, json={"prefix": "", "limit": 1000, "offset": offset})
                        if res.status_code != 200: break
                        files = res.json()
                        if not files: break
                        for f in files:
                            fname = f.get('name')
                            if fname and fname != ".emptyFolderPlaceholder" and fname not in valid_filenames:
                                orphans.append(fname)
                    
                    st.session_state.orphans = orphans
                    st.success(f"炙り出し完了： {len(orphans)} 件の迷子写真が見つかりました。")

            if st.session_state.get("orphans"):
                st.write("▼ 迷子写真のリスト（最初の10件のみ表示）")
                st.write(st.session_state.orphans[:10])
                
                if st.button("2. 🧪 テスト：リストの一番上の1枚だけを削除してみる"):
                    test_target = st.session_state.orphans[0]
                    requests.delete(f"{SUPABASE_URL}/storage/v1/object/photos/{test_target}", headers=HEADERS)
                    st.success(f"ファイル「 {test_target} 」を削除しました。")
                    st.info("Supabaseの管理画面（Storage）を開き、このファイルが消えているか、他の大事な画像に影響が出ていないかをご確認ください。")
        # ===== ここまで =====
# ==========================================
# 1. Supabase 接続設定 ＆ キャッシュ機構（AM3:00クリア対応）
# ==========================================
SUPABASE_URL = "https://vzuzeymvyftmfuaxrvtb.supabase.co"
SUPABASE_KEY = "sb_publishable_2y-rvfayu8BYs0oo-UOzGA_EQTBYLxm"
HEADERS = {
    "apikey": SUPABASE_KEY, 
    "Authorization": f"Bearer {SUPABASE_KEY}", 
    "Content-Type": "application/json",
    "Prefer": "return=minimal"
}

DELETE_PASSWORD = "5963"

if "db_cache" not in st.session_state:
    st.session_state.db_cache = {}
if "last_cache_clear_date" not in st.session_state:
    st.session_state.last_cache_clear_date = None
if "pending_records" not in st.session_state:
    st.session_state.pending_records = []

def check_and_clear_am3_cache():
    now = datetime.datetime.now()
    today_str = now.strftime("%Y-%m-%d")
    if now.hour >= 3 and st.session_state.last_cache_clear_date != today_str:
        st.session_state.db_cache = {}
        st.session_state.last_cache_clear_date = today_str
        print("\n【定期クリーンアップ発動】毎朝AM3:00のキャッシュ初期化が正常に完了しました。\n")

def get_cached_data(cache_key, fetch_func, *args, **kwargs):
    check_and_clear_am3_cache()
    if cache_key in st.session_state.db_cache: return st.session_state.db_cache[cache_key]
    data = fetch_func(*args, **kwargs)
    st.session_state.db_cache[cache_key] = data
    return data

def clear_specific_cache(target_prefix):
    keys_to_del = [k for k in st.session_state.db_cache.keys() if k.startswith(target_prefix)]
    for k in keys_to_del: del st.session_state.db_cache[k]

# DB操作関数群
def _raw_db_get(table, params):
    url = f"{SUPABASE_URL}/rest/v1/{table}?{params}"
    try:
        res = requests.get(url, headers=HEADERS)
        if res.status_code == 200:
            data = res.json()
            if isinstance(data, list): return [d for d in data if isinstance(d, dict)]
            elif isinstance(data, dict): return [data]
        return []
    except Exception: return []

def db_get(table, params=""):
    cache_key = f"{table}_{params}"
    return get_cached_data(cache_key, _raw_db_get, table, params)

def db_post(table, data): 
    try:
        res = requests.post(f"{SUPABASE_URL}/rest/v1/{table}", headers=HEADERS, json=data)
        clear_specific_cache(table)
        return res.status_code in [200, 201, 204]
    except: return False

def db_patch(table, record_id, data): 
    try:
        res = requests.patch(f"{SUPABASE_URL}/rest/v1/{table}?record_id=eq.{record_id}", headers=HEADERS, json=data)
        clear_specific_cache(table)
        return res.status_code in [200, 204]
    except: return False

def db_patch_property(prop_id, data): 
    requests.patch(f"{SUPABASE_URL}/rest/v1/properties?property_id=eq.{prop_id}", headers=HEADERS, json=data)
    clear_specific_cache("properties")

def db_patch_inspections_by_prop(prop_id, new_name):
    requests.patch(f"{SUPABASE_URL}/rest/v1/inspections?property_id=eq.{prop_id}", headers=HEADERS, json={"property_name": new_name})
    clear_specific_cache("inspections")

def db_patch_inspection(ins_id, data):
    requests.patch(f"{SUPABASE_URL}/rest/v1/inspections?inspection_id=eq.{ins_id}", headers=HEADERS, json=data)
    clear_specific_cache("inspections")

def db_delete_record(record_id): 
    requests.delete(f"{SUPABASE_URL}/rest/v1/inspection_records?record_id=eq.{record_id}", headers=HEADERS)
    clear_specific_cache("inspection_records")

def db_delete_property(prop_id):
    requests.delete(f"{SUPABASE_URL}/rest/v1/inspection_records?property_id=eq.{prop_id}", headers=HEADERS)
    requests.delete(f"{SUPABASE_URL}/rest/v1/inspections?property_id=eq.{prop_id}", headers=HEADERS)
    requests.delete(f"{SUPABASE_URL}/rest/v1/properties?property_id=eq.{prop_id}", headers=HEADERS)
    clear_specific_cache("inspection_records")
    clear_specific_cache("inspections")
    clear_specific_cache("properties")

def upload_to_storage(base64_str):
    if not base64_str or not isinstance(base64_str, str): return None
    if base64_str.startswith("http://") or base64_str.startswith("https://"): return base64_str
    try:
        encoded = base64_str.split(",", 1)[1] if "," in base64_str else base64_str
        file_data = base64.b64decode(encoded)
        filename = f"{uuid.uuid4()}.jpg"
        url = f"{SUPABASE_URL}/storage/v1/object/photos/{filename}"
        res = requests.post(url, headers={"apikey": SUPABASE_KEY, "Authorization": f"Bearer {SUPABASE_KEY}", "Content-Type": "image/jpeg"}, data=file_data)
        if res.status_code not in [200, 201]: return base64_str
        return f"{SUPABASE_URL}/storage/v1/object/public/photos/{filename}"
    except Exception: return base64_str

# ==========================================
# 物件・指摘の並び替えアルゴリズム
# ==========================================
AREA_ORDER = ["玄関", "トイレ", "キッチン", "バルコニー", "LDK", "洋室", "洗面室", "UB", "廊下・階段・ENT", "外部", "フリー項目"]
WORK_ORDER = ["A.リペア", "B.清掃", "C.クロス", "D.造作", "E.水道", "F.電気", "G.キッチン", "H.サッシ", "I.外壁", "J.外構", "K.コーキング", "L.ガス", "板金", "Z.その他"]

def sort_records(records):
    def get_sort_key(r):
        area = r.get('area', '')
        work = r.get('work_type', '')
        area_idx = AREA_ORDER.index(area) if area in AREA_ORDER else 999
        work_idx = WORK_ORDER.index(work) if work in WORK_ORDER else 999
        return (area_idx, work_idx)
    return sorted(records, key=get_sort_key)

def sort_properties_by_handover(props_list):
    if not props_list: return []
    def get_handover_key(p):
        h_date = p.get('handover_date')
        if h_date and h_date.strip(): return (0, h_date)
        return (1, "9999-12-31")
    return sorted(props_list, key=get_handover_key)

# ==========================================
# 2. スマート電子黒板カメラ
# ==========================================
SMART_CAMERA_HTML = """<!DOCTYPE html>
<html lang="ja">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no">
    <style>
        body { margin: 0; padding: 5px; font-family: sans-serif; display: flex; flex-direction: column; align-items: center; background-color: transparent;}
        .btn-group { display: flex; gap: 10px; width: 100%; max-width: 400px; }
        .upload-btn {
            flex: 1; padding: 15px 5px;
            color: white; border-radius: 8px; font-size: 14px; font-weight: bold; text-align: center; cursor: pointer; 
            box-sizing: border-box; box-shadow: 0 4px 6px rgba(0,0,0,0.1); display: flex; justify-content: center; align-items: center;
        }
        input[type="file"] { display: none; }
    </style>
</head>
<body>
    <div class="btn-group">
        <label class="upload-btn" id="lbl-lib" style="background-color: #27AE60;">
            <span id="txt-lib">📁 ライブラリ</span>
            <input type="file" accept="image/*" id="file-lib">
        </label>
        <label class="upload-btn" id="lbl-cam" style="background-color: #2980B9;">
            <span id="txt-cam">📷 カメラ起動</span>
            <input type="file" accept="image/*" capture="environment" id="file-cam">
        </label>
    </div>
    <script>
        const isMobile = /Android|webOS|iPhone|iPad|iPod|BlackBerry|IEMobile|Opera Mini/i.test(navigator.userAgent) || 
                         (navigator.platform === 'MacIntel' && navigator.maxTouchPoints > 1);
        if (!isMobile) { document.getElementById('lbl-cam').style.display = 'none'; }

        let b = { propName: "", inspType: "", inspDate: "", locationText: "", issueDetail: "", mode: "insp" };
        window.addEventListener("message", function(e) {
            if (e.data.type === "streamlit:render" && e.data.args) {
                b.propName = e.data.args.propName || ""; b.inspType = e.data.args.inspType || ""; 
                b.inspDate = e.data.args.inspDate || ""; b.locationText = e.data.args.locationText || ""; 
                b.issueDetail = e.data.args.issueDetail || ""; b.mode = e.data.args.mode || "insp";
            }
        });

        function wrapTextAndReturnY(context, text, x, y, maxWidth, lineHeight, maxLines) {
            if (!text) return y;
            var words = text.split(''); var line = ''; var lineCount = 0;
            for(var n = 0; n < words.length; n++) {
                var testLine = line + words[n];
                if (context.measureText(testLine).width > maxWidth && n > 0) {
                    context.fillText(line, x, y); line = words[n]; y += lineHeight; lineCount++;
                    if (lineCount >= maxLines) return y;
                } else { line = testLine; }
            }
            context.fillText(line, x, y); return y + lineHeight;
        }

        function sendToStreamlit(val) { window.parent.postMessage({isStreamlitMessage: true, type: "streamlit:setComponentValue", value: val}, "*"); }

        function handleFile(e) {
            const file = e.target.files[0]; if (!file) return;
            document.getElementById('lbl-lib').style.backgroundColor = '#f39c12';
            document.getElementById('lbl-cam').style.backgroundColor = '#f39c12';
            document.getElementById('txt-lib').innerHTML = '合成中...';
            document.getElementById('txt-cam').innerHTML = 'お待ちを';

            const reader = new FileReader();
            reader.onload = function(event) {
                const img = new Image();
                img.onload = function() {
                    const MAX_SIZE = 800; let w = img.width, h = img.height;
                    if (w > h) { if (w > MAX_SIZE) { h *= MAX_SIZE / w; w = MAX_SIZE; } }
                    else { if (h > MAX_SIZE) { w *= MAX_SIZE / h; h = MAX_SIZE; } }
                    const canvas = document.createElement('canvas'); canvas.width = w; canvas.height = h;
                    const ctx = canvas.getContext('2d');
                    ctx.drawImage(img, 0, 0, w, h);

                    const bw = w * 0.40, bh = h * 0.32;
                    const sx = w - bw - 10, sy = h - bh - 10;
                    
                    ctx.fillStyle = (b.mode === 'fix') ? "rgba(0, 40, 80, 0.9)" : "rgba(0, 50, 0, 0.85)";
                    ctx.fillRect(sx, sy, bw, bh);
                    ctx.strokeStyle = "white"; ctx.lineWidth = 2; ctx.strokeRect(sx+5, sy+5, bw-10, bh-10);
                    
                    ctx.fillStyle = "white"; const fs = Math.floor(w * 0.022); 
                    ctx.font = fs + "px 'Yu Gothic Medium', 'Hiragino Kaku Gothic ProN', sans-serif";
                    
                    let ty = sy + fs + 12; const ls = fs * 1.4; const textX = sx + 10; const dw = bw - 20;

                    ty = wrapTextAndReturnY(ctx, b.propName, textX, ty, dw, ls, 2);
                    ty = wrapTextAndReturnY(ctx, b.inspType + "  " + b.inspDate, textX, ty, dw, ls, 2);
                    ty = wrapTextAndReturnY(ctx, b.locationText, textX, ty, dw, ls, 2);
                    ctx.fillStyle = "#ffdddd";
                    wrapTextAndReturnY(ctx, b.issueDetail, textX, ty, dw, ls, 3);

                    sendToStreamlit(canvas.toDataURL('image/jpeg', 0.6));
                    document.getElementById('lbl-lib').style.backgroundColor = '#2ecc71';
                    document.getElementById('lbl-cam').style.backgroundColor = '#2ecc71';
                    document.getElementById('txt-lib').innerHTML = '✅ 完了';
                    document.getElementById('txt-cam').innerHTML = '✅ 完了';
                };
                img.src = event.target.result;
            };
            reader.readAsDataURL(file);
        }

        document.getElementById('file-lib').addEventListener('change', handleFile);
        document.getElementById('file-cam').addEventListener('change', handleFile);

        window.onload = function() {
            window.parent.postMessage({isStreamlitMessage: true, type: "streamlit:componentReady", apiVersion: 1}, "*");
            window.parent.postMessage({isStreamlitMessage: true, type: "streamlit:setFrameHeight", height: 75}, "*");
        };
    </script>
</body>
</html>
"""
temp_dir = os.path.join(tempfile.gettempdir(), "felix_components_planb")
os.makedirs(temp_dir, exist_ok=True)
with open(os.path.join(temp_dir, "index.html"), "w", encoding="utf-8") as f: f.write(SMART_CAMERA_HTML)
_smart_camera = components.declare_component("smart_cam_planb", path=temp_dir)

# ==========================================
# 3. UI設定
# ==========================================
st.set_page_config(page_title="Felix検査App", layout="wide", initial_sidebar_state="collapsed")

st.markdown("""
<style>
    [data-testid="collapsedControl"] { display: none !important; }
    [data-testid="stSidebar"] { display: none !important; }

    div.stButton > button { border-radius: 6px; height: 50px; font-weight: bold; width: 100%; margin-bottom: 5px; }
    footer {visibility: hidden;}
    [data-testid="stStatusWidget"] { display: none; }
    .record-box { border-bottom: 2px solid #EEEEEE; padding-bottom: 20px; margin-bottom: 20px; }
    .badge-wrap { display: inline-flex; align-items: center; gap: 8px; font-size: 13px; font-weight: bold; margin-left: 5px; color: #d93025; }
    
    div[data-testid="column"] button { height: 35px !important; font-size: 12px !important; font-weight: normal !important; padding: 0 !important; }

    .floating-back-btn {
        position: fixed !important;
        top: 15px !important;
        left: 15px !important;
        z-index: 999999 !important;
        width: auto !important;
    }
    .floating-back-btn button {
        background-color: #34495e !important;
        color: white !important;
        border-radius: 30px !important;
        padding: 5px 20px !important;
        box-shadow: 0 4px 6px rgba(0,0,0,0.3) !important;
        border: 2px solid white !important;
        font-size: 14px !important;
        font-weight: bold !important;
        height: auto !important;
        min-height: 40px !important;
    }
    .floating-back-btn button p { color: white !important; margin: 0 !important; }

    .report-img {
        width: 100%;
        max-height: 250px;
        object-fit: contain;
        border-radius: 4px;
    }

    @media print {
        .stButton, .stTextInput, .stRadio, .stSelectbox, .stCheckbox, [data-testid="stExpander"], .floating-back-btn { display: none !important; }
        .admin-delete-box, hr { display: none !important; }
        
        .main .block-container { padding: 0 !important; margin: 0 !important; max-width: 100% !important; }
        
        .report-img {
            max-height: 400px !important;
        }

        .report-item {
            page-break-inside: avoid !important;
            break-inside: avoid !important;
            padding-bottom: 25px !important;
        }
        .page-break {
            page-break-before: always !important;
            break-before: page !important;
            height: 0 !important;
            margin: 0 !important;
            padding: 0 !important;
        }
    }
</style>
""", unsafe_allow_html=True)

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
INSP_OPTS = [
    "-- 選択 --", "配筋検査", "躯体検査", "断熱検査", "中間検査", 
    "社内検査(設計)", "社内検査(建設)", "社内検査(マーケ)", "社内検査(不動産)",
    "【検査機関】配筋検査", "【検査機関】躯体検査", "【検査機関】断熱検査", "【検査機関】中間検査", "【検査機関】完了検査"
]
SHANAI_KENSA_TYPES = ["社内検査(設計)", "社内検査(建設)", "社内検査(マーケ)", "社内検査(不動産)"]
INSPECTOR_OPTS = ["工事監理チーム", "建設部", "不動産事業部", "マーケティング部", "検査機関"]

# ==========================================
# 5. セッション管理 
# ==========================================
for key in ["role", "active_menu", "pre_selected_prop", "delete_target", "edit_prop_target", "skip_render_ids", "show_bulk_confirm", "edit_saved_records", "cached_records", "cached_target_id", "temp_photo", "prev_floor", "prev_area", "splash_done", "logout_triggered"]:
    if key not in st.session_state: st.session_state[key] = None

if st.session_state.skip_render_ids is None: st.session_state.skip_render_ids = []
if "issue_saved" not in st.session_state: st.session_state.issue_saved = False
if "drill_target" not in st.session_state or not isinstance(st.session_state.drill_target, dict): st.session_state.drill_target = None
if "current_box" not in st.session_state or not isinstance(st.session_state.current_box, dict): st.session_state.current_box = None
if st.session_state.splash_done is None: st.session_state.splash_done = False
if "target_area" not in st.session_state: st.session_state.target_area = None

def jump_to_menu(menu_name, prop_id=None):
    st.session_state.active_menu = menu_name
    st.session_state.pre_selected_prop = prop_id
    st.session_state.drill_target = None
    st.session_state.current_box = None
    st.session_state.delete_target = None
    st.session_state.edit_prop_target = None
    st.session_state.issue_saved = False
    st.session_state.skip_render_ids = []
    st.session_state.show_bulk_confirm = False
    st.session_state.edit_saved_records = False
    st.session_state.cached_records = None
    st.session_state.cached_target_id = None
    st.session_state.temp_photo = None
    st.session_state.prev_floor = None
    st.session_state.prev_area = None
    st.rerun()

# ==========================================
# 6. メイン画面・機能
# ==========================================
def main():

    components.html("""
    <script>
    function floatBackButton() {
        const doc = window.parent.document;
        const buttons = Array.from(doc.querySelectorAll('button'));
        buttons.forEach(b => {
            if(b.innerText.includes('⬅ 戻る')) {
                const container = b.closest('div.stButton');
                if(container && !container.classList.contains('floating-back-btn')) {
                    container.classList.add('floating-back-btn');
                }
            }
        });
    }
    floatBackButton();
    const observer = new MutationObserver(floatBackButton);
    observer.observe(window.parent.document.body, {childList: true, subtree: true});
    </script>
    """, height=0)

    if st.session_state.logout_triggered:
        components.html("<script>localStorage.removeItem('felix_user_auth');</script>", height=0)
        time.sleep(0.5)
        st.session_state.clear()
        st.rerun()

    if st.session_state.role is None:
        role_html = """
        <!DOCTYPE html>
        <html>
        <head>
        <style>
            body { font-family: 'Helvetica Neue', Arial, sans-serif; padding: 20px; display: flex; flex-direction: column; align-items: center; justify-content: center; height: 100vh; margin: 0; background: #f8f9fa; }
            .btn { display: block; width: 100%; max-width: 320px; padding: 18px; margin: 12px 0; font-size: 16px; font-weight: bold; color: white; border: none; border-radius: 8px; cursor: pointer; text-align: center; box-shadow: 0 4px 6px rgba(0,0,0,0.1); transition: opacity 0.2s; }
            .btn:active { opacity: 0.8; }
            .btn-admin { background-color: #2C3E50; }
            .btn-partner-tokai { background-color: #27AE60; }
            .btn-partner-kanto { background-color: #2980B9; }
            h2 { color: #333; margin-bottom: 20px; font-size: 20px; text-align: center; }
            p { color: #666; font-size: 13px; text-align: center; margin-bottom: 30px; }
        </style>
        </head>
        <body>
            <div id="loading"><h3>認証情報を確認中...</h3></div>
            <div id="selector" style="display: none; width: 100%; text-align: center;">
                <h2>ログインアカウントの選択</h2>
                <p>※一度選択すると、次回以降はこの画面をスキップして自動で開きます。</p>
                <button class="btn btn-admin" onclick="setRole('admin', '')">💻 管理者として入室</button>
                <button class="btn btn-partner-tokai" onclick="setRole('partner', '東海エリア')">🛠️ 協力業者 (東海エリア)</button>
                <button class="btn btn-partner-kanto" onclick="setRole('partner', '関東エリア')">🛠️ 協力業者 (関東エリア)</button>
            </div>
            <script>
                function sendToStreamlit(data) {
                    window.parent.postMessage({isStreamlitMessage: true, type: "streamlit:setComponentValue", value: data}, "*");
                }
                function setRole(role, area) {
                    const data = {role: role, area: area};
                    localStorage.setItem('felix_user_auth', JSON.stringify(data));
                    sendToStreamlit(data);
                }
                window.onload = function() {
                    window.parent.postMessage({isStreamlitMessage: true, type: "streamlit:componentReady", apiVersion: 1}, "*");
                    window.parent.postMessage({isStreamlitMessage: true, type: "streamlit:setFrameHeight", height: 500}, "*");
                    const saved = localStorage.getItem('felix_user_auth');
                    if (saved) {
                        try {
                            const data = JSON.parse(saved);
                            if (data.role) { sendToStreamlit(data); return; }
                        } catch(e) {}
                    }
                    document.getElementById('loading').style.display = 'none';
                    document.getElementById('selector').style.display = 'block';
                };
            </script>
        </body>
        </html>
        """
        temp_dir_auth = os.path.join(tempfile.gettempdir(), "felix_auth_comp")
        os.makedirs(temp_dir_auth, exist_ok=True)
        with open(os.path.join(temp_dir_auth, "index.html"), "w", encoding="utf-8") as f: f.write(role_html)
        _auth_menu = components.declare_component("auth_menu", path=temp_dir_auth)
        auth_res = _auth_menu(key="auth_comp")

        if auth_res:
            st.session_state.role = auth_res.get("role")
            st.session_state.target_area = auth_res.get("area")
            st.session_state.active_menu = "ホーム"
            st.session_state.splash_done = False
            st.rerun()
        st.stop()

    confirm_cnt = 0
    if st.session_state.role == "admin":
        wait_conf_recs = db_get("inspection_records", "select=record_id&progress_status=eq.確認待ち")
        confirm_cnt = len(wait_conf_recs)

    def format_menu(m):
        if m == "検査内容確認（管理者）" and confirm_cnt > 0:
            return f"{m} (未確認{confirm_cnt}件)"
        return m

    if st.session_state.role == "admin":
        menu_opts = ["ホーム", "物件登録（管理者）", "検査実施（管理者）", "検査内容確認（管理者）", "是正ダッシュボード（管理者用）", "完了分一覧（共通）"]
    else:
        menu_opts = ["ホーム", "是正実施（協力業者）", "完了分一覧（共通）"]
        
    if st.session_state.active_menu not in menu_opts: st.session_state.active_menu = menu_opts[0]
    
    with st.expander(f"メニューを開く (現在のユーザー: {st.session_state.role})", expanded=False):
        selected_menu = st.radio("移動先を選択", menu_opts, index=menu_opts.index(st.session_state.active_menu), format_func=format_menu, label_visibility="collapsed")
        
        st.markdown("<br>", unsafe_allow_html=True)
        if st.button("ログアウト / アカウントの切り替え"):
            st.session_state.logout_triggered = True
            st.rerun()

    if selected_menu != st.session_state.active_menu:
        jump_to_menu(selected_menu, st.session_state.pre_selected_prop)

    # ----------------------------------------
    # メニュー: 0. ホーム
    # ----------------------------------------
    if st.session_state.active_menu == "ホーム":
        if not st.session_state.splash_done:
            st.markdown("""
            <style>
            .splash { display: flex; justify-content: center; align-items: center; height: 100vh; font-size: 16px; color: #555; position: fixed; top: 0; left: 0; width: 100vw; background: white; z-index: 999999; letter-spacing: 2px; font-family: sans-serif; }
            </style>
            <div class="splash">FELIX Inspection System...</div>
            """, unsafe_allow_html=True)
            time.sleep(1.5)
            st.session_state.splash_done = True
            st.rerun()
        else:
            role = st.session_state.role
            new_btn_text = "新規検査を開始する" if role == "admin" else "新規是正を開始する"
            ls_key = "felix_session" if role == "admin" else "felix_partner_session"
            
            menu_html = f"""
            <!DOCTYPE html>
            <html>
            <head>
            <style>
                body {{ margin:0; font-family: sans-serif; display: flex; flex-direction: column; height: 100vh; background: transparent; }}
                .menu-item {{ font-size: 16px; color: #333; cursor: pointer; margin: 24px 0; text-align: center; transition: color 0.2s; user-select: none; }}
                .menu-item:hover {{ color: #888; }}
                .container {{ position: absolute; top: 38.2%; left: 50%; transform: translate(-50%, -50%); width: 100%; }}
            </style>
            </head>
            <body>
            <div class="container">
                <div class="menu-item" onclick="sendVal('new')">{new_btn_text}</div>
                <div class="menu-item" id="resume-btn" style="display:none;" onclick="sendVal('resume')"></div>
            </div>
            <script>
                function sendVal(action) {{
                    let val = {{ action: action }};
                    if(action === 'resume') {{ val.data = JSON.parse(localStorage.getItem('{ls_key}')); }}
                    window.parent.postMessage({{isStreamlitMessage: true, type: "streamlit:setComponentValue", value: val}}, "*");
                }}
                const saved = localStorage.getItem('{ls_key}');
                if(saved) {{
                    try {{
                        const data = JSON.parse(saved);
                        let text = '';
                        if('{role}' === 'admin' && data.name && data.type) {{ text = '前回の続きから再開する（' + data.name + ' / ' + data.type + '）'; }} 
                        else if ('{role}' === 'partner' && data.prop && data.type) {{ text = '前回の続きから再開する（' + data.prop + ' / ' + data.type + '）'; }}
                        if(text) {{
                            const btn = document.getElementById('resume-btn');
                            btn.style.display = 'block'; btn.innerText = text;
                        }}
                    }} catch(e) {{}}
                }}
                window.onload = function() {{
                    window.parent.postMessage({{isStreamlitMessage: true, type: "streamlit:componentReady", apiVersion: 1}}, "*");
                    window.parent.postMessage({{isStreamlitMessage: true, type: "streamlit:setFrameHeight", height: 500}}, "*");
                }};
            </script>
            </body>
            </html>
            """
            temp_dir_menu = os.path.join(tempfile.gettempdir(), f"felix_home_menu_{role}")
            os.makedirs(temp_dir_menu, exist_ok=True)
            with open(os.path.join(temp_dir_menu, "index.html"), "w", encoding="utf-8") as f: f.write(menu_html)
            _home_menu = components.declare_component(f"home_menu_{role}", path=temp_dir_menu)
            res = _home_menu(key=f"home_menu_comp_{role}")
            
            if res:
                if res.get('action') == 'new':
                    st.session_state.active_menu = "検査実施（管理者）" if role == "admin" else "是正実施（協力業者）"
                    st.session_state.current_box = None; st.session_state.drill_target = None; st.rerun()
                elif res.get('action') == 'resume' and res.get('data'):
                    d = res['data']
                    if role == "admin":
                        st.session_state.active_menu = "検査実施（管理者）"
                        st.session_state.current_box = {"id": d.get('id', str(uuid.uuid4())), "prop_id": d.get('prop_id'), "name": d.get('name'), "type": d.get('type'), "inspector": d.get('inspector')}
                        st.session_state.prev_floor = d.get('prev_floor'); st.session_state.prev_area = d.get('prev_area')
                    else:
                        st.session_state.active_menu = "是正実施（協力業者）"
                        st.session_state.drill_target = {"prop": d.get('prop'), "type": d.get('type')}
                    st.rerun()

    # ----------------------------------------
    # メニュー: 1. 物件登録（管理者）
    # ----------------------------------------
    elif st.session_state.active_menu == "物件登録（管理者）":
        st.header("物件登録")
        with st.container():
            input_area = st.selectbox("エリアを選択", ["東海エリア", "関東エリア"])
            name = st.text_input("新規物件名")
            set_handover = st.checkbox("引渡し日を設定する", value=False, key="set_h_new")
            if set_handover: handover_date_val = st.date_input("引渡し日", value=datetime.date.today(), key="h_date_new")
            else: handover_date_val = None
            if st.button("登録"):
                if name:
                    h_str = str(handover_date_val) if set_handover and handover_date_val else None
                    db_post("properties", {"property_id": str(uuid.uuid4()), "property_name": name, "area": input_area, "handover_date": h_str})
                    st.success(f"[{input_area}] に登録完了"); st.rerun()
        st.markdown("---")
        st.subheader("登録済み物件一覧")
        filter_area = st.radio("一覧のエリア絞り込み", ["すべて表示", "東海エリア", "関東エリア"], horizontal=True)
        props = db_get("properties", "select=*")
        props = sort_properties_by_handover(props)
        all_ins = db_get("inspections", "select=property_id")
        prop_ins_counts = {}
        for ins in all_ins:
            pid = ins.get('property_id')
            if pid: prop_ins_counts[pid] = prop_ins_counts.get(pid, 0) + 1
        
        for idx, p in enumerate(props):
            prop_id = p.get('property_id')
            if not prop_id: continue
            p_area = p.get('area', '未設定')
            if filter_area != "すべて表示" and p_area != filter_area: continue
            p_name = p.get('property_name', '不明'); p_hdate = p.get('handover_date')
            hdate_disp = f" (引渡し: {p_hdate})" if p_hdate else " (引渡し日: 未設定)"
            ins_count = prop_ins_counts.get(prop_id, 0)
            count_disp = f"（データ: {ins_count}件）" if ins_count > 0 else "（データなし）"
            btn_text = f"[{p_area}] {p_name}{hdate_disp} {count_disp} 検査へ"
            key_suffix = f"{prop_id}_{idx}"
            
            c1, c2, c3 = st.columns([6, 2, 2])
            if c1.button(btn_text, key=f"p_{key_suffix}"): jump_to_menu("検査実施（管理者）", prop_id)
            if c2.button("変更", key=f"e_{key_suffix}"):
                st.session_state.edit_prop_target = prop_id; st.session_state.delete_target = None; st.rerun()
            if c3.button("削除", key=f"d_{key_suffix}"): 
                st.session_state.delete_target = prop_id; st.session_state.edit_prop_target = None; st.rerun()
            
            if st.session_state.edit_prop_target == prop_id:
                st.warning(f"「{p_name}」の内容を変更します。過去のデータ名も連動して更新されます。")
                new_name = st.text_input("物件名を入力", value=p_name, key=f"new_name_{key_suffix}")
                has_hdate = True if p_hdate and p_hdate.strip() else False
                try: init_d = datetime.datetime.strptime(p_hdate, "%Y-%m-%d").date() if has_hdate else datetime.date.today()
                except: init_d = datetime.date.today(); has_hdate = False
                edit_set_handover = st.checkbox("引渡し日を設定する", value=has_hdate, key=f"eh_cb_{key_suffix}")
                if edit_set_handover: new_hdate = st.date_input("引渡し日を変更", value=init_d, key=f"new_h_{key_suffix}")
                else: new_hdate = None
                
                col_y, col_n = st.columns(2)
                if col_y.button("保存", key=f"save_name_{key_suffix}", type="primary"):
                    nh_str = str(new_hdate) if edit_set_handover and new_hdate else None
                    db_patch_property(prop_id, {"property_name": new_name, "handover_date": nh_str})
                    if new_name != p_name: db_patch_inspections_by_prop(prop_id, new_name)
                    st.success("変更を保存しました"); st.session_state.edit_prop_target = None; st.rerun()
                if col_n.button("キャンセル", key=f"cancel_name_{key_suffix}"): st.session_state.edit_prop_target = None; st.rerun()
                st.markdown("---")
                
            if st.session_state.delete_target == prop_id:
                st.warning(f"本当に「{p_name}」を削除しますか？紐づくすべてのデータが消えます。")
                del_pw = st.text_input("削除用パスワードを入力", type="password", key=f"pw_{key_suffix}", placeholder="5963")
                col_y, col_n = st.columns(2)
                if col_y.button("Yes (削除実行)", key=f"yes_{key_suffix}"):
                    if del_pw == DELETE_PASSWORD:
                        db_delete_property(prop_id); st.session_state.delete_target = None; st.session_state.current_box = None; st.rerun()
                    else: st.error("パスワードが違います")
                if col_n.button("キャンセル", key=f"no_{key_suffix}"): st.session_state.delete_target = None; st.rerun()
                st.markdown("---")

# ----------------------------------------
    # メニュー: 2. 検査実施（管理者）
    # ----------------------------------------
    elif st.session_state.active_menu == "検査実施（管理者）":
        if not st.session_state.current_box:
            st.header("検査開始")
            props = db_get("properties", "select=*")
            props = sort_properties_by_handover(props)
            if st.session_state.pre_selected_prop is None:
                if props: st.session_state.pre_selected_prop = props[0].get("property_id")

            area_opts = ["-- 選択 --", "東海エリア", "関東エリア"]; init_area_idx = 0
            if st.session_state.pre_selected_prop:
                pre_prop = next((p for p in props if p.get('property_id') == st.session_state.pre_selected_prop), None)
                if pre_prop and pre_prop.get('area') in area_opts: init_area_idx = area_opts.index(pre_prop.get('area'))
            
            sel_area = st.selectbox("エリアを選択", area_opts, index=init_area_idx)
            search_query = st.text_input("物件名で検索（一部入力でも可）", key="search_insp")
            filtered_props = [p for p in props if p.get('area') == sel_area and p.get('property_id')] if sel_area != "-- 選択 --" else []
            if search_query: filtered_props = [p for p in filtered_props if search_query in p.get('property_name', '')]
                
            opts = [{"property_id": None, "property_name": "-- 選択 --"}] + filtered_props
            idx = next((i for i, p in enumerate(opts) if p.get('property_id') == st.session_state.pre_selected_prop), 0)
            
            def format_prop_selectbox(x):
                if x.get('property_id') is None: return x.get('property_name')
                h_disp = f" (引渡し: {x.get('handover_date')})" if x.get('handover_date') else " (引渡し未設定)"
                return f"{x.get('property_name')}{h_disp}"

            st.markdown("<p style='color:gray; font-size:12px; margin-bottom:0;'>物件は引渡し日が一番近い順に並んでいます</p>", unsafe_allow_html=True)
            target = st.selectbox("物件を選択", opts, index=idx, format_func=format_prop_selectbox)
            ins_type = st.selectbox("検査種類を選択", INSP_OPTS)
            
            c1, c2 = st.columns(2)
            ins_date = c1.date_input("検査日時", datetime.date.today())
            inspector = c2.selectbox("検査員", INSPECTOR_OPTS)
            
            if st.button("検査スタート"):
                prop_name = target.get('property_name'); prop_id = target.get('property_id')
                if prop_name != "-- 選択 --" and ins_type != "-- 選択 --":
                    nid = str(uuid.uuid4())
                    with st.spinner("通信中..."):
                        res_ok = db_post("inspections", {"inspection_id": nid, "property_id": prop_id, "property_name": prop_name, "inspection_type": ins_type, "inspection_date": str(ins_date), "inspector": inspector})
                    
                    if res_ok:
                        st.session_state.current_box = {"id": nid, "prop_id": prop_id, "name": prop_name, "type": ins_type, "inspector": inspector}
                        st.session_state.pre_selected_prop = prop_id
                        st.session_state.issue_saved = False; st.session_state.edit_saved_records = False; st.session_state.cached_records = None; st.session_state.temp_photo = None
                        st.session_state.prev_floor = None; st.session_state.prev_area = None
                        st.session_state.pending_records = []
                        st.rerun()
                    else:
                        st.error("通信エラー：サーバーとの接続に失敗しました。電波の良い場所でもう一度お試しください。")
                else: st.error("物件と検査種類を選んでください")
        else:
            cb = st.session_state.current_box
            if not isinstance(cb, dict): cb = {}
            c_name = cb.get('name', ''); c_type = cb.get('type', ''); c_id = cb.get('id', ''); c_prop_id = cb.get('prop_id', ''); c_inspector = cb.get('inspector', '')
            
            if st.button("⬅ 戻る", key="back_from_insp"):
                st.session_state.current_box = None; st.session_state.issue_saved = False; st.session_state.edit_saved_records = False; st.session_state.cached_records = None; st.session_state.temp_photo = None; st.session_state.prev_floor = None; st.session_state.prev_area = None; st.rerun()
            
            st.subheader(f"{c_name} / {c_type}")

            cb_data = cb.copy()
            cb_data['prev_floor'] = st.session_state.prev_floor; cb_data['prev_area'] = st.session_state.prev_area
            json_str = json.dumps(cb_data, ensure_ascii=False)
            components.html(f"<script>localStorage.setItem('felix_session', JSON.stringify({json_str}));</script>", height=0)
            
            if st.session_state.get("edit_saved_records"):
                st.markdown("#### 今回の検査で記録した指摘データ")
                if st.button("⬅ 戻る", key="back_to_edit_top"): st.session_state.edit_saved_records = False; st.rerun()
                st.markdown("---")
                
                if st.session_state.pending_records:
                    st.markdown("<h5 style='color:#E74C3C;'>⚠️ スマホ内に一時保存中のデータ（終了ボタンで一括送信されます）</h5>", unsafe_allow_html=True)
                    for idx, rec in enumerate(st.session_state.pending_records):
                        with st.container():
                            st.markdown('<div class="record-box" style="border:2px solid #E74C3C; padding:10px; border-radius:5px;">', unsafe_allow_html=True)
                            head_text = "" if c_type.startswith("【検査機関】") or rec['floor_level'] == "一式" else f"【{rec['floor_level']} {rec['area']}】".strip()
                            title = f"{head_text} {rec['issue_detail']}" if head_text else f"【指摘内容】 {rec['issue_detail']}"
                            st.markdown(f"**{title}**")
                            st.image(rec["photo_b64"], width=250)
                            
                            if st.button("この未送信データを削除（撮り直す場合）", key=f"del_pend_{rec['temp_id']}"):
                                st.session_state.pending_records = [r for r in st.session_state.pending_records if r['temp_id'] != rec['temp_id']]
                                st.rerun()
                            st.markdown('</div>', unsafe_allow_html=True)
                    st.markdown("---")

                st.markdown("##### サーバーへ送信済みの過去データ")
                saved_recs = db_get("inspection_records", f"inspection_id=eq.{c_id}")
                if not saved_recs: st.info("サーバーに保存された過去の指摘データはありません。")
                else:
                    if c_type in SHANAI_KENSA_TYPES:
                        floors_in_recs = sorted(list(set([r.get('floor_level', '一式') for r in saved_recs if r.get('floor_level')])))
                        sel_floor = st.selectbox("部屋（階層）で絞り込み", ["すべて表示"] + floors_in_recs, key="filter_edit_floor")
                        if sel_floor != "すべて表示": saved_recs = [r for r in saved_recs if r.get('floor_level') == sel_floor]
                
                    edit_w_opts = WORK_OPTS_KIKAN if c_type.startswith("【検査機関】") else WORK_OPTS_SHANAI if c_type in SHANAI_KENSA_TYPES else WORK_OPTS_KUTAI if c_type == "躯体検査" else WORK_OPTS_HAIKIN if c_type == "配筋検査" else WORK_OPTS_CHUKAN if c_type == "中間検査" else WORK_OPTS_DANNETSU if c_type == "断熱検査" else WORK_OPTS_STANDARD
                    saved_recs = sort_records(saved_recs)

                    for r in saved_recs:
                        rec_id = r.get('record_id')
                        if not rec_id: continue
                        floor = r.get('floor_level', ''); area = r.get('area', ''); detail = r.get('issue_detail', ''); orig_w = r.get('work_type', '')
                        head_text = "" if c_type.startswith("【検査機関】") or floor == "one" or floor == "一式" else f"【{floor} {area}】".strip()
                        title = f"{head_text} {detail}" if head_text else f"【指摘内容】 {detail}"
                        
                        with st.container():
                            st.markdown('<div class="record-box">', unsafe_allow_html=True)
                            st.markdown(f"**{title}**")
                            if r.get('issue_photo_url'): 
                                photo_url = r.get('issue_photo_url')
                                st.markdown(f'<a href="{photo_url}" target="_blank"><img src="{photo_url}" class="report-img"></a>', unsafe_allow_html=True)
                                
                            with st.expander("内容を修正・差し替え・削除"):
                                new_f = floor; new_a = area; sel_temp = None; default_w = ""
                                if not c_type.startswith("【検査機関】"):
                                    a_opts = AREA_OPTS_SHANAI if c_type in SHANAI_KENSA_TYPES else AREA_OPTS_STANDARD
                                    if c_type not in ["配筋検査", "躯体検査", "断熱検査", "中間検査"]:
                                        f_idx = FLOOR_OPTS[1:].index(floor) if floor in FLOOR_OPTS[1:] else 0
                                        new_f = st.radio("階層を変更", FLOOR_OPTS[1:], index=f_idx, horizontal=True, key=f"ef_{rec_id}")
                                        a_idx = a_opts[1:].index(area) if area in a_opts[1:] else 0
                                        new_a = st.radio("部位を変更", a_opts[1:], index=a_idx, horizontal=True, key=f"ea_{rec_id}")
                                    
                                    cat_dict = ISSUE_TEMPLATES.get(c_type, {}) if c_type in ["配筋検査", "躯体検査", "断熱検査", "中間検査"] else ISSUE_TEMPLATES.get("社内検査(設計)", {}).get(new_a, {}) if c_type in SHANAI_KENSA_TYPES else {}
                                    if not isinstance(cat_dict, dict): cat_dict = {}
                                    cat_keys = list(cat_dict.keys())
                                    sel_cat = st.radio("分類を変更", cat_keys, horizontal=True, key=f"ecat_{rec_id}") if cat_keys else None
                                    
                                    if sel_cat:
                                        detail_items = cat_dict.get(sel_cat, [])
                                        if not isinstance(detail_items, list): detail_items = []
                                        temp_list = detail_items + ["その他（フリー項目）"]
                                        sel_temp = st.radio("よくある指摘事項", temp_list, key=f"etemp_{rec_id}", horizontal=True)
                                        default_w = ""
                                
                                edit_desc_val = detail.split(":", 1)[1] if ":" in detail else detail.split("：", 1)[1] if "：" in detail else detail
                                st.markdown("##### 詳細・場所の追記を変更")
                                new_detail = st.text_area("詳細情報を変更", value=edit_desc_val, label_visibility="collapsed", key=f"ed_desc_{rec_id}")
                                
                                disp_w_opts = edit_w_opts[1:]
                                if default_w in disp_w_opts: w_idx = disp_w_opts.index(default_w)
                                elif orig_w in disp_w_opts: w_idx = disp_w_opts.index(orig_w)
                                else: w_idx = 0
                                new_w = st.radio("工種を変更", disp_w_opts, index=w_idx, horizontal=True, key=f"ed_work_{rec_id}_{sel_cat}_{sel_temp}")
                                
                                if sel_temp == "その他（フリー項目）": final_desc = new_detail.strip()
                                else: final_desc = (sel_temp + ("：" + new_detail.strip() if new_detail.strip() != "" else "")) if sel_temp else new_detail.strip()
                                if final_desc == "": final_desc = detail 
                                
                                loc_parts = [str(new_f), str(new_a)]
                                if not c_type.startswith("【検査機関】") and sel_cat: loc_parts.append(str(sel_cat))
                                loc_str = " ".join(loc_parts).strip()
                                disp_desc = final_desc[:80] + "..." if len(final_desc) > 80 else final_desc
                                
                                st.write("写真を差し替える場合のみ撮影/選択してください")
                                new_photo = _smart_camera(
                                    propName=c_name, inspType=c_type, inspDate=datetime.date.today().strftime("%Y/%m/%d"), 
                                    locationText=loc_str, issueDetail=disp_desc, mode="insp", key=f"ed_cam_{rec_id}"
                                )
                                
                                c_save, c_del = st.columns(2)
                                if c_save.button("この内容で上書き", key=f"ed_save_{rec_id}", type="primary"):
                                    with st.spinner("保存中..."):
                                        up_data = {"floor_level": new_f, "area": new_a, "work_type": new_w, "issue_detail": final_desc, "line_notified": True}
                                        if new_photo:
                                            url = upload_to_storage(new_photo)
                                            if url and url != new_photo: up_data["issue_photo_url"] = url
                                        db_patch("inspection_records", rec_id, up_data)
                                    st.rerun()
                                if c_del.button("この指摘を削除", key=f"ed_del_{rec_id}"): 
                                    db_delete_record(rec_id); st.rerun()
                                if new_photo: 
                                    st.markdown("<p style='font-size:12px; color:gray; margin-top:10px;'>▼ 差し替え用プレビュー (縮小表示)</p>", unsafe_allow_html=True)
                                    st.image(new_photo, width=250)
                                    
                            st.markdown('</div>', unsafe_allow_html=True)

            elif not st.session_state.issue_saved:
                prev_f = st.session_state.prev_floor; prev_a = st.session_state.prev_area
                if c_type.startswith("【検査機関】"):
                    f = "一式"; a = "全体"; sel_cat = None; sel_temp = None; default_w = ""
                    st.markdown("##### 詳細・場所の追記（自由入力）")
                    desc = st.text_area("詳細情報を入力", label_visibility="collapsed", placeholder="具体的な指摘内容や場所を入力してください")
                    st.markdown("##### 工種を選択")
                    work_opts = WORK_OPTS_KIKAN; w_idx = 0
                else:
                    f = "一式"; a = "全体"; default_w = ""
                    area_opts = AREA_OPTS_SHANAI if c_type in SHANAI_KENSA_TYPES else AREA_OPTS_STANDARD
                    work_opts = WORK_OPTS_SHANAI if c_type in SHANAI_KENSA_TYPES else WORK_OPTS_KUTAI if c_type == "躯体検査" else WORK_OPTS_HAIKIN if c_type == "配筋検査" else WORK_OPTS_CHUKAN if c_type == "中間検査" else WORK_OPTS_DANNETSU if c_type == "断熱検査" else WORK_OPTS_STANDARD
                    
                    if c_type not in ["配筋検査", "躯体検査", "断熱検査", "中間検査"]:
                        f_idx = FLOOR_OPTS[1:].index(prev_f) if prev_f in FLOOR_OPTS[1:] else 0
                        f = st.radio("階層を選択", FLOOR_OPTS[1:], index=f_idx, horizontal=True)
                        a_idx = area_opts[1:].index(prev_a) if prev_a in area_opts[1:] else 0
                        a = st.radio("部位を選択", area_opts[1:], index=a_idx, horizontal=True)
                    
                    cat_dict = ISSUE_TEMPLATES.get(c_type, {}) if c_type in ["配筋検査", "躯体検査", "断熱検査", "中間検査"] else ISSUE_TEMPLATES.get("社内検査(設計)", {}).get(a, {}) if c_type in SHANAI_KENSA_TYPES else {}
                    if not isinstance(cat_dict, dict): cat_dict = {}
                    cat_keys = list(cat_dict.keys())
                    sel_cat = st.radio("分類を選択", cat_keys, horizontal=True) if cat_keys else None
                    
                    if sel_cat:
                        detail_items = cat_dict.get(sel_cat, [])
                        if not isinstance(detail_items, list): detail_items = []
                        temp_list = detail_items + ["その他（フリー項目）"]
                        sel_temp = st.radio("よくある指摘事項", temp_list, horizontal=True)
                        default_w = ""
                    else: sel_temp = None
                        
                    st.markdown("##### 詳細・場所の追記（自由入力）")
                    desc = st.text_area("詳細情報を入力", label_visibility="collapsed")
                    
                    disp_w_opts = work_opts[1:]
                    if default_w in disp_w_opts: w_idx = disp_w_opts.index(default_w)
                    else: w_idx = 0
                
                disp_w_opts = work_opts if c_type.startswith("【検査機関】") else work_opts[1:]
                w = st.radio("工種を選択", disp_w_opts, index=w_idx, horizontal=True, key=f"w_new_{sel_cat}_{sel_temp}")
                
                if sel_temp == "その他（フリー項目）": final_desc = desc.strip()
                else: final_desc = (sel_temp + ("：" + desc.strip() if desc.strip() != "" else "")) if sel_temp else desc.strip()
                
                loc_parts = [str(f), str(a)]
                if not c_type.startswith("【検査機関】") and sel_cat: loc_parts.append(str(sel_cat))
                loc_str = " ".join(loc_parts).strip()
                disp_desc = final_desc[:80] + "..." if len(final_desc) > 80 else final_desc

                st.markdown("##### 現場写真の追加（黒板自動合成）")
                photo_input = _smart_camera(
                    propName=c_name, inspType=c_type, inspDate=datetime.date.today().strftime("%Y/%m/%d"), 
                    locationText=loc_str, issueDetail=disp_desc, mode="insp", key="insp_cam"
                )
                if photo_input: st.session_state.temp_photo = photo_input

                if st.button("この内容で一時保存（通信なし）", type="primary"):
                    active_photo = st.session_state.temp_photo
                    if w and final_desc != "" and active_photo is not None:
                        record_data = {
                            "temp_id": str(uuid.uuid4()),
                            "floor_level": f, "area": a, "work_type": w, "issue_detail": final_desc, 
                            "photo_b64": active_photo
                        }
                        st.session_state.pending_records.append(record_data)
                        st.session_state.issue_saved = True
                        st.session_state.temp_photo = None
                        st.session_state.prev_floor = f
                        st.session_state.prev_area = a
                        st.rerun()
                    else: st.error("工種・内容・写真はすべて必須です")
                
                if st.session_state.temp_photo:
                    st.markdown("<p style='font-size:12px; color:gray; margin-top:10px;'>▼ プレビュー (1/4縮小表示)</p>", unsafe_allow_html=True)
                    st.image(st.session_state.temp_photo, width=250)

            else:
                st.success("一時保存しました（まだサーバーには送信されていません）") 
                if st.button("続けて次を登録", use_container_width=True): st.session_state.issue_saved = False; st.session_state.temp_photo = None; st.rerun()
                if st.button("保存データを確認・修正", use_container_width=True): st.session_state.edit_saved_records = True; st.rerun()
                
                if st.button("内容を保存して検査を終了する（サーバーへ送信）", use_container_width=True): 
                    if not st.session_state.pending_records:
                        st.session_state.current_box = None; st.session_state.issue_saved = False; st.session_state.edit_saved_records = False; st.session_state.cached_records = None; st.session_state.temp_photo = None; st.session_state.prev_floor = None; st.session_state.prev_area = None; st.rerun()
                    else:
                        with st.spinner(f"全 {len(st.session_state.pending_records)} 件のデータを送信中...（このまま画面を閉じないでください）"):
                            err_count = 0
                            for rec in st.session_state.pending_records:
                                url = upload_to_storage(rec["photo_b64"])
                                if not url or url == rec["photo_b64"]:
                                    err_count += 1
                                    continue
                                
                                initial_status = "確認待ち" if c_inspector in ["工事監理チーム", "検査機関"] else "是正待ち"
                                db_rec = {
                                    "record_id": str(uuid.uuid4()), "inspection_id": c_id, "property_id": c_prop_id, 
                                    "floor_level": rec["floor_level"], "area": rec["area"], "work_type": rec["work_type"], 
                                    "issue_detail": rec["issue_detail"], "progress_status": initial_status, "line_notified": True,
                                    "issue_photo_url": url
                                }
                                res = requests.post(f"{SUPABASE_URL}/rest/v1/inspection_records", headers=HEADERS, json=db_rec)
                                if res.status_code not in [200, 201, 204]:
                                    err_count += 1
                            
                            if err_count == 0:
                                clear_specific_cache("inspection_records")
                                st.success("すべてのデータを正常に保存しました！")
                                st.session_state.pending_records = []
                                st.session_state.current_box = None
                                st.session_state.issue_saved = False
                                st.session_state.edit_saved_records = False
                                st.session_state.cached_records = None
                                st.session_state.temp_photo = None
                                st.session_state.prev_floor = None
                                st.session_state.prev_area = None
                                time.sleep(1.5)
                                st.rerun()
                            else:
                                st.error(f"一部のデータの送信に失敗しました（{err_count}件エラー）。電波の良い場所でもう一度「終了する」ボタンを押してください。")
# ----------------------------------------
    # メニュー: 3. 検査内容確認（管理者）
    # ----------------------------------------
    elif st.session_state.active_menu == "検査内容確認（管理者）":
        st.header("検査内容確認 ＆ 最終修正")
        sel_area = st.radio("表示エリアで絞り込み", ["すべて表示", "東海エリア", "関東エリア"], horizontal=True)
        search_query = st.text_input("物件名で検索（一部入力でも可）", key="search_conf")
        
        recs = db_get("inspection_records", "select=inspection_id,progress_status&progress_status=eq.確認待ち")
        ins = {i.get('inspection_id'): i for i in db_get("inspections", "select=*") if isinstance(i, dict)}
        props = {p.get('property_id'): p for p in db_get("properties", "select=*") if isinstance(p, dict)}
        
        tree = {}
        for r in recs:
            if not isinstance(r, dict): continue
            i = ins.get(r.get('inspection_id'))
            if i:
                pid = i.get('property_id')
                p = props.get(pid, {})
                if sel_area != "すべて表示" and p.get('area') != sel_area: continue
                
                pname = i.get('property_name', '不明')
                tname = i.get('inspection_type', '不明')
                if pname not in tree: tree[pname] = {"types": {}, "pid": pid}
                tree[pname]["types"][tname] = tree[pname]["types"].get(tname, 0) + 1
                
        if search_query: tree = {k: v for k, v in tree.items() if search_query in k}
        
        if not st.session_state.drill_target:
            for p_name, v in tree.items():
                p_hdate = props.get(v['pid'], {}).get('handover_date', '')
                h_disp = f" (引渡し: {p_hdate})" if p_hdate else " (引渡し未設定)"
                with st.expander(f"{p_name}{h_disp}"):
                    for t_name, cnt in v["types"].items():
                        if st.button(f"{t_name} ({cnt}件)", key=f"f_{p_name}_{t_name}"): 
                            st.session_state.drill_target = {"prop": p_name, "type": t_name}
                            st.rerun()
            if not tree: st.info("現在、確認待ちのデータはありません。")
        else:
            sel = st.session_state.drill_target
            prop_val = sel.get('prop'); type_val = sel.get('type')
            if st.button("⬅ 戻る"): st.session_state.drill_target = None; st.session_state.cached_records = None; st.rerun()
            
            t_ids = [str(i.get('inspection_id')) for i in ins.values() if i.get('property_name') == prop_val and i.get('inspection_type') == type_val]
            
            # 🌟 物件お引越し機能
            with st.expander("🔄 この検査の物件を変更する（間違えて登録した場合）"):
                p_opts = [p for p in props.values() if p.get('property_name') != prop_val]
                if p_opts:
                    new_p = st.selectbox("正しい移動先の物件を選択", p_opts, format_func=lambda x: f"[{x.get('area')}] {x.get('property_name')}")
                    if st.button("この物件にデータを移動する", type="primary"):
                        with st.spinner("移動中..."):
                            for iid in t_ids:
                                requests.patch(f"{SUPABASE_URL}/rest/v1/inspections?inspection_id=eq.{iid}", headers=HEADERS, json={"property_id": new_p['property_id'], "property_name": new_p['property_name']})
                                requests.patch(f"{SUPABASE_URL}/rest/v1/inspection_records?inspection_id=eq.{iid}", headers=HEADERS, json={"property_id": new_p['property_id']})
                            clear_specific_cache("inspections")
                            clear_specific_cache("inspection_records")
                        st.success("移動完了！")
                        st.session_state.drill_target = None
                        time.sleep(1)
                        st.rerun()

            if t_ids:
                recs_detail = sort_records(db_get("inspection_records", f"inspection_id=in.({','.join(t_ids)})&progress_status=eq.確認待ち"))
                if st.button("すべて承認して業者へ送る", type="primary"):
                    with st.spinner("承認処理中..."):
                        for r in recs_detail: 
                            requests.patch(f"{SUPABASE_URL}/rest/v1/inspection_records?record_id=eq.{r['record_id']}", headers=HEADERS, json={"progress_status": "是正待ち", "line_notified": True})
                        clear_specific_cache("inspection_records")
                    st.success("一括承認完了！")
                    st.session_state.drill_target = None
                    time.sleep(1)
                    st.rerun()
                    
                for r in recs_detail:
                    floor = r.get('floor_level', ''); area = r.get('area', ''); detail = r.get('issue_detail', '')
                    head_text = "" if type_val.startswith("【検査機関】") or floor == "一式" else f"【{floor} {area}】".strip()
                    title = f"{head_text} {detail}" if head_text else f"【指摘内容】 {detail}"
                    
                    with st.expander(title):
                        new_d = st.text_area("詳細内容を修正", value=detail, key=f"dd_{r['record_id']}")
                        c_ok, c_del = st.columns(2)
                        if c_ok.button("承認（個別に業者へ送る）", key=f"ok_{r['record_id']}"): 
                            db_patch("inspection_records", r['record_id'], {"progress_status": "是正待ち", "issue_detail": new_d})
                            st.rerun()
                        if c_del.button("削除（この指摘を無かったことにする）", key=f"del_{r['record_id']}"): 
                            db_delete_record(r['record_id'])
                            st.rerun()
                        if r.get('issue_photo_url'):
                            st.image(r['issue_photo_url'], width=300)

    # ----------------------------------------
    # メニュー: 4. 是正実施 / 是正ダッシュボード
    # ----------------------------------------
    elif st.session_state.active_menu in ["是正実施（協力業者）", "是正ダッシュボード（管理者用）"]:
        is_admin = (st.session_state.active_menu == "是正ダッシュボード（管理者用）")
        st.header("是正ダッシュボード（確認・実施）" if is_admin else "是正実施")
        
        if is_admin:
            sel_area = st.radio("表示エリア", ["すべて表示", "東海エリア", "関東エリア"], horizontal=True)
            t_area = sel_area if sel_area != "すべて表示" else None
        else:
            t_area = st.session_state.target_area
        
        status_filter = "in.(是正待ち,是正確認中)" if is_admin else "eq.是正待ち"
        recs = db_get("inspection_records", f"select=inspection_id,progress_status,record_id,area,floor_level,work_type,issue_detail&progress_status={status_filter}")
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
                h_disp = f" (引渡し: {p_hdate})" if p_hdate else " (引渡し未設定)"
                with st.expander(f"{p_name}{h_disp}"):
                    for t_name in sorted(list(v["types"])):
                        c = counts[p_name][t_name]
                        if not is_admin and c["wait_fix"] == 0: continue
                        
                        btn_txt = t_name
                        if is_admin: badge = f"是正写真待ち:{c['wait_fix']} / 管理者確認待ち:{c['wait_conf']}"
                        else: badge = f"全{c['total']}件 [未完了(写真待ち):{c['unres']}]"
                        
                        col1, col2 = st.columns([3, 7])
                        if col1.button(btn_txt, key=f"f_{p_name}_{t_name}", use_container_width=True): 
                            st.session_state.drill_target = {"prop": p_name, "type": t_name}
                            st.rerun()
                        col2.markdown(f"<div class='badge-wrap' style='margin-top:15px;'><span style='color:#E74C3C;'>{badge}</span></div>", unsafe_allow_html=True)
            if not tree: st.info("該当する項目はありません。")
        else:
            sel = st.session_state.drill_target
            prop_val = sel.get('prop'); type_val = sel.get('type')
            if st.button("⬅ 戻る"): st.session_state.drill_target = None; st.session_state.skip_render_ids = []; st.rerun()
            
            t_ids = [str(i.get('inspection_id')) for i in ins.values() if i.get('property_name') == prop_val and i.get('inspection_type') == type_val]
            
            if is_admin:
                with st.expander("🔄 この検査の物件を変更する（間違えて登録した場合）"):
                    p_opts = [p for p in props.values() if p.get('property_name') != prop_val]
                    if p_opts:
                        new_p = st.selectbox("正しい移動先の物件を選択", p_opts, format_func=lambda x: f"[{x.get('area')}] {x.get('property_name')}")
                        if st.button("この物件にデータを移動する", type="primary"):
                            with st.spinner("移動中..."):
                                for iid in t_ids:
                                    requests.patch(f"{SUPABASE_URL}/rest/v1/inspections?inspection_id=eq.{iid}", headers=HEADERS, json={"property_id": new_p['property_id'], "property_name": new_p['property_name']})
                                    requests.patch(f"{SUPABASE_URL}/rest/v1/inspection_records?inspection_id=eq.{iid}", headers=HEADERS, json={"property_id": new_p['property_id']})
                                clear_specific_cache("inspections")
                                clear_specific_cache("inspection_records")
                            st.success("移動完了！")
                            st.session_state.drill_target = None
                            time.sleep(1)
                            st.rerun()
            
            status_q = "in.(是正待ち,是正確認中)" if is_admin else "eq.是正待ち"
            recs_detail = sort_records(db_get("inspection_records", f"inspection_id=in.({','.join(t_ids)})&progress_status={status_q}"))
            
            issue_count = 1
            for r in recs_detail:
                rid = r['record_id']; stat = r['progress_status']
                if rid in st.session_state.skip_render_ids: continue
                
                # 管理者用 印刷ページ区切り
                if is_admin and (issue_count == 4 or (issue_count > 4 and (issue_count - 4) % 4 == 0)): 
                    st.markdown('<div class="page-break"></div>', unsafe_allow_html=True)
                
                floor = r.get('floor_level', ''); area = r.get('area', ''); detail = r.get('issue_detail', '')
                head_text = "" if type_val.startswith("【検査機関】") or floor == "一式" else f"【{floor} {area}】".strip()
                title = f"{head_text} {detail}" if head_text else f"【指摘内容】 {detail}"
                
                with st.container():
                    st.markdown(f'<div class="record-box {"report-item" if is_admin else ""}">', unsafe_allow_html=True)
                    st.markdown(f"**{title}** <span style='color:red;'>[{stat}]</span>", unsafe_allow_html=True)
                    
                    if is_admin and r.get('reject_reason'): st.error(f"否認理由: {r.get('reject_reason')}")
                    
                    c1, c2 = st.columns(2)
                    with c1:
                        st.markdown("**【Before】**")
                        if r.get('issue_photo_url'): st.markdown(f'<a href="{r["issue_photo_url"]}" target="_blank"><img src="{r["issue_photo_url"]}" class="report-img"></a>', unsafe_allow_html=True)
                        else: st.write("写真なし")
                    with c2:
                        if stat == "是正待ち":
                            st.markdown("**【After写真を撮影】**")
                            loc_str = f"{floor} {area}".strip()
                            disp_d = detail[:80] + "..." if len(detail)>80 else detail
                            up = _smart_camera(propName=prop_val, inspType=type_val, inspDate=datetime.date.today().strftime("%Y/%m/%d"), locationText=loc_str, issueDetail=disp_d, mode="fix", key=f"cam_{rid}")
                            
                            if st.button("完了報告として送信", key=f"s_{rid}", type="primary"):
                                if up: 
                                    with st.spinner("送信中..."):
                                        fix_url = upload_to_storage(up)
                                        db_patch("inspection_records", rid, {"progress_status": "是正確認中", "fix_photo_url": fix_url if fix_url else up, "line_notified": True})
                                        st.session_state.skip_render_ids.append(rid)
                                    st.rerun()
                                else: st.error("写真をセットしてください")
                        elif stat == "是正確認中" and is_admin:
                            st.markdown("**【After写真の確認】**")
                            if r.get('fix_photo_url'): st.markdown(f'<a href="{r["fix_photo_url"]}" target="_blank"><img src="{r["fix_photo_url"]}" class="report-img"></a>', unsafe_allow_html=True)
                            
                            ca, cb = st.columns(2)
                            if ca.button("承認（完了）", key=f"ok_{rid}", type="primary"):
                                db_patch("inspection_records", rid, {"progress_status": "完了", "approved_date": str(datetime.date.today())})
                                st.session_state.skip_render_ids.append(rid)
                                st.rerun()
                            
                            reason = cb.text_input("否認理由", key=f"re_{rid}", label_visibility="collapsed", placeholder="理由を入力")
                            if cb.button("否認（差戻し）", key=f"ng_{rid}"):
                                db_patch("inspection_records", rid, {"progress_status": "是正待ち", "reject_reason": reason, "line_notified": False})
                                st.session_state.skip_render_ids.append(rid)
                                st.rerun()
                    st.markdown('</div>', unsafe_allow_html=True)
                    issue_count += 1
            
            if is_admin and [r for r in recs_detail if r['progress_status'] == '是正確認中' and r['record_id'] not in st.session_state.skip_render_ids]:
                st.markdown("<br>", unsafe_allow_html=True)
                if st.button("写真提出済みの全項目を一括で承認する", type="primary", use_container_width=True):
                    with st.spinner("一括承認中..."):
                        for r in [r for r in recs_detail if r['progress_status'] == '是正確認中']:
                            requests.patch(f"{SUPABASE_URL}/rest/v1/inspection_records?record_id=eq.{r['record_id']}", headers=HEADERS, json={"progress_status": "完了", "approved_date": str(datetime.date.today())})
                        clear_specific_cache("inspection_records")
                    st.success("一括承認完了！")
                    st.session_state.drill_target = None
                    time.sleep(1)
                    st.rerun()

    # ----------------------------------------
    # メニュー: 5. 完了分一覧
    # ----------------------------------------
    elif st.session_state.active_menu == "完了分一覧（共通）":
        st.header("完了分一覧")
        
        if not st.session_state.drill_target:
            if st.session_state.role == "admin":
                sel_area = st.radio("表示エリア", ["すべて表示", "東海エリア", "関東エリア"], horizontal=True)
                t_area = sel_area if sel_area != "すべて表示" else None
            else: t_area = st.session_state.target_area
            
            search_query = st.text_input("物件名で検索（一部入力でも可）", key="search_done")
            
            recs = db_get("inspection_records", "select=inspection_id&progress_status=eq.完了")
            ins = {i.get('inspection_id'): i for i in db_get("inspections", "select=*") if isinstance(i, dict)}
            props = {p.get('property_id'): p for p in db_get("properties", "select=*") if isinstance(p, dict)}
            
            tree = {}
            for r in recs:
                i = ins.get(r.get('inspection_id'))
                if i:
                    pid = i.get('property_id'); p = props.get(pid, {})
                    if t_area and p.get('area') != t_area: continue
                    pname = i.get('property_name', '不明'); tname = i.get('inspection_type', '不明')
                    if pname not in tree: tree[pname] = {"types": {}, "pid": pid}
                    tree[pname]["types"][tname] = tree[pname]["types"].get(tname, 0) + 1
            
            if search_query: tree = {k: v for k, v in tree.items() if search_query in k}
            
            for p_name, v in tree.items():
                p_hdate = props.get(v['pid'], {}).get('handover_date', '')
                h_disp = f" (引渡し: {p_hdate})" if p_hdate else " (引渡し未設定)"
                with st.expander(f"{p_name}{h_disp}"):
                    for t_name, cnt in v["types"].items():
                        if st.button(f"{t_name} (完了: {cnt}件)", key=f"d_{p_name}_{t_name}"): 
                            st.session_state.drill_target = {"prop": p_name, "type": t_name}
                            st.rerun()
            if not tree: st.info("完了データはありません。")
        else:
            sel = st.session_state.drill_target
            prop_val = sel.get('prop'); type_val = sel.get('type')
            if st.button("⬅ 戻る"): st.session_state.drill_target = None; st.rerun()
            
            t_ids = [str(i.get('inspection_id')) for i in db_get("inspections", "select=*") if i.get('property_name') == prop_val and i.get('inspection_type') == type_val]
            
            # 🌟 管理者用 データの完全削除（5963バグ修正＆キャッシュ完全削除追加）
            if st.session_state.role == "admin":
                st.markdown(f"""
                <div class="admin-delete-box" style="background-color:#FFF0F0; padding:15px; border:2px solid #FF4B4B; border-radius:10px; margin-bottom:20px;">
                    <h3 style="color:#FF4B4B; margin-top:0;">完了物件の保存及び削除（管理者専用）</h3>
                    <p style="font-size:14px; color:#333;">PDF等の保存が完了しましたら、データを削除してください。<br><b>※一度削除した写真は元に戻せません。</b></p>
                </div>
                """, unsafe_allow_html=True)
                
                del_pass = st.text_input("削除用パスワードを入力 (5963)", type="password", placeholder="5963")
                if st.button(f"この検査データを完全に削除する", type="primary"):
                    if del_pass == DELETE_PASSWORD:
                        with st.spinner("削除処理中..."):
                            for iid in t_ids:
                                requests.delete(f"{SUPABASE_URL}/rest/v1/inspection_records?inspection_id=eq.{iid}", headers=HEADERS)
                                requests.delete(f"{SUPABASE_URL}/rest/v1/inspections?inspection_id=eq.{iid}", headers=HEADERS)
                            
                            # 【超重要】ここがないと亡霊データが残ります
                            clear_specific_cache("inspection_records")
                            clear_specific_cache("inspections")
                            
                        st.success("すべてのデータを完全に削除しました")
                        st.session_state.drill_target = None
                        time.sleep(1)
                        st.rerun()
                    else: st.error("パスワードが違います")
                st.markdown("<hr class='admin-delete-box'>", unsafe_allow_html=True)
                    
            recs_detail = sort_records(db_get("inspection_records", f"inspection_id=in.({','.join(t_ids)})&progress_status=eq.完了"))
            
            st.markdown(f"""
            <div style="background:white; padding:0; font-family:sans-serif; width:100%;">
                <div style="text-align:center; margin-bottom:5px; font-size:24px; font-weight:bold;">{prop_val}</div>
                <div style="text-align:center; margin-top:0; font-size:20px; font-weight:bold;">{type_val} 報告書</div>
                <div style="text-align:right; font-size:12px; color:#555; margin-bottom:10px; border-bottom:2px solid #000; padding-bottom:5px;">
                    <strong>完了:</strong> {len(recs_detail)}件
                </div>
            </div>
            """, unsafe_allow_html=True)
            
            issue_count = 1
            for r in recs_detail:
                if issue_count == 4 or (issue_count > 4 and (issue_count - 4) % 4 == 0):
                    st.markdown('<div class="page-break"></div>', unsafe_allow_html=True)
                
                floor = r.get('floor_level', ''); area = r.get('area', ''); detail = r.get('issue_detail', '')
                loc_text = "" if type_val.startswith("【検査機関】") or floor == "一式" else f"【{floor} {area}】"
                i_photo = r.get("issue_photo_url"); f_photo = r.get("fix_photo_url")
                app_date_str = f"<span style='background-color:#f1f3f4; padding:3px 8px; border-radius:4px;'>承認日: {r.get('approved_date', '')}</span>" if r.get('approved_date') else ""
                
                no_img = '<div style="text-align:center; padding:30px; color:#999; border:1px solid #eee;">写真なし</div>'
                img_b = f'<a href="{i_photo}" target="_blank"><img src="{i_photo}" class="report-img"></a>' if i_photo else no_img
                img_a = f'<a href="{f_photo}" target="_blank"><img src="{f_photo}" class="report-img"></a>' if f_photo else no_img
                
                st.markdown(f"""
                <div class="report-item" style="page-break-inside: avoid; border-bottom: 1px dashed #ccc; padding: 15px 0; margin-bottom: 10px;">
                    <div style="display: flex; justify-content: space-between;">
                        <div style="font-size:14px; font-weight:bold;">No.{issue_count} {loc_text}</div>
                        <div style="font-size:11px;">{app_date_str}</div>
                    </div>
                    <div style="font-size:14px; margin: 8px 0;"><strong>内容：</strong> {detail}</div>
                    <table style="width:100%; table-layout:fixed; border:none;">
                        <tr>
                            <td style="width:50%; text-align:center;"><div style="font-size:12px; margin-bottom:4px;">[ Before ]</div>{img_b}</td>
                            <td style="width:50%; text-align:center;"><div style="font-size:12px; margin-bottom:4px;">[ After ]</div>{img_a}</td>
                        </tr>
                    </table>
                </div>
                """, unsafe_allow_html=True)
                
                if st.session_state.role == "admin":
                    c_s, c_u = st.columns([8, 2])
                    if c_u.button("↩️ 完了取消", key=f"undo_{r['record_id']}"):
                        db_patch("inspection_records", r['record_id'], {"progress_status": "是正確認中", "approved_date": None})
                        st.success("完了を取り消し、ダッシュボードに戻しました")
                        time.sleep(1)
                        st.rerun()
                issue_count += 1

if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        st.error("システムエラーが発生しました。電波の良い場所でやり直してください。")
        if st.button("システム復旧"): 
            st.session_state.clear()
            st.rerun()
