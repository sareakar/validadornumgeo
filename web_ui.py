"""
Web UI temporal para normalizar archivos CSV/Excel con números telefónicos.
Feature branch — la integración final va en AsterVoIP.

Rutas que agrega al servidor REST existente:
  GET  /           → HTML de la interfaz
  POST /ui/analyze → detecta columnas del archivo subido (JSON)
  POST /ui/process → procesa y devuelve CSV normalizado (descarga)
"""

import csv
import io
import json
import logging
import os
import re
import sys

logger = logging.getLogger("web_ui")

PHONE_KEYWORDS = {
    "tel", "phone", "cel", "fon", "numero", "nro", "num", "movil", "fijo",
    "whatsapp", "contacto", "telefono", "celular", "llamada", "mobile",
    "teléfono", "phone_number", "phonenumber", "numero_tel", "nro_tel",
}

# ── HTML ──────────────────────────────────────────────────────────────────────

HTML = """<!DOCTYPE html>
<html lang="es">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>ValidadorNumGeo</title>
  <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.3/dist/css/bootstrap.min.css" rel="stylesheet">
  <style>
    body { background: #f0f2f5; }
    .card { border: none; box-shadow: 0 1px 4px rgba(0,0,0,.09); border-radius: 10px; }
    .drop-zone {
      border: 2px dashed #ced4da;
      border-radius: 8px;
      padding: 38px 24px;
      text-align: center;
      cursor: pointer;
      transition: border-color .18s, background .18s;
      user-select: none;
    }
    .drop-zone:hover, .drop-zone.dragover { border-color: #0d6efd; background: #f0f4ff; }
    .drop-zone.has-file { border-color: #198754; border-style: solid; background: #f0faf4; }
    #config-panel, #result-panel { display: none; }
    .sample-badge { font-size: .74rem; font-weight: 400; }
  </style>
</head>
<body>
<div class="container py-5" style="max-width:680px">

  <div class="mb-4">
    <h5 class="mb-0 fw-bold">ValidadorNumGeo</h5>
    <p class="text-muted small mb-0">Normalización de teléfonos argentinos · ENACOM · 13 carriers</p>
  </div>

  <!-- 1 — Archivo -->
  <div class="card mb-3">
    <div class="card-body p-4">
      <p class="small text-muted mb-2 fw-semibold text-uppercase" style="letter-spacing:.05em">1 — Archivo</p>
      <div class="drop-zone" id="dz">
        <input type="file" id="fi" accept=".csv,.xlsx,.xls,.txt" class="d-none">
        <div id="st-idle">
          <div class="text-muted mb-1" style="font-size:2rem">&#128194;</div>
          <p class="mb-0 text-secondary">Arrastrá un archivo o <span class="text-primary">hacé clic</span></p>
          <small class="text-muted">CSV, Excel (.xlsx / .xls), TXT</small>
        </div>
        <div id="st-file" class="d-none">
          <span style="font-size:1.4rem">&#128196;</span>
          <span id="fn" class="fw-semibold ms-2"></span>
          <span class="text-muted ms-2 small" id="fs"></span>
          <button type="button" class="btn btn-sm btn-link text-danger p-0 ms-3" id="btn-clear">Quitar</button>
        </div>
      </div>
    </div>
  </div>

  <!-- 2 — Configuración -->
  <div class="card mb-3" id="config-panel">
    <div class="card-body p-4">
      <p class="small text-muted mb-3 fw-semibold text-uppercase" style="letter-spacing:.05em">2 — Configuración</p>
      <div class="row g-3 align-items-start">
        <div class="col-sm-7">
          <label class="form-label small">Columna con teléfonos <span class="text-danger">*</span></label>
          <select class="form-select form-select-sm" id="sel-col"></select>
          <div id="prev-box" class="mt-1 d-none">
            <small class="text-muted">Muestra: </small><span id="prev-vals"></span>
          </div>
        </div>
        <div class="col-sm-5">
          <label class="form-label small">Carrier / Proveedor</label>
          <select class="form-select form-select-sm" id="sel-prov">
            <option value="">— Todos los formatos —</option>
          </select>
          <div class="form-text">Define el formato de <code>tel_normalizado</code></div>
        </div>
        <div class="col-auto">
          <label class="form-label small">Área por defecto</label>
          <input type="text" class="form-control form-control-sm" id="inp-area" value="11" style="width:72px" maxlength="4">
          <div class="form-text">Para números sin código</div>
        </div>
        <div class="col-auto d-flex align-items-end" style="padding-bottom:.45rem">
          <div class="form-check mb-0">
            <input class="form-check-input" type="checkbox" id="chk-only">
            <label class="form-check-label small" for="chk-only">Solo válidos</label>
          </div>
        </div>
      </div>
      <div class="mt-4 d-flex align-items-center gap-3">
        <button class="btn btn-primary px-4" id="btn-proc">
          <span id="btn-lbl">Procesar y descargar</span>
          <span id="btn-spin" class="spinner-border spinner-border-sm ms-2 d-none"></span>
        </button>
        <small class="text-muted" id="lbl-rows"></small>
      </div>
    </div>
  </div>

  <!-- 3 — Resultado -->
  <div class="card" id="result-panel">
    <div class="card-body p-4" id="result-body"></div>
  </div>

</div>
<script>
const dz      = document.getElementById('dz');
const fi      = document.getElementById('fi');
const stIdle  = document.getElementById('st-idle');
const stFile  = document.getElementById('st-file');
const fnEl    = document.getElementById('fn');
const fsEl    = document.getElementById('fs');
const btnClr  = document.getElementById('btn-clear');
const cfgPan  = document.getElementById('config-panel');
const selCol  = document.getElementById('sel-col');
const selProv = document.getElementById('sel-prov');
const inpArea = document.getElementById('inp-area');
const chkOnly = document.getElementById('chk-only');
const btnProc = document.getElementById('btn-proc');
const btnLbl  = document.getElementById('btn-lbl');
const btnSpin = document.getElementById('btn-spin');
const lblRows = document.getElementById('lbl-rows');
const resPan  = document.getElementById('result-panel');
const resBody = document.getElementById('result-body');
const prevBox = document.getElementById('prev-box');
const prevVals= document.getElementById('prev-vals');

let file = null, samples = {};

fetch('/providers').then(r=>r.json()).then(d=>{
  Object.entries(d).forEach(([k,p])=>{
    const o = document.createElement('option');
    o.value = k; o.textContent = p.name;
    selProv.appendChild(o);
  });
}).catch(()=>{});

dz.addEventListener('click', ()=> fi.click());
dz.addEventListener('dragover', e=>{ e.preventDefault(); dz.classList.add('dragover'); });
dz.addEventListener('dragleave', ()=> dz.classList.remove('dragover'));
dz.addEventListener('drop', e=>{
  e.preventDefault(); dz.classList.remove('dragover');
  if (e.dataTransfer.files[0]) pick(e.dataTransfer.files[0]);
});
fi.addEventListener('change', ()=>{ if (fi.files[0]) pick(fi.files[0]); });
btnClr.addEventListener('click', e=>{ e.stopPropagation(); reset(); });

const sz = b => b < 1024 ? b+' B' : b < 1<<20 ? (b/1024).toFixed(1)+' KB' : (b/1<<20).toFixed(1)+' MB';
const esc = s => String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');

function pick(f) {
  file = f;
  dz.classList.add('has-file');
  stIdle.classList.add('d-none'); stFile.classList.remove('d-none');
  fnEl.textContent = f.name; fsEl.textContent = sz(f.size);
  resPan.style.display = 'none';
  analyze(f);
}

function reset() {
  file = null; fi.value = '';
  dz.classList.remove('has-file');
  stIdle.classList.remove('d-none'); stFile.classList.add('d-none');
  cfgPan.style.display = 'none'; resPan.style.display = 'none';
  selCol.innerHTML = '';
}

async function analyze(f) {
  const fd = new FormData(); fd.append('file', f);
  try {
    const r = await fetch('/ui/analyze', { method: 'POST', body: fd });
    const d = await r.json();
    if (!r.ok) { showErr(d.error || 'Error al analizar el archivo'); return; }
    samples = d.column_samples || {};
    selCol.innerHTML = '';
    d.columns.forEach(c => {
      const o = document.createElement('option');
      o.value = c; o.textContent = c;
      selCol.appendChild(o);
    });
    if (d.detected_column) selCol.value = d.detected_column;
    lblRows.textContent = d.total_rows.toLocaleString() + ' filas';
    updatePreview();
    selCol.addEventListener('change', updatePreview);
    cfgPan.style.display = 'block';
  } catch(e) { showErr('Error: ' + e.message); }
}

function updatePreview() {
  const s = (samples[selCol.value] || []).slice(0, 5);
  if (s.length) {
    prevVals.innerHTML = s.map(v =>
      `<span class="badge bg-secondary sample-badge me-1">${esc(v)}</span>`
    ).join('');
    prevBox.classList.remove('d-none');
  } else { prevBox.classList.add('d-none'); }
}

btnProc.addEventListener('click', async () => {
  if (!file) return;
  resPan.style.display = 'none';
  btnLbl.textContent = 'Procesando...';
  btnSpin.classList.remove('d-none');
  btnProc.disabled = true;

  const fd = new FormData();
  fd.append('file', file);
  fd.append('column', selCol.value);
  fd.append('provider', selProv.value);
  fd.append('default_area', inpArea.value || '11');
  fd.append('only_valid', chkOnly.checked ? '1' : '0');

  try {
    const r = await fetch('/ui/process', { method: 'POST', body: fd });
    const total   = r.headers.get('X-Total')   || '?';
    const valid   = r.headers.get('X-Valid')   || '?';
    const invalid = r.headers.get('X-Invalid') || '?';
    const cd      = r.headers.get('Content-Disposition') || '';

    if (!r.ok) {
      const e = await r.json().catch(() => ({}));
      showErr(e.error || 'Error procesando el archivo');
      return;
    }

    const blob = await r.blob();
    const m = cd.match(/filename="([^"]+)"/);
    const fname = m ? m[1] : 'resultado.csv';
    const a = document.createElement('a');
    a.href = URL.createObjectURL(blob); a.download = fname; a.click();
    URL.revokeObjectURL(a.href);

    showOk(`
      <div class="d-flex align-items-center gap-4 flex-wrap">
        <div>
          <div class="fw-semibold text-success mb-0">&#10003; Descarga lista</div>
          <small class="text-muted">${esc(fname)}</small>
        </div>
        <div class="vr d-none d-sm-block" style="height:36px"></div>
        <div class="d-flex gap-4">
          <div class="text-center"><div class="fs-5 fw-bold">${esc(total)}</div><small class="text-muted">total</small></div>
          <div class="text-center"><div class="fs-5 fw-bold text-success">${esc(valid)}</div><small class="text-muted">válidos</small></div>
          <div class="text-center"><div class="fs-5 fw-bold text-danger">${esc(invalid)}</div><small class="text-muted">inválidos</small></div>
        </div>
      </div>
    `);
  } catch(e) { showErr('Error: ' + e.message); }
  finally {
    btnLbl.textContent = 'Procesar y descargar';
    btnSpin.classList.add('d-none');
    btnProc.disabled = false;
  }
});

function showErr(msg) {
  resBody.innerHTML = `<div class="text-danger"><strong>Error:</strong> ${esc(msg)}</div>`;
  resPan.style.display = 'block';
}
function showOk(html) {
  resBody.innerHTML = html;
  resPan.style.display = 'block';
}
</script>
</body>
</html>"""


# ── helpers ───────────────────────────────────────────────────────────────────

def _parse_multipart(handler):
    """
    Parsea multipart/form-data sin módulo cgi (eliminado en Python 3.13).
    Devuelve dict: {name: {"value": bytes, "filename": str|None}}
    """
    ctype  = handler.headers.get("Content-Type", "")
    length = int(handler.headers.get("Content-Length", 0))
    body   = handler.rfile.read(length)

    boundary = None
    for seg in ctype.split(";"):
        seg = seg.strip()
        if seg.lower().startswith("boundary="):
            boundary = seg[9:].strip('"')
            break
    if not boundary:
        return {}

    delim = b"\r\n--" + boundary.encode()
    prefix = b"--" + boundary.encode()

    start = body.find(prefix)
    if start == -1:
        return {}
    body = body[start + len(prefix):]

    result = {}
    for part in body.split(delim):
        if part.startswith(b"--"):
            break
        if part.startswith(b"\r\n"):
            part = part[2:]
        if b"\r\n\r\n" not in part:
            continue
        header_bytes, content = part.split(b"\r\n\r\n", 1)
        if content.endswith(b"\r\n"):
            content = content[:-2]

        headers = {}
        for line in header_bytes.decode("utf-8", errors="replace").split("\r\n"):
            if ":" in line:
                k, v = line.split(":", 1)
                headers[k.strip().lower()] = v.strip()

        cd = headers.get("content-disposition", "")
        name = filename = None
        for seg in cd.split(";"):
            seg = seg.strip()
            if seg.lower().startswith("name="):
                name = seg[5:].strip('"')
            elif seg.lower().startswith("filename="):
                filename = seg[9:].strip('"')

        if name:
            result[name] = {"value": content, "filename": filename}

    return result


def _read_file(content: bytes, filename: str) -> tuple[list[str], list[dict]]:
    """
    Lee CSV/TXT con stdlib puro o Excel con openpyxl.
    Devuelve (columns, rows) donde rows es lista de dicts {col: str}.
    """
    name = (filename or "").lower()

    if name.endswith((".xlsx", ".xls")):
        try:
            import openpyxl
        except ImportError:
            raise ValueError(
                "openpyxl no está instalado. Instalalo con: pip install openpyxl  "
                "— o guardá el archivo como CSV desde Excel (Archivo → Guardar como → CSV)."
            )
        wb = openpyxl.load_workbook(io.BytesIO(content), read_only=True, data_only=True)
        ws = wb.active
        row_iter = ws.iter_rows(values_only=True)
        raw_headers = next(row_iter, [])
        columns = [str(h) if h is not None else f"col_{i}" for i, h in enumerate(raw_headers)]
        rows = []
        for raw in row_iter:
            rows.append({col: (str(v) if v is not None else "") for col, v in zip(columns, raw)})
        wb.close()
        return columns, rows

    # CSV / TXT
    last_exc = None
    for enc in ("utf-8-sig", "utf-8", "latin-1", "iso-8859-1"):
        try:
            text = content.decode(enc)
            # Auto-detectar delimitador (coma, punto y coma, tab, pipe)
            try:
                dialect = csv.Sniffer().sniff(text[:4096], delimiters=",;\t|")
            except csv.Error:
                dialect = csv.excel  # fallback: coma
            reader = csv.DictReader(io.StringIO(text), dialect=dialect)
            rows = list(reader)
            columns = list(reader.fieldnames or [])
            if not columns:
                raise ValueError("No se encontraron columnas")
            rows = [{k: (v or "") for k, v in r.items()} for r in rows]
            return columns, rows
        except Exception as e:
            last_exc = e
            continue

    raise ValueError(f"No se pudo leer el archivo: {last_exc}")


def _looks_phone(v: str) -> bool:
    clean = re.sub(r"[\s\-\(\)\+\.]", "", v)
    return bool(re.match(r"^\d{7,15}$", clean))


def _detect_phone_col(columns: list[str], rows: list[dict]) -> str | None:
    scores = {}
    for col in columns:
        score = 0
        if any(kw in col.lower() for kw in PHONE_KEYWORDS):
            score += 10
        sample = [str(r.get(col, "") or "") for r in rows[:10]]
        score += sum(1 for v in sample if v.strip() and _looks_phone(v))
        scores[col] = score
    if not scores:
        return None
    best = max(scores, key=scores.get)
    return best if scores[best] > 0 else (columns[0] if columns else None)


def _send_json(handler, data, status=200):
    body = json.dumps(data, ensure_ascii=False).encode("utf-8")
    handler.send_response(status)
    handler.send_header("Content-Type", "application/json; charset=utf-8")
    handler.send_header("Content-Length", str(len(body)))
    handler.send_header("Access-Control-Allow-Origin", "*")
    handler.end_headers()
    handler.wfile.write(body)


def _send_error(handler, msg, status=400):
    _send_json(handler, {"error": msg}, status)


# ── handlers ──────────────────────────────────────────────────────────────────

def handle_index(handler):
    body = HTML.encode("utf-8")
    handler.send_response(200)
    handler.send_header("Content-Type", "text/html; charset=utf-8")
    handler.send_header("Content-Length", str(len(body)))
    handler.end_headers()
    handler.wfile.write(body)


def handle_analyze(handler):
    try:
        form = _parse_multipart(handler)
        if "file" not in form:
            return _send_error(handler, "No se recibió ningún archivo")
        item = form["file"]
        columns, rows = _read_file(item["value"], item["filename"] or "")

        detected = _detect_phone_col(columns, rows)

        column_samples = {}
        for col in columns:
            vals = [str(r.get(col, "") or "") for r in rows]
            vals = [v for v in vals if v.strip()][:5]
            column_samples[col] = vals

        _send_json(handler, {
            "columns": columns,
            "detected_column": detected,
            "total_rows": len(rows),
            "column_samples": column_samples,
        })
    except Exception as e:
        logger.exception("Error en /ui/analyze")
        _send_error(handler, str(e))


def handle_process(handler):
    try:
        from validator import validate_bulk
        from providers import format_for_provider

        form = _parse_multipart(handler)
        if "file" not in form:
            return _send_error(handler, "No se recibió ningún archivo")

        def _fval(key, default=""):
            return form.get(key, {}).get("value", default.encode()).decode("utf-8")

        item     = form["file"]
        column   = _fval("column")
        provider = _fval("provider") or None
        area     = _fval("default_area", "11") or "11"
        only_v   = _fval("only_valid", "0") == "1"

        columns, rows = _read_file(item["value"], item["filename"] or "")

        if column not in columns:
            return _send_error(handler, f"Columna '{column}' no encontrada en el archivo")

        numbers = [str(r.get(column, "") or "") for r in rows]
        results = validate_bulk(numbers, default_area=area)

        total     = len(results)
        valid_n   = sum(1 for r in results if r.valid)
        invalid_n = total - valid_n

        out_rows = []
        for row_dict, r in zip(rows, results):
            if only_v and not r.valid:
                continue
            out = {k: str(v) for k, v in row_dict.items()}
            if r.valid:
                out["tel_normalizado"] = (
                    format_for_provider(r.formats, r.line_type, provider)
                    if provider
                    else r.formats.get("fmt_10dig", "")
                ) or ""
                out["tel_valido"]     = "SI"
                out["tel_tipo"]       = r.line_type or ""
                out["tel_modalidad"]  = r.modalidad or ""
                out["tel_operador"]   = r.operador or ""
                out["tel_localidad"]  = r.province or ""
                out["tel_area"]       = r.area_code or ""
                out["tel_10dig"]      = r.formats.get("fmt_10dig", "")
                out["tel_con0"]       = r.formats.get("fmt_con_0", "")
                out["tel_con015"]     = r.formats.get("fmt_con_0_15", "")
                out["tel_e164"]       = r.formats.get("fmt_e164", "")
                out["tel_e164_movil"] = r.formats.get("fmt_e164_movil", "")
                out["tel_error"]      = ""
            else:
                for k in ("tel_normalizado", "tel_tipo", "tel_modalidad", "tel_operador",
                          "tel_localidad", "tel_area", "tel_10dig", "tel_con0", "tel_con015",
                          "tel_e164", "tel_e164_movil"):
                    out[k] = ""
                out["tel_valido"] = "NO"
                out["tel_error"]  = r.error or ""
            out_rows.append(out)

        fieldnames = list(columns) + [
            "tel_normalizado", "tel_valido", "tel_tipo", "tel_modalidad",
            "tel_operador", "tel_localidad", "tel_area", "tel_10dig", "tel_con0", "tel_con015",
            "tel_e164", "tel_e164_movil", "tel_error",
        ]

        buf = io.StringIO()
        writer = csv.DictWriter(buf, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(out_rows)
        body = buf.getvalue().encode("utf-8-sig")  # BOM para compatibilidad Excel

        base = os.path.splitext(item["filename"] or "archivo")[0]
        out_fname = f"{base}_normalizado.csv"

        handler.send_response(200)
        handler.send_header("Content-Type", "text/csv; charset=utf-8")
        handler.send_header("Content-Disposition", f'attachment; filename="{out_fname}"')
        handler.send_header("Content-Length", str(len(body)))
        handler.send_header("Access-Control-Allow-Origin", "*")
        handler.send_header("Access-Control-Expose-Headers",
                            "X-Total, X-Valid, X-Invalid, Content-Disposition")
        handler.send_header("X-Total",   str(total))
        handler.send_header("X-Valid",   str(valid_n))
        handler.send_header("X-Invalid", str(invalid_n))
        handler.end_headers()
        handler.wfile.write(body)

    except Exception as e:
        logger.exception("Error en /ui/process")
        _send_error(handler, str(e))
