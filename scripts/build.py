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
PER_SECTION = {"espana": 8, "politica": 8, "economia": 8, "international": 10, "moda": 5}
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
        desc = first(it, "description", "summary", "content")
        date_el = first(it, "pubDate", "published", "updated", "date")
        src = child(it, "source")
        enc = child(it, "enclosure")
        out.append({
            "title": title, "link": link,
            "summary": clean(desc.text if desc is not None else "", 360),
            "date": parse_date(date_el.text if date_el is not None else ""),
            "source": clean(src.text) if src is not None and src.text else "",
            "audio": enc.attrib.get("url", "") if enc is not None else "",
        })
    return out


def guess_region(text):
    low = text.lower()
    for reg, pat in REGIONS:
        if re.search(pat, low):
            return reg
    return "global"


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
                if not e["title"] or not e["link"]:
                    continue
                if e["date"] and (now - e["date"]).total_seconds() > MAX_AGE_H * 3600:
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
                    "words": norm_words(title),
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
        })

    def rank_key(s):
        return (s["score"], s["date"] or "")

    chosen = []
    for sec, n in PER_SECTION.items():
        pool = sorted([s for s in stories if s["sec"] == sec], key=rank_key, reverse=True)[:n]
        chosen.extend(pool)
    for i, s in enumerate(chosen):
        s["id"] = f"s{i+1}"

    top_pool = sorted(chosen, key=rank_key, reverse=True)
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

    if len(chosen) < 5:
        log("Muy pocas noticias; no se sobrescribe la edición.")
        sys.exit(1)

    head = next((s for s in chosen if s["id"] == top[0]["id"]), chosen[0])
    edition = {
        "date": madrid_today, "generated_at": now.isoformat(timespec="minutes"),
        "headline": head["title"], "headline_sec": head["sec"],
        "sources_ok": sum(1 for s in status if s["ok"]), "sources_total": len(status),
        "stories": chosen, "top": top, "podcasts": pods, "status": status,
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
