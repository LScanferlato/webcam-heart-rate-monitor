# Monitoraggio non invasivo della frequenza cardiaca mediante fotopletismografia ottica da webcam

## Sommario

Il presente elaborato descrive un sistema software per la stima in tempo reale della
frequenza cardiaca (Heart Rate, HR) mediante tecniche di fotopletismografia (PPG) da
webcam. L'implementazione si basa sull'algoritmo di magnificazione del colore (Eulerian
Video Magnification, EVM) sviluppato presso il MIT Computer Science & Artificial
Intelligence Laboratory (CSAIL). Il sistema acquisisce un flusso video dalla webcam,
applica una decomposizione piramidale gaussiana, esegue un filtraggio passa-banda nel
dominio delle frequenze per isolare la componente pulsatile del segnale
pletiSmografico, e ne amplifica l'ampiezza per consentire la visualizzazione
dell'onda di pressione sanguigna a livello cutaneo.

**Riferimento bibliografico:** Wu, H.-Y., Rubinstein, M., Shih, E., Guttag, J.,
Durand, F., & Freeman, W. T. (2012). _Eulerian Video Magnification for Revealing
Subtle Changes in the World._ ACM Transactions on Graphics, 31(4).
[http://people.csail.mit.edu/mrub/papers/vidmag.pdf](http://people.csail.mit.edu/mrub/papers/vidmag.pdf)

---

## 1. Introduzione

La fotopletismografia (PPG) è una tecnica ottica non invasiva che rileva le
variazioni volumetriche del flusso sanguigno nel microcircolo cutaneo. Ogni
contrazione cardiaca genera un'onda di pressione che si propaga attraverso il sistema
circolatorio, determinando una variazione temporanea del volume sanguigno nei tessuti.
Questa variazione modifica le proprietà di assorbimento e riflessione della luce sulla
superficie cutanea. L'algoritmo EVM consente di amplificare tali variazioni
cromatiche, generalmente impercettibili all'occhio umano, rendendo possibile la
stima della frequenza cardiaca mediante l'analisi del segnale video acquisito da una
webcam consumer.

### 1.1 Obiettivi

- Implementare un sistema di monitoraggio cardiovascolare in tempo reale
- Applicare tecniche di elaborazione numerica dei segnali per l'estrazione della
  componente frequenziale cardiaca
- Fornire una rappresentazione visuale dell'onda pulsatile mediante magnificazione
  cromatica
- Garantire l'acquisizione e la persistenza su supporto di memorizzazione del flusso
  video originale e di quello elaborato

---

## 2. Architettura del sistema

Il sistema è strutturato secondo un'architettura modulare che separa le
responsabilità di configurazione, elaborazione del segnale e interfaccia utente.

### 2.1 Moduli software

| Modulo               | Responsabilità funzionale                                          |
|----------------------|--------------------------------------------------------------------|
| `config.py`          | Parametri di configurazione del sistema                           |
| `signal_processor.py`| Trasformazioni nel dominio spaziale e frequenziale del segnale    |
| `main.py`            | Orchestrazione del flusso di acquisizione e visualizzazione (CLI) |
| `web_server.py`      | Server web Flask con API REST per elaborazione via browser        |
| `templates/index.html`| Interfaccia utente web con accesso webcam lato client            |

### 2.2 Diagramma di flusso

```
Acquisizione fotogramma → Estrazione area di rilevamento →
Piramide gaussiana → FFT → Filtro passa-banda (1.0–2.0 Hz) →
IFFT → Amplificazione → Ricostruzione piramide → Overlay sul fotogramma
```

---

## 3. Metodologia

### 3.1 Decomposizione piramidale gaussiana

Il fotogramma acquisito viene sottoposto a una decomposizione piramidale gaussiana
con `L` livelli, ottenuta mediante applicazione ricorsiva del filtro `pyrDown` di
OpenCV. Il livello più alto della piramide (`L`) viene selezionato per l'elaborazione
frequenziale. La ricostruzione avviene mediante applicazione ricorsiva del filtro
`pyrUp`.

### 3.2 Analisi frequenziale

Per ciascun canale cromatico, il segnale temporale estratto dal livello piramidale
viene trasformato nel dominio delle frequenze mediante Trasformata Rapida di Fourier
(FFT) lungo l'asse temporale del buffer circolare di dimensione `N = 150`
fotogrammi. Si applica quindi un filtro passa-banda che seleziona la banda
frequenziale corrispondente al range fisiologico cardiaco:

- **Frequenza minima:** 1.0 Hz (60 BPM)
- **Frequenza massima:** 2.0 Hz (120 BPM)

### 3.3 Stima della frequenza cardiaca

A intervalli regolari (`Δ = 15` fotogrammi), la FFT media sull'intero buffer viene
calcolata e la frequenza dominante viene estratta mediante massimizzazione
dell'ampiezza spettrale. La frequenza cardiaca istantanea è espressa in battiti per
minuto (BPM) come:

```
BPM = f_dominante × 60
```

Il valore visualizzato è la media mobile su un buffer circolare di `K = 10`
campioni, garantendo una stima robusta agli artefatti motori.

### 3.4 Magnificazione cromatica

Il segnale filtrato nel dominio delle frequenze viene antitrasformato e amplificato
di un fattore `α = 170`. Il segnale amplificato viene quindi sommato al fotogramma
originale dell'area di rilevamento, producendo l'effetto visivo di magnificazione
della componente pulsatile.

---

## 4. Requisiti di sistema

### 4.1 Hardware

- Webcam integrata o esterna con risoluzione minima 320×240 pixel
- Processore con architettura x86-64 o ARM64

### 4.2 Software

- Python ≥ 3.8
- numpy ≥ 1.21.0
- opencv-python ≥ 4.5.5
- Flask ≥ 2.2.0 (solo per la modalità web)

### 4.3 Installazione delle dipendenze

```bash
pip install -r requirements.txt
```

---

## 5. Modalità operative

Il sistema supporta due modalità operative: una modalità nativa tramite interfaccia
a riga di comando (CLI) con finestra OpenCV, e una modalità web che consente
l'elaborazione direttamente dal browser.

### 5.1 Modalità CLI — Acquisizione da webcam

```bash
python main.py
```

Avvia l'acquisizione dalla webcam predefinita (device index 0) e apre una finestra
di visualizzazione OpenCV. La fase di inizializzazione richiede approssimativamente
10 secondi per il riempimento del buffer circolare. Durante l'esecuzione vengono
generati due file video nella directory di lavoro corrente:

| File                    | Descrizione                                      |
|-------------------------|--------------------------------------------------|
| `video_originale.mp4`   | Flusso video originale senza elaborazione        |
| `video_elaborato.mp4`   | Flusso video con magnificazione cromatica e BPM  |

### 5.2 Modalità CLI — Analisi di un file video pre-acquisito

```bash
python main.py <percorso_video>
```

Il file video deve presentare risoluzione 320×240 pixel e frequenza di
acquisizione di 15 fotogrammi al secondo.

### 5.3 Modalità CLI — Terminazione

Premere il tasto `q` per terminare l'esecuzione e rilasciare le risorse allocate.

### 5.4 Modalità web — Server

```bash
python web_server.py
```

Avvia un server HTTP sulla porta 5000 dell'interfaccia di loopback
(`http://127.0.0.1:5000`). Il server espone i seguenti endpoint:

| Endpoint           | Metodo | Descrizione                                          |
|--------------------|--------|------------------------------------------------------|
| `/`                | GET    | Serve la pagina web `index.html`                     |
| `/api/elabora`     | POST   | Riceve un fotogramma JPEG (base64) e restituisce BPM e ROI elaborata |

L'elaborazione avviene lato server mediante la classe `ElaboratoreBattito`
(in `web_server.py`), che mantiene lo stato del buffer circolare tra richieste
HTTP successive. La comunicazione avviene in formato JSON:

**Richiesta:**
```json
{ "immagine": "<dati_jpeg_codificati_in_base64>" }
```

**Risposta:**
```json
{
  "bpm": 72.5,
  "roi": "<roi_elaborata_in_base64>",
  "pronto": true
}
```

### 5.5 Modalità web — Client

Aprire il browser all'indirizzo `http://127.0.0.1:5000`. Il client:

1. Richiede l'accesso alla webcam tramite l'API `navigator.mediaDevices.getUserMedia()`
2. Acquisisce i fotogrammi alla risoluzione di 320×240 pixel a circa 15 fps
3. Trasmette ciascun fotogramma al server come JPEG in codifica base64
4. Riceve la regione di interesse (ROI) elaborata e il valore BPM corrente
5. Sovrappone la ROI amplificata al video live e aggiorna l'interfaccia

Il client espone inoltre un controllo per l'acquisizione di screenshot
dell'elaborazione corrente.

---

## 6. Risultati sperimentali

### 6.1 Condizioni operative raccomandate

- Illuminazione uniforme e sufficiente del volto del soggetto
- Posizionamento della fronte all'interno dell'area di rilevamento (riquadro verde)
- Riduzione al minimo degli artefatti motori (movimenti del capo, ammiccamento)

### 6.2 Limitazioni note

- La precisione della stima BPM può degradare in condizioni di scarsa illuminazione
- Movimenti bruschi del soggetto introducono artefatti nel segnale FFT
- La risoluzione temporale è limitata dalla frequenza di acquisizione (15 fps)

---

## 7. Architettura del server web

### 7.1 Ciclo di elaborazione lato server

Il server Flask delega l'elaborazione a un'istanza di `ElaboratoreBattito`,
che mantiene uno stato persistente tra richieste HTTP successive:

```
┌──────────────┐     POST /api/elabora     ┌──────────────────┐
│   Browser    │ ──── JPEG (base64) ──────→ │  Flask server    │
│  (webcam)    │                            │  web_server.py   │
│              │ ←── JSON (BPM + ROI) ──── │                  │
└──────────────┘                            └──────────────────┘
                                                    │
                                           ┌────────▼────────┐
                                           │ ElaboratoreBattito│
                                           │ • buffer circolare│
                                           │ • piramide Gauss. │
                                           │ • FFT / filtro   │
                                           │ • amplificazione │
                                           └─────────────────┘
```

Il buffer circolare di 150 fotogrammi (`config.DIMENSIONE_BUFFER`) garantisce la
continuità temporale del segnale nonostante la natura stateless del protocollo HTTP.

### 7.2 Ciclo di elaborazione lato client

Il client JavaScript esegue un loop asincrono a 15 fps:

1. Acquisizione del fotogramma da `<video>` a `<canvas>` offscreen
2. Conversione in JPEG (`canvas.toBlob`, qualità 0.8)
3. Codifica base64 e trasmissione via `fetch()` a `/api/elabora`
4. Decodifica della risposta e rendering della ROI su `<canvas>` sovrapposto
5. Aggiornamento dell'indicatore BPM e dello stato del semaforo di caricamento

Un meccanismo di mutex (`inAttesa`) impedisce la sovrapposizione di richieste
concorrenti, garantendo l'integrità sequenziale del buffer lato server.

---

## 8. Note legali e licenza

Questo progetto è distribuito esclusivamente a scopo educativo e di ricerca. Non è
autorizzato l'uso commerciale del software o di sue parti. L'algoritmo EVM è di
proprietà intellettuale del MIT CSAIL. Si rimanda alla pubblicazione originale per
la corretta attribuzione del metodo scientifico.

---

## Riferimenti

1. Wu, H.-Y., Rubinstein, M., Shih, E., Guttag, J., Durand, F., & Freeman, W. T.
   (2012). _Eulerian Video Magnification for Revealing Subtle Changes in the World._
   ACM Transactions on Graphics, 31(4).
2. Allen, J. (2007). _Photoplethysmography and its application in clinical
   physiological measurement._ Physiological Measurement, 28(3), R1–R39.
3. Verkruysse, W., Svaasand, L. O., & Nelson, J. S. (2008). _Remote
   plethysmographic imaging using ambient light._ Optics Express, 16(26),
   21434–21445.
