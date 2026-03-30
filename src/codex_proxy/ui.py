"""Embedded HTML/JS configuration UI served by the proxy server."""
import json
import logging
import os
from .config import Config, config as _config

logger = logging.getLogger(__name__)

_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>codex-proxy · Config</title>
<style>
  *, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }
  :root {
    --bg: #0f1117;
    --surface: #1a1d27;
    --border: #2e3148;
    --accent: #6c63ff;
    --accent-hover: #7d75ff;
    --text: #e2e4f0;
    --muted: #7b7f96;
    --success: #3ddc97;
    --warning: #f5a623;
    --error: #ff5c5c;
    --radius: 8px;
    --font: 'Inter', system-ui, -apple-system, sans-serif;
    --mono: 'JetBrains Mono', 'Fira Code', 'Cascadia Code', monospace;
  }
  body { background: var(--bg); color: var(--text); font-family: var(--font); font-size: 14px; min-height: 100vh; }
  header {
    display: flex; align-items: center; gap: 12px;
    padding: 16px 24px; border-bottom: 1px solid var(--border);
    background: var(--surface);
  }
  header h1 { font-size: 18px; font-weight: 600; letter-spacing: -0.3px; }
  header .badge {
    background: var(--accent); color: #fff; font-size: 10px;
    font-weight: 700; padding: 2px 7px; border-radius: 99px; letter-spacing: 0.5px;
  }
  .status-dot {
    width: 9px; height: 9px; border-radius: 50%;
    background: var(--success); box-shadow: 0 0 6px var(--success);
    margin-left: auto; flex-shrink: 0;
  }
  main { max-width: 780px; margin: 0 auto; padding: 32px 24px; }
  .toast {
    position: fixed; top: 20px; right: 20px; z-index: 999;
    padding: 10px 18px; border-radius: var(--radius); font-size: 13px; font-weight: 500;
    opacity: 0; transform: translateY(-8px); transition: all 0.25s ease;
    pointer-events: none;
  }
  .toast.show { opacity: 1; transform: translateY(0); }
  .toast.ok { background: var(--success); color: #0a1a12; }
  .toast.err { background: var(--error); color: #fff; }

  section { margin-bottom: 32px; }
  section > h2 {
    font-size: 11px; font-weight: 600; text-transform: uppercase;
    letter-spacing: 1.2px; color: var(--muted); margin-bottom: 14px;
  }
  .card {
    background: var(--surface); border: 1px solid var(--border);
    border-radius: var(--radius); overflow: hidden;
  }
  .field {
    display: grid; grid-template-columns: 200px 1fr;
    align-items: start; gap: 12px;
    padding: 13px 18px; border-bottom: 1px solid var(--border);
  }
  .field:last-child { border-bottom: none; }
  .field label { color: var(--muted); font-size: 13px; padding-top: 6px; font-weight: 500; }
  .field label small { display: block; font-size: 11px; color: #555870; margin-top: 2px; font-weight: 400; }
  .field input, .field select {
    width: 100%; background: var(--bg); border: 1px solid var(--border);
    color: var(--text); padding: 6px 10px; border-radius: 6px; font-size: 13px;
    font-family: var(--mono); outline: none; transition: border-color 0.15s;
  }
  .field input:focus, .field select:focus { border-color: var(--accent); }
  .field input[type="password"] { letter-spacing: 2px; }
  .field input[type="number"] { width: 120px; }
  .field input[type="checkbox"] { width: 18px; height: 18px; margin-top: 5px; cursor: pointer; accent-color: var(--accent); }
  .field .toggle-eye {
    position: relative; display: flex; gap: 6px;
  }
  .toggle-eye input { flex: 1; }
  .toggle-eye button {
    background: var(--bg); border: 1px solid var(--border); color: var(--muted);
    border-radius: 6px; padding: 0 10px; cursor: pointer; font-size: 12px;
    transition: border-color 0.15s;
  }
  .toggle-eye button:hover { border-color: var(--accent); color: var(--text); }
  .tag-input-wrap { display: flex; flex-wrap: wrap; gap: 6px; padding: 6px 10px;
    background: var(--bg); border: 1px solid var(--border); border-radius: 6px;
    cursor: text; min-height: 36px; align-items: center; }
  .tag-input-wrap:focus-within { border-color: var(--accent); }
  .tag {
    background: #252840; border: 1px solid #3a3d5c; color: var(--text);
    padding: 2px 8px; border-radius: 99px; font-size: 12px;
    display: flex; align-items: center; gap: 4px; font-family: var(--mono);
  }
  .tag button { background: none; border: none; color: var(--muted); cursor: pointer; font-size: 14px; line-height: 1; padding: 0 1px; }
  .tag button:hover { color: var(--error); }
  .tag-input-wrap input {
    background: none; border: none; color: var(--text); outline: none;
    font-family: var(--mono); font-size: 13px; min-width: 80px; flex: 1;
    padding: 0;
  }
  .actions { display: flex; gap: 12px; margin-top: 24px; justify-content: flex-end; }
  button.primary {
    background: var(--accent); color: #fff; border: none;
    padding: 9px 22px; border-radius: var(--radius); font-size: 14px; font-weight: 600;
    cursor: pointer; transition: background 0.15s;
  }
  button.primary:hover { background: var(--accent-hover); }
  button.secondary {
    background: transparent; color: var(--muted); border: 1px solid var(--border);
    padding: 9px 18px; border-radius: var(--radius); font-size: 14px;
    cursor: pointer; transition: border-color 0.15s, color 0.15s;
  }
  button.secondary:hover { border-color: var(--accent); color: var(--text); }
  .info { font-size: 12px; color: var(--muted); margin-top: 4px; }
  @media (max-width: 560px) {
    .field { grid-template-columns: 1fr; }
    .field label small { display: inline; margin-left: 6px; }
  }
</style>
</head>
<body>
<header>
  <h1>codex&#8209;proxy</h1>
  <span class="badge">CONFIG</span>
  <div class="status-dot" title="Server running"></div>
</header>
<main>
<div id="toast" class="toast"></div>
<form id="cfg" autocomplete="off">

  <section>
    <h2>Server</h2>
    <div class="card">
      <div class="field">
        <label>Port <small>CODEX_PROXY_PORT</small></label>
        <input type="number" id="port" name="port" min="1" max="65535">
      </div>
      <div class="field">
        <label>Log level <small>CODEX_PROXY_LOG_LEVEL</small></label>
        <select id="log_level" name="log_level">
          <option value="DEBUG">DEBUG</option>
          <option value="INFO">INFO</option>
          <option value="WARNING">WARNING</option>
          <option value="ERROR">ERROR</option>
        </select>
      </div>
      <div class="field">
        <label>Debug mode <small>CODEX_PROXY_DEBUG</small></label>
        <input type="checkbox" id="debug_mode" name="debug_mode">
      </div>
    </div>
  </section>

  <section>
    <h2>Authentication</h2>
    <div class="card">
      <div class="field">
        <label>Z.AI API key <small>CODEX_PROXY_ZAI_API_KEY</small></label>
        <div class="toggle-eye">
          <input type="password" id="z_ai_api_key" name="z_ai_api_key" placeholder="sk-…">
          <button type="button" onclick="togglePw('z_ai_api_key', this)">show</button>
        </div>
      </div>
      <div class="field">
        <label>Gemini API key <small>CODEX_PROXY_GEMINI_API_KEY</small></label>
        <div class="toggle-eye">
          <input type="password" id="gemini_api_key" name="gemini_api_key" placeholder="AIza…">
          <button type="button" onclick="togglePw('gemini_api_key', this)">show</button>
        </div>
      </div>
    </div>
  </section>

  <section>
    <h2>Models</h2>
    <div class="card">
      <div class="field">
        <label>Allowed models <small>comma-separated, empty&nbsp;= any</small></label>
        <div id="models-wrap" class="tag-input-wrap" onclick="document.getElementById('models-raw').focus()">
          <input id="models-raw" placeholder="add model…" autocomplete="off">
        </div>
      </div>
      <div class="field">
        <label>Compaction model</label>
        <input type="text" id="compaction_model" name="compaction_model" placeholder="e.g. glm-4.6">
      </div>
    </div>
  </section>

  <section>
    <h2>Timeouts</h2>
    <div class="card">
      <div class="field">
        <label>Connect timeout <small>seconds</small></label>
        <input type="number" id="request_timeout_connect" name="request_timeout_connect" min="1">
      </div>
      <div class="field">
        <label>Read timeout <small>seconds</small></label>
        <input type="number" id="request_timeout_read" name="request_timeout_read" min="1">
      </div>
    </div>
  </section>

  <section>
    <h2>Reasoning</h2>
    <div class="card">
      <div class="field">
        <label>Default effort</label>
        <select id="reasoning_effort" name="reasoning_effort">
          <option value="none">none</option>
          <option value="minimal">minimal</option>
          <option value="low">low</option>
          <option value="medium">medium</option>
          <option value="high">high</option>
          <option value="xhigh">xhigh</option>
        </select>
      </div>
    </div>
  </section>

  <div class="actions">
    <button type="button" class="secondary" onclick="load()">Reset</button>
    <button type="submit" class="primary">Save to disk</button>
  </div>
</form>
</main>
<script>
const FIELDS_TEXT = ['z_ai_api_key','gemini_api_key','compaction_model'];
const FIELDS_NUM  = ['port','request_timeout_connect','request_timeout_read'];
const FIELDS_SEL  = ['log_level','reasoning_effort'];
const FIELDS_BOOL = ['debug_mode'];
let modelTags = [];

function togglePw(id, btn) {
  const el = document.getElementById(id);
  const show = el.type === 'password';
  el.type = show ? 'text' : 'password';
  btn.textContent = show ? 'hide' : 'show';
}

function renderTags() {
  const wrap = document.getElementById('models-wrap');
  wrap.querySelectorAll('.tag').forEach(t => t.remove());
  modelTags.forEach((t, i) => {
    const span = document.createElement('span');
    span.className = 'tag';
    span.innerHTML = `${t}<button type="button" onclick="removeTag(${i})" title="remove">&times;</button>`;
    wrap.insertBefore(span, document.getElementById('models-raw'));
  });
}
function removeTag(i) { modelTags.splice(i, 1); renderTags(); }
document.getElementById('models-raw').addEventListener('keydown', e => {
  const v = e.target.value.trim();
  if ((e.key === 'Enter' || e.key === ',') && v) {
    e.preventDefault();
    if (!modelTags.includes(v)) { modelTags.push(v); renderTags(); }
    e.target.value = '';
  } else if (e.key === 'Backspace' && !e.target.value && modelTags.length) {
    modelTags.pop(); renderTags();
  }
});

function populate(data) {
  FIELDS_TEXT.forEach(k => { if (data[k] != null) document.getElementById(k).value = data[k]; });
  FIELDS_NUM.forEach(k  => { if (data[k] != null) document.getElementById(k).value = data[k]; });
  FIELDS_SEL.forEach(k  => { if (data[k] != null) document.getElementById(k).value = data[k]; });
  FIELDS_BOOL.forEach(k => { if (data[k] != null) document.getElementById(k).checked = !!data[k]; });
  modelTags = Array.isArray(data.models) ? [...data.models] : [];
  renderTags();
}

async function load() {
  try {
    const r = await fetch('/config');
    if (!r.ok) throw new Error(r.statusText);
    populate(await r.json());
  } catch(e) { toast('Failed to load config: ' + e.message, true); }
}

document.getElementById('cfg').addEventListener('submit', async e => {
  e.preventDefault();
  const body = {};
  FIELDS_TEXT.forEach(k => { body[k] = document.getElementById(k).value; });
  FIELDS_NUM.forEach(k  => { body[k] = parseInt(document.getElementById(k).value, 10); });
  FIELDS_SEL.forEach(k  => { body[k] = document.getElementById(k).value; });
  FIELDS_BOOL.forEach(k => { body[k] = document.getElementById(k).checked; });
  body.models = [...modelTags];
  try {
    const r = await fetch('/config', { method: 'POST', headers: {'Content-Type':'application/json'}, body: JSON.stringify(body) });
    const j = await r.json();
    if (!r.ok) throw new Error(j.error || r.statusText);
    toast('Saved ✓');
  } catch(e) { toast(e.message, true); }
});

function toast(msg, err=false) {
  const el = document.getElementById('toast');
  el.textContent = msg;
  el.className = 'toast show ' + (err ? 'err' : 'ok');
  setTimeout(() => { el.className = 'toast'; }, 3000);
}

load();
</script>
</body>
</html>
"""


def get_html() -> bytes:
    return _HTML.encode("utf-8")


def get_current_config() -> dict:
    """Return the current live config as a JSON-serialisable dict."""
    c = _config
    return {
        "port": c.port,
        "log_level": c.log_level,
        "debug_mode": c.debug_mode,
        "z_ai_api_key": c.z_ai_api_key,
        "gemini_api_key": c.gemini_api_key,
        "models": list(c.models),
        "compaction_model": c.compaction_model or "",
        "request_timeout_connect": c.request_timeout_connect,
        "request_timeout_read": c.request_timeout_read,
        "reasoning_effort": c.reasoning.get("default_effort", c.reasoning_effort),
    }


def apply_and_save(data: dict) -> dict:
    """Validate, apply to live config, and persist to config file."""
    c = _config

    if "port" in data:
        v = int(data["port"])
        if not (1 <= v <= 65535):
            raise ValueError(f"Port must be 1-65535, got {v}")
        c.port = v

    if "log_level" in data:
        lvl = str(data["log_level"]).upper()
        if lvl not in ("DEBUG", "INFO", "WARNING", "ERROR"):
            raise ValueError(f"Invalid log_level: {lvl}")
        c.log_level = lvl
        logging.getLogger().setLevel(lvl)

    if "debug_mode" in data:
        c.debug_mode = bool(data["debug_mode"])

    for key in ("z_ai_api_key", "gemini_api_key"):
        if key in data:
            setattr(c, key, str(data[key]))

    if "models" in data:
        c.models = [m for m in data["models"] if m]

    if "compaction_model" in data:
        c.compaction_model = str(data["compaction_model"]) or None

    if "request_timeout_connect" in data:
        c.request_timeout_connect = max(1, int(data["request_timeout_connect"]))

    if "request_timeout_read" in data:
        c.request_timeout_read = max(1, int(data["request_timeout_read"]))

    if "reasoning_effort" in data:
        effort = str(data["reasoning_effort"])
        valid = {"none", "minimal", "low", "medium", "high", "xhigh"}
        if effort not in valid:
            raise ValueError(f"reasoning_effort must be one of {valid}")
        c.reasoning_effort = effort
        c.reasoning["default_effort"] = effort

    # Persist to disk
    _save_config(c)
    return get_current_config()


def _save_config(c: Config):
    """Write current config to the config file (creates dirs if needed)."""
    os.makedirs(os.path.dirname(c.config_path), exist_ok=True)

    # Load existing file to preserve keys we don't manage
    existing: dict = {}
    if os.path.exists(c.config_path):
        try:
            with open(c.config_path, "r") as f:
                existing = json.load(f)
        except Exception:
            pass

    existing.update({
        "port": c.port,
        "log_level": c.log_level,
        "debug_mode": c.debug_mode,
        "z_ai_api_key": c.z_ai_api_key,
        "gemini_api_key": c.gemini_api_key,
        "models": list(c.models),
        "compaction_model": c.compaction_model or "",
        "request_timeout_connect": c.request_timeout_connect,
        "request_timeout_read": c.request_timeout_read,
        "reasoning_effort": c.reasoning_effort,
        "reasoning": c.reasoning,
    })

    with open(c.config_path, "w") as f:
        json.dump(existing, f, indent=2)
    logger.info(f"Config saved to {c.config_path}")
