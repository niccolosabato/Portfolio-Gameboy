#!/usr/bin/env python3
"""Genera le pagine di lettura delle analisi a partire dai Google Doc.

Per ogni analisi elencata in ANALISI lo script:
  1. scarica il documento come .docx dall'export pubblico di Google;
  2. lo converte in HTML con pandoc (le figure finiscono in una cartella
     temporanea);
  3. sistema il markup: via il titolo doppione in testa, figure e tabelle
     pronte per la lettura, indirizzi nudi trasformati in link;
  4. scrive `analisi/<slug>/index.html` e `analisi/<slug>/figures/`.

I Google Doc restano la fonte: quando un documento cambia si rilancia lo
script e si committano le pagine rigenerate. Il sito resta senza passi di
compilazione.

Uso:
    python3 genera_analisi.py                     # tutte le analisi
    python3 genera_analisi.py lavoro-giovanile    # solo una

Serve pandoc nel PATH; se non c'è, lo script prova da solo
`mise x pandoc@latest -- pandoc`.
"""

import html
import re
import shutil
import struct
import subprocess
import sys
import tempfile
import urllib.request
from html.parser import HTMLParser
from pathlib import Path

RADICE = Path(__file__).resolve().parent
USCITA = RADICE / "analisi"

# Un documento per analisi. `promuovi_bold` serve ai Doc in cui i titoli di
# sezione sono paragrafi tutti in grassetto invece che titoli veri.
ANALISI = [
    {
        "slug": "violenza-sessuale",
        "doc": "1CIKL1s-yVU6bndmdKX2jlnR_WC8mJ0xYIBAMISr8K58",
        "titolo": "Violenza sessuale in Italia",
        "promuovi_bold": True,
    },
    {
        "slug": "lavoro-giovanile",
        "doc": "1fVb0Rmpoc5o3gcO3UezIQMdw7TZoo4uDyZO_35PK8XU",
        "titolo": "Lavoro giovanile in Italia",
        "promuovi_bold": True,
    },
    {
        "slug": "suicidio-giovanile",
        "doc": "1iZlEsRHXOvukP7RPmO1Ghms4zSjpvocDg-r_iyCGREA",
        "titolo": "Salute mentale e suicidio tra i giovani",
        "promuovi_bold": False,
    },
]

VUOTI = {
    "area", "base", "br", "col", "embed", "hr", "img", "input",
    "link", "meta", "param", "source", "track", "wbr",
}
INTESTAZIONI = {"h1", "h2", "h3", "h4", "h5", "h6"}
INDIRIZZO = re.compile(r"https?://[^\s<>()\[\]]+")


# ---------------------------------------------------------------------------
# Un albero HTML minimo, quanto basta per leggere e riscrivere l'output di
# pandoc. I nodi di testo sono stringhe dentro `figli`.
# ---------------------------------------------------------------------------

class Nodo:
    def __init__(self, tag, attrs=None):
        self.tag = tag
        self.attrs = list(attrs or [])
        self.figli = []

    def testo(self):
        parti = []
        for f in self.figli:
            parti.append(f if isinstance(f, str) else f.testo())
        return "".join(parti)


class Albero(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.radice = Nodo("#radice")
        self.pila = [self.radice]

    def handle_starttag(self, tag, attrs):
        nodo = Nodo(tag, attrs)
        self.pila[-1].figli.append(nodo)
        if tag not in VUOTI:
            self.pila.append(nodo)

    def handle_endtag(self, tag):
        for i in range(len(self.pila) - 1, 0, -1):
            if self.pila[i].tag == tag:
                del self.pila[i:]
                return

    def handle_data(self, dati):
        self.pila[-1].figli.append(dati)


# ---------------------------------------------------------------------------
# Lavorazione del markup
# ---------------------------------------------------------------------------

def significativi(nodi):
    return [f for f in nodi if not (isinstance(f, str) and f.strip() == "")]


def contiene(nodo, tag):
    for f in nodo.figli:
        if isinstance(f, str):
            continue
        if f.tag == tag or contiene(f, tag):
            return True
    return False


def togli_titolo_di_testa(radice):
    """Il Doc si apre con il proprio titolo ("... a cura di ..."), che la
    pagina mette già nella testata: qui si toglie per non vederlo due volte."""
    for i, f in enumerate(radice.figli):
        if isinstance(f, str) and f.strip() == "":
            continue
        if isinstance(f, Nodo) and f.tag == "h1":
            del radice.figli[i]
        elif isinstance(f, Nodo) and f.tag == "p":
            dentro = significativi(f.figli)
            if (len(dentro) == 1 and not isinstance(dentro[0], str)
                    and dentro[0].tag == "strong"
                    and "a cura di" in dentro[0].testo().lower()):
                del radice.figli[i]
        return


def promuovi_paragrafi(radice):
    """Nei Doc dove i titoli di sezione sono paragrafi in grassetto, li
    riporta a veri <h2>. Solo fuori dai limiti di un titolo normale: un
    paragrafo lungo tutto in grassetto è enfasi, non una sezione."""
    for f in radice.figli:
        if not isinstance(f, Nodo) or f.tag != "p":
            continue
        dentro = significativi(f.figli)
        if (len(dentro) != 1 or isinstance(dentro[0], str)
                or dentro[0].tag != "strong"):
            continue
        testo = dentro[0].testo().strip()
        if not testo or len(testo) > 120:
            continue
        f.tag = "h2"
        f.figli = dentro[0].figli


def sgonfia(nodi, tag):
    """Toglie i nodi `tag` sostituendoli con i loro figli, a ogni livello."""
    fuori = []
    for f in nodi:
        if isinstance(f, Nodo) and f.tag in tag:
            fuori.extend(sgonfia(f.figli, tag))
        else:
            if isinstance(f, Nodo):
                f.figli = sgonfia(f.figli, tag)
            fuori.append(f)
    return fuori


def sistema_img(img, dimensioni):
    nome = Path(dict(img.attrs).get("src", "")).name
    nuovi = [("src", "figures/" + nome)]
    for chiave, valore in img.attrs:
        if chiave == "alt":
            nuovi.append(("alt", valore))
    misura = dimensioni.get(nome)
    if misura:
        nuovi.append(("width", str(misura[0])))
        nuovi.append(("height", str(misura[1])))
    nuovi.append(("loading", "lazy"))
    nuovi.append(("decoding", "async"))
    img.attrs = nuovi


def sistema_a(nodo, dimensioni):
    for f in nodo.figli:
        if isinstance(f, str):
            continue
        if f.tag == "img":
            sistema_img(f, dimensioni)
        elif f.tag in INTESTAZIONI:
            f.figli = sgonfia(f.figli, {"strong"})
        elif f.tag == "li":
            f.figli = sgonfia(f.figli, {"p"})
        sistema_a(f, dimensioni)


def sistema_b(nodi):
    """Filtra i blocchi inutili e prepara tabelle e immagini."""
    fuori = []
    for f in nodi:
        if isinstance(f, str):
            fuori.append(f)
            continue
        if f.tag in INTESTAZIONI and f.testo().strip() == "":
            continue
        if f.tag == "p" and f.testo().strip() == "" and not contiene(f, "img"):
            continue
        if f.tag == "table":
            f.figli = sistema_b(f.figli)
            riquadro = Nodo("div", [("class", "tabella")])
            riquadro.figli = [f]
            fuori.append(riquadro)
            continue
        f.figli = sistema_b(f.figli)
        fuori.append(f)
    return fuori


def collega_url(nodi):
    """Gli indirizzi scritti nudi nei Doc diventano link veri."""
    fuori = []
    for f in nodi:
        if isinstance(f, str):
            fuori.extend(link_nel_testo(f))
        else:
            if f.tag != "a":
                f.figli = collega_url(f.figli)
            fuori.append(f)
    return fuori


def link_nel_testo(testo):
    pezzi = []
    pos = 0
    for m in INDIRIZZO.finditer(testo):
        url = m.group(0).rstrip(".,;:")
        if m.start() > pos:
            pezzi.append(testo[pos:m.start()])
        a = Nodo("a", [("href", url)])
        a.figli = [url]
        pezzi.append(a)
        pos = m.end()
    if pos < len(testo):
        pezzi.append(testo[pos:])
    return pezzi


# ---------------------------------------------------------------------------
# Serializzazione e pagina
# ---------------------------------------------------------------------------

def serializza(nodo):
    if isinstance(nodo, str):
        return html.escape(nodo, quote=False)
    attr = "".join(
        ' %s="%s"' % (chiave, html.escape(str(valore), quote=True))
        for chiave, valore in nodo.attrs
    )
    if nodo.tag in VUOTI:
        return "<%s%s>" % (nodo.tag, attr)
    dentro = "".join(serializza(f) for f in nodo.figli)
    return "<%s%s>%s</%s>" % (nodo.tag, attr, dentro, nodo.tag)


def corpo_html(radice):
    blocchi = [f for f in radice.figli
               if not (isinstance(f, str) and f.strip() == "")]
    return "\n".join(serializza(f) for f in blocchi)


def pagina(titolo, corpo):
    return """<!DOCTYPE html>
<html lang="it">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>%s · Sabato Portfolio</title>
<link rel="stylesheet" href="/analisi/analisi.css">
</head>
<body>
<header>
  <nav class="barra"><a href="/">Sabato Portfolio</a></nav>
  <h1>%s</h1>
  <p class="autore">A cura di Sabato Niccolò</p>
</header>
<main>
%s
</main>
<footer><a href="/">Torna al portfolio</a></footer>
</body>
</html>
""" % (html.escape(titolo), html.escape(titolo), corpo)


# ---------------------------------------------------------------------------
# Scarico e conversione
# ---------------------------------------------------------------------------

def trova_pandoc():
    try:
        subprocess.run(["pandoc", "--version"],
                       capture_output=True, check=True)
        return ["pandoc"]
    except (OSError, subprocess.CalledProcessError):
        pass
    try:
        subprocess.run(["mise", "--version"],
                       capture_output=True, check=True)
    except (OSError, subprocess.CalledProcessError):
        raise SystemExit(
            "pandoc non trovato: installalo (oppure usa mise) e riprova."
        )
    return ["mise", "x", "pandoc@latest", "--", "pandoc"]


def scarica_docx(doc_id, destinazione):
    url = "https://docs.google.com/document/d/%s/export?format=docx" % doc_id
    richiesta = urllib.request.Request(
        url, headers={"User-Agent": "sabatoPortfolio-genera-analisi"}
    )
    with urllib.request.urlopen(richiesta, timeout=90) as risposta:
        dati = risposta.read()
    if not dati.startswith(b"PK"):
        raise SystemExit(
            "l'export di %s non è un .docx: il documento è pubblico?"
            % doc_id
        )
    destinazione.write_bytes(dati)


def converti(pandoc, docx, cartella):
    out = cartella / "doc.html"
    media = cartella / "media"
    subprocess.run(
        [*pandoc, str(docx), "-f", "docx", "-t", "html5", "--wrap=none",
         "--extract-media", str(media), "-o", str(out)],
        check=True, capture_output=True,
    )
    return out.read_text(encoding="utf-8"), media


def dimensione_png(percorso):
    with open(percorso, "rb") as f:
        testa = f.read(24)
    if len(testa) < 24 or not testa.startswith(b"\x89PNG\r\n\x1a\n"):
        return None
    larghezza, altezza = struct.unpack(">II", testa[16:24])
    return larghezza, altezza


def genera(analisi, pandoc):
    slug = analisi["slug"]
    print("%s:" % slug)

    with tempfile.TemporaryDirectory(prefix="analisi-") as tmp:
        tmp = Path(tmp)
        docx = tmp / "doc.docx"
        print("  scarico il documento (%s...)" % analisi["doc"][:8])
        scarica_docx(analisi["doc"], docx)

        print("  converto con pandoc")
        html_grezzo, media = converti(pandoc, docx, tmp)
        figure = sorted(
            p for p in media.rglob("*") if p.suffix.lower() == ".png"
        )
        dimensioni = {p.name: dimensione_png(p) for p in figure}
        # la cartella temporanea sparisce all'uscita dal blocco
        figure_bytes = {p.name: p.read_bytes() for p in figure}

        albero = Albero()
        albero.feed(html_grezzo)
        radice = albero.radice
        togli_titolo_di_testa(radice)
        if analisi.get("promuovi_bold"):
            promuovi_paragrafi(radice)
        sistema_a(radice, dimensioni)
        radice.figli = sistema_b(radice.figli)
        radice.figli = collega_url(radice.figli)
        corpo = corpo_html(radice)

    destinazione = USCITA / slug
    if destinazione.is_dir():
        shutil.rmtree(destinazione)
    elif destinazione.exists():
        destinazione.unlink()
    cartella_figure = destinazione / "figures"
    cartella_figure.mkdir(parents=True)
    for nome, dati in figure_bytes.items():
        (cartella_figure / nome).write_bytes(dati)
    (destinazione / "index.html").write_text(
        pagina(analisi["titolo"], corpo), encoding="utf-8"
    )
    print("  scritto %s/index.html con %d figure"
          % (destinazione.relative_to(RADICE), len(figure)))


def main():
    scelti = ANALISI
    if len(sys.argv) > 1:
        richiesti = set(sys.argv[1:])
        scelti = [a for a in ANALISI if a["slug"] in richiesti]
        ignoti = richiesti - {a["slug"] for a in ANALISI}
        if ignoti:
            raise SystemExit("analisi sconosciute: " + ", ".join(sorted(ignoti)))

    pandoc = trova_pandoc()
    for analisi in scelti:
        genera(analisi, pandoc)
    print("Fatto. Anteprima: python3 server.py, poi /analisi/<slug>/")


if __name__ == "__main__":
    main()