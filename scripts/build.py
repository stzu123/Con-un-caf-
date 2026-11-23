#!/usr/bin/env python3
"""Con un Café: monta la edición del día a partir de RSS. Sin IA y sin claves.

Lee feeds.json, descarga los titulares, agrupa las noticias que cuentan lo mismo,
las ordena por importancia (cuántas fuentes distintas las cuentan) y escribe:
  data/AAAA-MM-DD.json  (la edición)
  data/index.json       (lista de ediciones para el calendario)
Solo usa la biblioteca estándar de Python.
"""
import json, re, sys, html, unicodedata, datetime, urllib.request
from pathlib import Path
from email.utils import parsedate_to_datetime
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
UA = "Mozilla/5.0 (compatible; ConUnCafe/1.0; +https://github.com)"
MAX_AGE_H = 36            # solo noticias de las últimas 36 horas
PER_SECTION = {"espana": 10, "politica": 10, "economia": 10, "international": 12, "moda": 6}
TOP_N = 8                 # piezas del collage «Lectura en 30 segundos»

POLITICA = re.compile(r"\b(gobierno|psoe|pp|vox|sumar|podemos|junts|erc|pnv|bildu|congreso|senado|elecci|electoral|campa[nñ]a|"
                      r"s[aá]nchez|feij[oó]o|abascal|d[ií]az|ministr|moncloa|parlament|diputad|ley|decreto|debate|votaci|encuesta|cis)\w*", re.I)
REGIONS = [
    ("europe", r"europ|ukrain|russia|france|german|ital|spain|poland|brussels|nato|uk\b|britain|london|paris|berlin|türki|turkey"),
    ("us", r"\bus\b|u\.s\.|united states|america(?!n latin)|trump|washington|congress|senate|white house|new york|california|canada"),
    ("asia", r"china|japan|korea|india|pakistan|taiwan|asia|indonesia|philippin|vietnam|thailand|australia|beijing"),
    ("latam", r"mexic|brazil|argentin|venezuel|colombi|chile|peru|cuba|latin america|bolivi|ecuador"),
    ("mea", r"israel|gaza|iran|iraq|syria|leban|yemen|saudi|egypt|africa|nigeria|sudan|kenya|ethiopi|middle east|qatar|houthi|hormuz"),
]
# Titulares de relleno que no son noticia
BLOCK = re.compile(r"(loter[ií]a|bonoloto|primitiva|euromillones|el gordo|once\b.*sorteo|sorteo|hor[oó]scopo|tiempo (hoy|mañana)|"
                   r"previsi[oó]n del tiempo|precio de la (luz|gasolina)|gasolina (hoy|más barata)|resultados? del? (partido)|"
                   r"ibex(\s*35)? (abre|cierra|sube|baja|cae|avanza|retrocede|arranca|termina)|bolsa española (abre|cierra|sube|baja)|"
                   r"wall street (abre|cierra)|el euro (sube|baja) frente|cotizaci[oó]n (del|de la) (euro|d[oó]lar|bitcoin) hoy|"
                   r"en directo|última hora|minuto a minuto|crucigrama|sudoku|quiz|wordle|ofertas?|descuentos?|black friday|cupones?)", re.I)
# Sucesos (accidentes, crímenes, incendios locales…) que no aportan, salvo que tengan peso político o geopolítico
SUCESOS = re.compile(r"(muere|muertos?|fallec|heridos?|herida|killed|\bdead\b|\bdies\b|died|injur|accidente|atropell|incendio|fire at|\bblaze\b|crash|choque|colisi|apu[ñn]al|asesin|homicid|cad[aá]ver|detenid|arrest|tiroteo|shoot|stabb|\brob(o|os)\b|atraco|\bramas?\b|derrumb|ahog|drown|desaparec|missing|sucesos?|polic[ií]a local|guardia civil (busca|localiza)|reyerta|okup)", re.I)
PESO = re.compile(r"(guerra|\bwar\b|gaza|ucrania|ukrain|rusia|russia|dron|drone|attack|ataque|ofensiva|militar|military|army|ej[eé]rcito|gobierno|government|ministr|presiden|elecci|election|parlament|congreso|ley\b|\blaw\b|terror|dana|clima|climate|protest|manifest|huelga|strike|sanci[oó]n|sanction|s[aá]nchez|feij[oó]o|abascal|psoe|\bpp\b|\bvox\b|sumar|trump|putin|alcald|mayor\b|ministro|minister)", re.I)
# Titulares gancho tipo «el aparato que…»
CLICKBAIT = re.compile(r"(el aparato|el truco|trucos? para|el producto|chollo|as[ií] (puedes|podr[aá]s)|sin poner la calefacci|lo que (nadie|no) te|no te (lo )?vas a creer|te sorprender)", re.I)
def no_aporta(title, sec):
    if sec != "moda" and CLICKBAIT.search(title): return True
    return bool(SUCESOS.search(title)) and not PESO.search(title)

ECON_SUB = [
    ("bolsillo", r"vivienda|alquiler|hipoteca|eur[ií]bor|sueldo|salari|empleo|paro|trabaj|beca|pensi[oó]n|precio|s[uú]per|cesta|luz|gasolina|"
                 r"impuesto|irpf|consum|ahorro|jov[eé]n|universit|housing|rent|mortgage|wage|salary|jobs?\b|workers?|prices|grocer|tax"),
    ("empresas", r"empresa|startup|tecnolog|\bia\b|inteligencia artificial|apple|google|meta|amazon|microsoft|nvidia|openai|anthropic|tesla|"
                 r"spotify|netflix|inditex|zara|mercadona|telef[oó]nica|santander|bbva|iberdrola|repsol|cripto|bitcoin|beneficio|ventas|"
                 r"despid|ere\b|fusi[oó]n|compra|adquisi|company|startup|tech|\bai\b|chip|profit|sales|layoff|merger|deal|ceo"),
]
STOP = set("""a al algo ante con contra de del desde el ella ellos en entre era es esta este esto ha han hay la las le les lo los mas me mi muy
na ni no nos o para pero por que se sin sobre su sus te tras un una uno y ya the of to in and for on with at by from as is are was were be
has have after over into new says said its it his her their this that will than more about amid""".split())


def log(*a):
    print(*a, file=sys.stderr)


def fetch(url):
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "application/rss+xml, application/xml, text/xml, */*"})
    with urllib.request.urlopen(req, timeout=25) as r:
        return r.read()


def clean(text, limit=None):
    text = html.unescape(re.sub(r"<[^>]+>", " ", text or ""))
    text = re.sub(r"\s+", " ", text).strip()
    if limit and len(text) > limit:
        text = text[:limit].rsplit(" ", 1)[0].rstrip(",.;:") + "…"
    return text


def norm_words(title):
    t = unicodedata.normalize("NFKD", title.lower())
    t = "".join(c for c in t if not unicodedata.combining(c))
    words = re.findall(r"[a-z0-9]+", t)
    return {w for w in words if len(w) > 2 and w not in STOP}


def tag(el):
    return el.tag.split("}")[-1]


def child(el, name):
    for c in el:
        if tag(c) == name:
            return c
    return None


def parse_date(text):
    if not text:
        return None
    try:
        d = parsedate_to_datetime(text)
    except Exception:
        try:
            d = datetime.datetime.fromisoformat(text.replace("Z", "+00:00"))
        except Exception:
            return None
    if d.tzinfo is None:
        d = d.replace(tzinfo=datetime.timezone.utc)
    return d


def first(el, *names):
    for n in names:
        c = child(el, n)
        if c is not None:
            return c
    return None


def parse_feed(raw):
    """Devuelve una lista de dicts con title, link, summary, date, source (RSS 2.0 y Atom)."""
    root = ET.fromstring(raw)
    items = [e for e in root.iter() if tag(e) in ("item", "entry")]
    out = []
    for it in items:
        t = child(it, "title")
        title = clean(t.text if t is not None else "")
        link_el = child(it, "link")
        link = ""
        if link_el is not None:
            link = (link_el.text or "").strip() or link_el.attrib.get("href", "")
        desc = next((c for c in it if tag(c) in ("description", "summary", "encoded", "content") and (c.text or "").strip()), None)
        date_el = first(it, "pubDate", "published", "updated", "date")
        src = child(it, "source")
        enc = child(it, "enclosure")
        image = ""
        for c in it.iter():
            tg, url = tag(c), c.attrib.get("url", "")
            if url and (tg == "thumbnail" or (tg == "content" and c.attrib.get("medium", "image") == "image" and not url.endswith((".mp3", ".mp4")))
                        or (tg == "enclosure" and c.attrib.get("type", "").startswith("image"))):
                image = url
                break
        if not image and desc is not None:
            m = re.search(r'<img[^>]+src="([^"]+)"', desc.text or "")
            if m:
                image = html.unescape(m.group(1))
        out.append({
            "title": title, "link": link,
            "summary": clean(desc.text if desc is not None else "", 360),
            "date": parse_date(date_el.text if date_el is not None else ""),
            "source": clean(src.text) if src is not None and src.text else "",
            "audio": enc.attrib.get("url", "") if enc is not None and enc.attrib.get("type", "").startswith("audio") else "",
            "image": image if image.startswith("https://") else "",
        })
    return out


def guess_region(text):
    low = text.lower()
    for reg, pat in REGIONS:
        if re.search(pat, low):
            return reg
    return "global"


AI_PROMPT = """Eres la redactora de «Con un Café», la prensa matinal de una universitaria española de 21 años.
Ya sabe lo básico (qué es la inflación, el BCE, el Congreso...), así que NO definas conceptos básicos.
Para cada noticia te doy el titular y lo que dicen las fuentes. Escribe en español (aunque la noticia esté en inglés):
- "esencial": 1-2 frases claras con qué ha pasado (se lee debajo del titular en la portada).
- "porque": 1-2 frases: por qué importa hoy y a quién afecta.
- "desarrollo": 120-180 palabras: la noticia contada entera y ordenada (qué, quién, cuándo, dónde, qué dice cada fuente
  y en qué coinciden o discrepan).
- "cafe": 120-170 palabras, cercano y con chispa, sin paternalismo: contexto, causas, consecuencias, quién gana y quién pierde,
  y cómo conecta con otras noticias de la lista o con su vida (alquiler, primer empleo, ahorro, viajes, tecnología).
REGLAS: usa SOLO la información que te doy y conocimiento general estable; NO inventes cifras, fechas, nombres ni declaraciones.
Si un dato no está en el texto, no lo pongas. No copies frases de las fuentes: redacta con tus palabras.
Responde SOLO con JSON válido, sin texto antes ni después:
{"id": {"esencial": "...", "porque": "...", "desarrollo": "...", "cafe": "..."}, ...}"""


def call_ai(messages):
    """Gemini (nivel gratuito) si existe GEMINI_API_KEY, con reintentos; si falla, GitHub Models con el token de Actions."""
    import os, time
    attempts = []
    if os.environ.get("GEMINI_API_KEY"):
        for model in os.environ.get("GEMINI_MODEL", "gemini-4-hydrogen,gemini-flash-latest,gemini-flash-lite-latest").split(","):
            attempts.append(("https://generativelanguage.googleapis.com/v1beta/openai/chat/completions", os.environ["GEMINI_API_KEY"], model.strip()))
    if os.environ.get("GITHUB_TOKEN"):
        attempts.append(("https://models.github.ai/inference/chat/completions", os.environ["GITHUB_TOKEN"],
                         os.environ.get("GH_MODEL", "openai/gpt-4.1-mini")))
    for url, key, model in attempts:
        for wait in (0, 15, 40):          # servicio saturado (503) o límite por minuto (429): esperar y repetir
            if wait:
                time.sleep(wait)
            raw = ""
            try:
                body = {"model": model, "messages": messages, "temperature": 0.4}
                if "googleapis" in url:
                    body["response_format"] = {"type": "json_object"}
                req = urllib.request.Request(url, data=json.dumps(body).encode(),
                                             headers={"Authorization": "Bearer " + key, "Content-Type": "application/json", "User-Agent": UA})
                with urllib.request.urlopen(req, timeout=180) as r:
                    raw = r.read().decode("utf-8", "replace")
                txt = json.loads(raw)["choices"][0]["message"]["content"]
                txt = re.sub(r"^```(json)?|```$", "", txt.strip()).strip()
                m = re.search(r"\{.*\}", txt, re.S)
                return json.loads(m.group(0)), url.split("/")[2] + " · " + model
            except urllib.error.HTTPError as ex:
                log("IA", model, "HTTP", ex.code, ex.read()[:160])
                if ex.code not in (429, 500, 503):
                    break
            except Exception as ex:
                log("IA", model, type(ex).__name__, str(ex)[:120], "| respuesta:", raw[:160])
                break
    return None, None


def explain(chosen, top):
    """Añade «esencial», «porque», «desarrollo» y «cafe» a las noticias principales (en dos tandas de 5).
    Si la IA falla, la edición sale igual."""
    ids = [t["id"] for t in top]
    extra = [s["id"] for s in sorted(chosen, key=lambda s: s["score"], reverse=True) if s["id"] not in ids]
    ids = (ids + extra)[:10]
    pick = [s for s in chosen if s["id"] in ids]
    n = 0
    for k in range(0, len(pick), 5):
        batch = pick[k:k + 5]
        lines = []
        for s in batch:
            others = "; ".join(f'{o["source"]}: {o["title"]}' for o in s["others"][:4])
            lines.append(f'id={s["id"]} | sección={s["sec"]} | {s["source"]}: {s["title"]} | resumen: {s["summary"] or "-"} | otras fuentes: {others or "-"}')
        res, engine = call_ai([{"role": "system", "content": AI_PROMPT}, {"role": "user", "content": "\n".join(lines)}])
        if not res:
            continue
        for s in batch:
            r = res.get(s["id"]) or {}
            if isinstance(r, dict) and r.get("cafe"):
                s["ai"] = {f: clean(str(r.get(f, "")), 2000) for f in ("esencial", "porque", "desarrollo", "cafe")}
                n += 1
        chosen_engine[0] = engine
    log(f"Explicaciones IA: {n} noticias ({chosen_engine[0]})")


chosen_engine = [None]


def main():
    cfg = json.loads((ROOT / "feeds.json").read_text(encoding="utf-8"))
    now = datetime.datetime.now(datetime.timezone.utc)
    madrid_today = (now + datetime.timedelta(hours=1)).date().isoformat()
    items, status = [], []

    for f in cfg["news"]:
        try:
            entries = parse_feed(fetch(f["url"]))
            n = 0
            for e in entries[:40]:
                if not e["title"] or not e["link"] or BLOCK.search(e["title"]):
                    continue
                if e["date"] and (now - e["date"]).total_seconds() > MAX_AGE_H * 3600:
                    continue
                if no_aporta(e["title"], f["sec"]):
                    continue
                source = f["name"]
                title = e["title"]
                if f.get("aggregator"):
                    # Google Noticias: «Titular - Medio»
                    if e["source"]:
                        source = e["source"]
                    m = re.match(r"^(.*)\s+-\s+([^-]{2,60})$", title)
                    if m:
                        title, source = m.group(1).strip(), e["source"] or m.group(2).strip()
                    e["summary"] = ""   # su descripción es una lista de enlaces, no un resumen
                sec = f["sec"]
                if sec == "espana" and POLITICA.search(title):
                    sec = "politica"
                items.append({
                    "title": title, "link": e["link"], "summary": e["summary"], "source": source,
                    "date": e["date"].isoformat() if e["date"] else None, "sec": sec, "lang": f["lang"],
                    "region": f.get("region") or (guess_region(title + " " + e["summary"]) if sec == "international" else None),
                    "words": norm_words(title), "image": e.get("image", ""),
                })
                n += 1
            status.append({"name": f["name"], "ok": True, "items": n})
        except Exception as ex:
            status.append({"name": f["name"], "ok": False, "error": type(ex).__name__})
            log("FALLA", f["name"], ex)

    # Agrupar noticias que cuentan lo mismo (titulares muy parecidos dentro de la misma sección)
    clusters = []
    for it in items:
        best, best_sim = None, 0.0
        for c in clusters:
            if c["sec"] != it["sec"] and {c["sec"], it["sec"]} != {"espana", "politica"}:
                continue
            a, b = c["words"], it["words"]
            if not a or not b:
                continue
            sim = len(a & b) / min(len(a), len(b))
            if sim > best_sim:
                best, best_sim = c, sim
        if best is not None and best_sim >= 0.5:
            best["items"].append(it)
            best["words"] |= it["words"]
        else:
            clusters.append({"sec": it["sec"], "words": set(it["words"]), "items": [it]})

    stories = []
    for c in clusters:
        srcs = []
        for it in c["items"]:
            if it["source"] not in [s["source"] for s in srcs]:
                srcs.append(it)
        # titular principal: el de la fuente directa con resumen (si hay), si no el primero
        main_it = next((s for s in srcs if s["summary"]), srcs[0])
        newest = max((s["date"] for s in srcs if s["date"]), default=None)
        stories.append({
            "sec": "politica" if any(i["sec"] == "politica" for i in c["items"]) else main_it["sec"],
            "lang": main_it["lang"], "region": main_it["region"],
            "title": main_it["title"], "summary": main_it["summary"], "link": main_it["link"],
            "source": main_it["source"], "date": newest,
            "others": [{"source": s["source"], "title": s["title"], "link": s["link"]} for s in srcs if s is not main_it][:6],
            "score": len(srcs),
            "image": next((s["image"] for s in srcs if s.get("image")), ""),
        })
        if stories[-1]["sec"] == "economia":
            low = (stories[-1]["title"] + " " + stories[-1]["summary"]).lower()
            stories[-1]["sub"] = next((k for k, pat in ECON_SUB if re.search(pat, low)), "mundo")

    def rank_key(s):
        # los sucesos con peso político o geopolítico van los últimos
        return (0 if SUCESOS.search(s["title"]) else 1, s["score"], s["date"] or "")

    chosen = []
    for sec, n in PER_SECTION.items():
        pool = sorted([s for s in stories if s["sec"] == sec], key=rank_key, reverse=True)[:n]
        chosen.extend(pool)
    for i, s in enumerate(chosen):
        s["id"] = f"s{i+1}"

    top_pool = sorted([c for c in chosen if not SUCESOS.search(c["title"])] or chosen, key=rank_key, reverse=True)
    top, seen_secs = [], {}
    for s in top_pool:
        if len(top) >= TOP_N:
            break
        if seen_secs.get(s["sec"], 0) >= 3:      # que no lo acapare una sola sección
            continue
        seen_secs[s["sec"]] = seen_secs.get(s["sec"], 0) + 1
        top.append(s["id"])
    sizes = ["xl", "m", "m"] + ["s"] * (len(top) - 3)
    top = [{"id": i, "size": sizes[k]} for k, i in enumerate(top)]

    pods = []
    for p in cfg.get("podcasts", []):
        entry = {"sec": p["sec"], "show": p["show"],
                 "spotify": "https://open.spotify.com/search/" + urllib.request.quote(p.get("search") or p["show"])}
        if p.get("url"):
            try:
                eps = parse_feed(fetch(p["url"]))
                if eps:
                    e = eps[0]
                    entry.update({"episode": e["title"], "link": e["link"], "audio": e["audio"],
                                  "date": e["date"].isoformat() if e["date"] else None})
                status.append({"name": "Podcast · " + p["show"], "ok": True, "items": len(eps)})
            except Exception as ex:
                status.append({"name": "Podcast · " + p["show"], "ok": False, "error": type(ex).__name__})
        pods.append(entry)

    explain(chosen, top)

    if len(chosen) < 5:
        log("Muy pocas noticias; no se sobrescribe la edición.")
        sys.exit(1)

    head = next((s for s in chosen if s["id"] == top[0]["id"]), chosen[0])
    edition = {
        "date": madrid_today, "generated_at": now.isoformat(timespec="minutes"),
        "headline": head["title"], "headline_sec": head["sec"],
        "sources_ok": sum(1 for s in status if s["ok"]), "sources_total": len(status),
        "stories": chosen, "top": top, "podcasts": pods, "status": status, "ai_engine": chosen_engine[0],
    }
    DATA.mkdir(exist_ok=True)
    (DATA / f"{madrid_today}.json").write_text(json.dumps(edition, ensure_ascii=False, indent=1), encoding="utf-8")

    idx_path = DATA / "index.json"
    idx = json.loads(idx_path.read_text(encoding="utf-8")) if idx_path.exists() else {"editions": []}
    eds = [e for e in idx["editions"] if e["date"] != madrid_today]
    eds.insert(0, {"date": madrid_today, "headline": head["title"], "sec": head["sec"]})
    eds.sort(key=lambda e: e["date"], reverse=True)
    idx["editions"] = eds[:120]
    idx_path.write_text(json.dumps(idx, ensure_ascii=False, indent=1), encoding="utf-8")
    log(f"Edición {madrid_today}: {len(chosen)} noticias, {edition['sources_ok']}/{edition['sources_total']} fuentes OK")


if __name__ == "__main__":
    main()
