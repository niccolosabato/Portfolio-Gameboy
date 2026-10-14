# Sabato Portfolio

Sito personale in stile Game Boy. I contenuti stanno dentro uno schermo LCD e
ci si naviga con i tasti della console — croce direzionale, A, B, Start e
Select — usabili con mouse, dito o tastiera.

La disposizione è verticale ed è la stessa su tutti gli schermi: pannello in
alto, croce e A/B sotto, Start e Select in fondo.

Cambia solo la cornice attorno. Su una finestra orizzontale la console ha una
sagoma con gli angoli del Game Boy, staccata dal fondo dall'ombra e da un bordo
chiaro — lo sfondo è lo stesso grigio della plastica, un tono più scuro. Su
telefono, o su una finestra verticale, la sagoma sparisce e la plastica riempie
lo schermo: lì non c'è spazio attorno a cui staccarsi, e un corpo delimitato
dentro uno schermo già stretto sembrerebbe un riquadro appiccicato. Rispetto alla console vera lo schermo è molto più grande in proporzione
al corpo — sull'originale occupa poco più di metà della larghezza, qui i tre
quarti — perché altrimenti sarebbe illeggibile su un monitor.

Live: <https://niccolosabato.github.io>

## Com'è fatto

HTML, CSS e JavaScript puri. Nessuna dipendenza, nessun passo di
compilazione, nessuna chiamata di rete: quello che si vede è tutto nel repo.

```
index.html
check.mjs           controlla che i testi stiano nello schermo
server.py            server di sviluppo locale
css/shell.css       plancia: plastica, comandi, disposizione
css/screen.css      pannello LCD e font
fonts/              Press Start 2P
js/main.js          avvio e interruttore
js/screen.js        disegno sul canvas: griglia, testo, a capo
js/input.js         tastiera, mouse e touch → comandi astratti
js/router.js        macchina a stati delle schermate
js/audio.js         bip generati con oscillatori, accesi di default
js/prefs.js         l'audio acceso o spento, in localStorage
js/screens/home.js  la home: l'elenco dei progetti
js/screens/         una schermata per file
data/projects.js    i progetti
data/contacts.js    i contatti
analisi/            le pagine di lettura delle analisi
genera_analisi.py   le rigenera dai Google Doc
```

### Le due tecniche di disegno

La plastica e i comandi sono **CSS**, quindi vettoriali: si ridimensionano con
la finestra e restano nitidi a qualunque scala. Niente immagini.

Lo schermo è un **canvas di 240x216 pixel veri**, ingrandito dal CSS con
`image-rendering: pixelated`. L'ingrandimento nearest-neighbour tiene i pixel
netti a qualunque fattore di scala, anche frazionario, come fa un emulatore.
Con un `<div>` scalato via `transform` il testo sarebbe risultato sfocato a
ogni scala non intera.

Quanto grande sia un pixel lo decide `--k`, e da lì deriva **tutto il resto**:
corpo, cornice, tasti, altoparlante, dimensioni dei caratteri. Si ridimensiona
la console intera cambiando quel solo numero.

```css
--k: min((100vw - 20px) / 334, (100dvh - 20px) / 504);
```

I due numeri sono le proporzioni del corpo: 334 di larghezza per 504 di
altezza, cioè la somma delle bande messe una sopra l'altra. Sono scritte per
esteso in cima a `css/shell.css`, così si vede da dove escono.

Su una finestra da 1440x900 lo schermo arriva a 419px, con il testo a 14px.

Come sull'originale la cornice è più larga a sinistra, perché lì stanno il LED
rosso e la scritta BATTERY. Su schermi stretti la scritta sparisce e la
striscia si assottiglia, altrimenti si mangerebbe un sesto della larghezza
dello schermo.

Il prezzo è che il testo del canvas non è selezionabile né leggibile dagli
screen reader. È una perdita accettata a monte: questo sito non insegue né i
motori di ricerca né i lettori di schermo.

### Lo spazio a disposizione

Lo schermo tiene **28 colonne per 20 righe**: celle da 8x8 pixel, righe
distanziate 10. Il Game Boy vero ha 160x144 pixel, cioè 20 colonne, dove la
sola parola "IndovinaQuando" ne occupa 14. Qui la risoluzione è una volta e
mezza, mantenendo la proporzione 10:9 originale: il guscio resta fedele, i
testi respirano.

## Comandi

| | Tastiera | Puntatore |
|---|---|---|
| Croce | frecce o WASD | i tasti sul guscio |
| A | Z, spazio, invio | " |
| B | X, Esc, backspace | " |
| Start | P | " |
| Select | Shift | " |

L'interruttore in alto a sinistra spegne e riaccende davvero: da spento lo
schermo si smorza, riaccendendolo riparte l'animazione di avvio.

## Sviluppo

```bash
python3 server.py        # http://localhost:8765
node check.mjs          # i testi stanno nello schermo?
```

Il doppio clic su `index.html` **non** funziona: gli ES modules non si caricano
da `file://`.

## Aggiungere un progetto

Si tocca solo `data/projects.js`. I limiti sono scritti in cima al file; per
verificarli basta `node check.mjs`, che li controlla tutti e dice cosa sfora.

I progetti rimandano a un URL pubblico, che sia un repo o un sito. Le analisi
invece hanno una pagina di lettura sul sito, sotto `analisi/`.

## Le pagine delle analisi

Le analisi si leggono su pagine del sito, fuori dal guscio Game Boy: foglio
bianco, testo nero, un solo foglio di stile per tutte (`analisi/analisi.css`).
Non si scrivono a mano, si generano dai Google Doc con

```bash
python3 genera_analisi.py
```

Lo script scarica i documenti, li converte con pandoc, copia le figure sotto
`analisi/<slug>/figures/` e riscrive le pagine. Quando un documento cambia si
rilancia lo script e si committano le pagine rigenerate. Serve pandoc nel PATH.

## Le schermate

La home **è** l'elenco dei contenuti, diviso in sezioni: `PROGETTI` e
`ANALISI`. Non c'è un menu prima. In fondo, staccate da un filetto, ci sono
`CONTATTI` e l'interruttore dell'audio. Da ogni voce si apre la sua scheda,
con descrizione, stack e i link da aprire: per le analisi il link è la pagina
di lettura sul sito.

L'audio è **acceso** di default: il primo suono arriva alla prima pressione,
che è anche il momento in cui il browser permette di riprodurlo.

All'avvio il logotipo scende come sulla console vera; si salta con un tasto e
non ricompare finché la scheda resta aperta.

## Pubblicazione

GitHub Pages come sito utente: il repo si chiama `niccolosabato.github.io` e il
sito esce sulla radice del dominio. Non serve nessuna configurazione oltre ad
attivare Pages sul branch principale. Il file `.nojekyll` serve a impedire che
Pages passi tutto per Jekyll.

## Nota sul marchio

La forma della console è un omaggio al Game Boy di Nintendo. Il logotipo sul
pannello è "sabato PORTFOLIO": nessun marchio altrui è riprodotto.
