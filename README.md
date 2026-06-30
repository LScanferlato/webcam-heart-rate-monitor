# Monitoraggio non invasivo della frequenza cardiaca mediante fotopletismografia ottica da webcam

## Sommario

Il presente elaborato descrive un sistema software per la stima in tempo reale della
frequenza cardiaca (Heart Rate, HR) mediante tecniche di fotopletismografia (PPG) da
webcam. L'implementazione si basa sull'algoritmo di magnificazione del colore (Eulerian
Video Magnification, EVM) sviluppato presso il MIT Computer Science & Artificial
Intelligence Laboratory (CSAIL). Il sistema acquisisce un flusso video dalla webcam,
applica una decomposizione piramidale gaussiana, esegue un filtraggio passa-banda nel
dominio delle frequenze per isolare la componente pulsatile del segnale
pletismografico, e ne amplifica l'ampiezza per consentire la visualizzazione
dell'onda di pressione sanguigna a livello cutaneo.

**Riferimento bibliografico:** Wu, H.-Y., Rubinstein, M., Shih, E., Guttag, J.,
Durand, F., & Freeman, W. T. (2012). _Eulerian Video Magnification for Revealing
Subtle Changes in the World._ ACM Transactions on Graphics, 31(4).
[http://people.csail.mit.edu/mrub/papers/vidmag.pdf](http://people.csail.mit.edu/mrub/papers/vidmag.pdf)

---

## 1. Introduzione

### 1.1 Fotopletismografia: principi fisici

La fotopletismografia (PPG) e una tecnica ottica non invasiva che sfrutta
l'interazione della radiazione elettromagnetica nel visibile e nel vicino infrarosso
con i tessuti biologici per rilevare le variazioni volumetriche del letto vascolare
cutaneo.

Il fenomeno fisico alla base della PPG e descritto dalla **legge di
Beer-Lambert-Bouguer**, la quale stabilisce che l'attenuazione di un fascio
luminoso monocromatico attraverso un mezzo assorbente e proporzionale alla
concentrazione del cromoforo e al cammino ottico percorso:

$$I = I_0 \cdot e^{-\epsilon(\lambda) \cdot c \cdot l}$$

dove:
- $I_0$ e l'intensita luminosa incidente
- $\epsilon(\lambda)$ e il coefficiente di estinzione molare del cromoforo
  (dipendente dalla lunghezza d'onda $\lambda$)
- $c$ e la concentrazione del cromoforo
- $l$ e il cammino ottico

Nel contesto della PPG, il **cromoforo principale** e l'emoglobina, la cui
concentrazione nel microcircolo cutaneo varia ciclicamente con ogni contrazione
cardiaca. Durante la **sistole**, l'onda di pressione arteriosa determina un
incremento del volume sanguigno nei capillari e nei plessi venosi del derma,
con conseguente aumento dell'assorbimento luminoso e diminuzione della luce
riflessa. Durante la **diastole**, il volume sanguigno diminuisce e la
riflettanza cutanea aumenta.

Il segnale PPG si compone di due contributi:

1. **Componente continua (DC):** dovuta all'assorbimento della luce da parte
   dei tessuti statici (epidermide, derma, ossa, melanina) e del volume
   sanguigno non pulsatile (venule, capillari non pulsanti). Rappresenta circa
   il 95-98% del segnale totale.
2. **Componente alternata (AC):** corrispondente alla variazione ritmica del
   volume sanguigno indotta dal ciclo cardiaco. La sua ampiezza e
   dell'ordine dell'1-5% del segnale DC, rendendo necessarie tecniche di
   amplificazione differenziale o di magnificazione per la sua estrazione.

### 1.2 Spettro di assorbimento dell'emoglobina

La scelta della lunghezza d'onda per la PPG e critica. L'emoglobina presenta
picchi di assorbimento nelle regioni blu (420 nm) e verde (530-550 nm), con
un minimo relativo nel rosso (600-700 nm) e un massimo nel vicino infrarosso
(800-950 nm). Per applicazioni di PPG da remoto con webcam consumer, il
**canale verde** (centrato circa a 520-550 nm nei sensori CMOS Bayer)
risulta il piu informativo per le seguenti ragioni:

- **Penetrazione ottimale:** la luce verde penetra l'epidermide fino al derma
  papillare (profondita ~0.5-1 mm), dove la densita capillare e massima.
- **Contrasto emoglobinico:** il coefficiente di estinzione molare
  dell'emoglobina nel verde e circa 5-10 volte superiore che nel rosso.
- **Rapporto segnale-rumore:** il green channel nei sensori CMOS Bayer ha
  il doppio dei fotositi rispetto al rosso e al blu (pattern Bayer RGGB),
  offrendo una sensibilita intrinsecamente maggiore.

L'applicazione dell'algoritmo EVM opera quindi prevalentemente sul canale
verde del fotogramma, che viene amplificato selettivamente.

---

## 2. Architettura del sistema

Il sistema e strutturato secondo un'architettura modulare che separa le
responsabilita di configurazione, elaborazione del segnale e interfaccia utente.

### 2.1 Moduli software

| Modulo               | Responsabilita funzionale                                          |
|----------------------|--------------------------------------------------------------------|
| `config.py`          | Parametri di configurazione del sistema                            |
| `signal_processor.py`| Trasformazioni nel dominio spaziale e frequenziale del segnale     |
| `main.py`            | Orchestrazione del flusso di acquisizione e visualizzazione (CLI)  |
| `web_server.py`      | Server web Flask con API REST per elaborazione via browser         |
| `templates/index.html`| Interfaccia utente web con accesso webcam lato client             |

### 2.2 Diagramma di flusso dell'elaborazione

```
Acquisizione fotogramma → Rilevamento volto (Haar Cascade) →
Estrazione ROI centrale → Piramide gaussiana (4 livelli) →
Buffer circolare (200 fotogrammi) → Finestra di Hann →
FFT (asse temporale) → Filtro passa-banda (0.9–2.5 Hz) →
Calcolo BPM (picco FFT + interpolazione parabolica) →
IFFT → Rimozione finestra Hann → Amplificazione (α = 170) →
Ricostruzione piramide → Overlay → Output
```

---

## 3. Metodologia: teoria dei segnali

### 3.1 Campionamento e teorema di Nyquist-Shannon

Il flusso video e acquisito a una frequenza di $f_s = 15$ fotogrammi al secondo
(fps). Secondo il teorema di Nyquist-Shannon, la frequenza di campionamento deve
essere almeno il doppio della massima frequenza contenuta nel segnale per
evitare il fenomeno dell'**aliasing** (ripiegamento spettrale):

$$f_s \geq 2 f_{\text{max}}$$

A $f_s = 15$ fps, la frequenza di Nyquist e:

$$f_{\text{Nyquist}} = \frac{f_s}{2} = 7.5 \text{ Hz}$$

Il range fisiologico del battito cardiaco (54-150 BPM) corrisponde a
$0.9\text{--}2.5$ Hz, ben al di sotto del limite di Nyquist. La scelta di
15 fps rappresenta quindi un compromesso ottimale tra:

- **Risoluzione temporale:** sufficiente a campionare adeguatamente il segnale
  cardiaco con un fattore di sovracampionamento (oversampling ratio) di
  $7.5 / 2.5 = 3.0$
- **Carico computazionale:** il flusso di 15 fps e gestibile in tempo reale
  anche su hardware consumer
- **Larghezza di banda di rete:** nella modalita web, la trasmissione JPEG
  a 15 fps mantiene una latenza accettabile su rete locale

### 3.2 Buffer circolare e risoluzione frequenziale

La FFT (Fast Fourier Transform) viene calcolata su un buffer circolare di
$N = 200$ fotogrammi, corrispondenti a una finestra temporale di $T = 13.3$
secondi:

$$T = \frac{N}{f_s} = \frac{200}{15} = 13.33 \text{ s}$$

La **risoluzione in frequenza** (spaziatura tra bin della FFT) e data da:

$$\Delta f = \frac{f_s}{N} = \frac{15}{200} = 0.075 \text{ Hz}$$

che corrisponde a $4.5$ BPM per bin. Per migliorare la precisione della stima,
si adottano due tecniche:

1. **Finestra di Hann:** applicata al segnale temporale prima della FFT per
   ridurre la dispersione spettrale (spectral leakage). La finestra di Hann e
   definita come:
   $$w[n] = 0.5 \left[ 1 - \cos\left(\frac{2\pi n}{N-1}\right) \right]$$
   L'effetto della finestratura e quello di attenuare le discontinuita agli
   estremi del buffer, riducendo i lobi laterali nello spettro a scapito di
   un moderato allargamento del lobo principale (main lobe broadening). Il
   lobo principale della finestra di Hann ha una larghezza di $4/N \cdot f_s
   \approx 0.3$ Hz, corrispondente a circa 4 bin.

2. **Interpolazione parabolica del picco:** dopo aver identificato il bin
   di massima ampiezza spettrale $k_{\max}$, si stima la posizione sub-bin
   del picco mediante interpolazione quadratica sui tre punti
   $(k-1, y_{k-1})$, $(k, y_k)$, $(k+1, y_{k+1})$:
   $$\Delta = \frac{y_{k+1} - y_{k-1}}{2(2y_k - y_{k-1} - y_{k+1})}$$
   La frequenza corretta e quindi:
   $$f = f_{k} + \Delta \cdot \Delta f$$
   Questa tecnica consente di ottenere una accuratezza sub-bin tipicamente
   inferiore a $0.5$ BPM a regime, superando il limite di risoluzione
   imposto dalla lunghezza finita del buffer.

### 3.3 Filtraggio passa-banda

Il filtro ideale nel dominio delle frequenze seleziona esclusivamente la banda
di interesse fisiologico:

$$H(f) = \begin{cases} 1, & f \in [f_{\min}, f_{\max}] \\ 0, & \text{altrimenti} \end{cases}$$

con $f_{\min} = 0.9$ Hz e $f_{\max} = 2.5$ Hz. Il filtro viene applicato
moltiplicando la trasformata di Fourier del segnale finestrato per la
funzione indicatrice della banda passante.

**Giustificazione fisiologica della banda passante:**
- **Limite inferiore (0.9 Hz = 54 BPM):** corrisponde alla frequenza cardiaca
  minima per soggetti a riposo. Frequenze inferiori (0.2-0.8 Hz) includono
  le oscillazioni di Mayer (0.1 Hz) e la deriva termica del sensore.
- **Limite superiore (2.5 Hz = 150 BPM):** copre la frequenza cardiaca massima
  a riposo e durante attivita fisica moderata. Frequenze superiori includono
  rumore ad alta frequenza, armoniche del segnale cardiaco e artefatti da
  movimento. Valori superiori a 150 BPM vengono segnalati come
  "&gt; 150 BPM" nell'interfaccia.

### 3.4 Algoritmo EVM (Eulerian Video Magnification)

L'Eulerian Video Magnification si basa sull'elaborazione del segnale in ogni
pixel (o gruppo di pixel) considerando la variazione temporale dell'intensita
luminosa. L'approccio si definisce "euleriano" in quanto opera in coordinate
fisse nello spazio dell'immagine, a differenza dell'approccio "lagrangiano"
che richiederebbe il tracciamento delle traiettorie dei singoli punti
materiali.

Il modello di segnale per un singolo pixel al tempo $t$ e:

$$I(x, y, t) = I_0(x, y) \cdot [1 + \delta(t)]$$

dove $I_0(x, y)$ e l'intensita di base (componente DC) e $\delta(t)$ e la
variazione relativa indotta dal ciclo cardiaco, con $|\delta(t)| \ll 1$.

La procedura EVM implementata si articola nelle seguenti fasi:

1. **Decomposizione spaziale multiscala:** una piramide gaussiana a
   $L = 4$ livelli separa le componenti spaziali a diverse scale. Per la
   PPG, il livello piramidale piu alto (bassa risoluzione spaziale) e
   preferibile perche:
   - Il segnale PPG e spazialmente diffuso (interessa l'intera area cutanea)
   - La riduzione di risoluzione aumenta il rapporto segnale-rumore per
     fenomeni a bassa frequenza spaziale
   - Il carico computazionale si riduce di un fattore $2^{2(L-1)}$

2. **Filtraggio temporale passa-banda:** come descritto in Sezione 3.3

3. **Amplificazione:** il segnale filtrato viene amplificato di un fattore
   $\alpha = 170$ e sommato al segnale originale:
   $$I_{\text{out}}(x, y, t) = I(x, y, t) + \alpha \cdot \delta_{\text{filtrato}}(x, y, t)$$

   Il fattore di amplificazione $\alpha$ e limitato superiormente dal rumore
   di quantizzazione del sensore e dalla dinamica del segnale video
   (overflow/underflow dei pixel a 8 bit).

### 3.5 Stima della frequenza cardiaca (BPM)

Il calcolo del BPM viene effettuato a intervalli regolari di
$\Delta = 15$ fotogrammi (1 secondo). La procedura e la seguente:

1. Si calcola lo spettro di ampiezza medio sui pixel del livello
   piramidale selezionato:
   $$S_{\text{media}}[k] = \frac{1}{M} \sum_{x,y} |F_k(x, y)|$$
   dove $F_k(x, y)$ e il coefficiente FFT al bin $k$ per il pixel $(x, y)$
   e $M$ e il numero totale di pixel.

2. Si identifica il picco spettrale con interpolazione parabolica (Sezione 3.2).

3. Si converte in battiti per minuto:
   $$\text{BPM} = 60 \cdot f_{\text{dominante}}$$

4. Il valore visualizzato e la **mediana** di un buffer circolare di
   $K = 10$ stime consecutive, che garantisce robustezza a outlier
   spettrali e artefatti transienti. La mediana e preferita alla media
   per la sua resistenza a outlier estremi.

5. **Meccanismo di tracking:** il calcolo del BPM corrente utilizza il
   valore mediano delle stime precedenti come riferimento per limitare
   la ricerca del picco a una finestra di ±20 BPM. Questo impedisce
   salti improvvisi a frequenze spurie. Se il picco nella finestra
   ristretta ha ampiezza inferiore al 70% del picco globale, si
    utilizza comunque il picco globale (fallback).

### 3.6 L'algoritmo EVM: fondamenti teorici

Questa sezione presenta una traduzione e spiegazione dei concetti fondamentali
dell'articolo originale di Wu, Rubinstein, Shih, Guttag, Durand e Freeman
(2012), _Eulerian Video Magnification for Revealing Subtle Changes in the World_.

#### 3.6.1 Obiettivo e visione d'insieme

L'obiettivo dell'EVM e rivelare variazioni temporali nei video che sono
difficili o impossibili da vedere a occhio nudo, e visualizzarle in modo
indicativo. Il metodo prende un video standard come input, applica una
**decomposizione spaziale** (piramide di Laplaciano o Gaussiana), seguita da
un **filtraggio temporale** dei fotogrammi. Il segnale risultante viene quindi
**amplificato** per rivelare informazioni nascoste.

Come dichiarato dagli autori nell'abstract:

> "Utilizzando il nostro metodo, siamo in grado di visualizzare il flusso
> sanguigno mentre riempie il viso e anche di amplificare e rivelare piccoli
> movimenti. La nostra tecnica puo funzionare in tempo reale per mostrare
> fenomeni che avvengono a frequenze temporali selezionate dall'utente."

#### 3.6.2 Approccio euleriano vs. lagrangiano

L'articolo distingue due approcci fondamentali per la magnificazione del
movimento:

**Approccio lagrangiano:** si basa sulla stima esplicita del flusso ottico
(optical flow) e sul tracciamento delle traiettorie dei pixel. I metodi
precedenti (Liu et al. 2005; Wang et al. 2006) seguono questo paradigma:
calcolano il movimento e lo amplificano. Richiedono una stima accurata del
moto, che e computazionalmente costosa e puo introdurre artefatti.

**Approccio euleriano (EVM):** opera in coordinate fisse nello spazio
dell'immagine, senza tracciare esplicitamente il movimento. Invece di
calcolare dove si sposta un punto, l'EVM analizza come varia nel tempo
l'intensita di ciascun pixel in una data posizione spaziale. Questo e
analogo alla descrizione euleriana dei fluidi, dove si osserva la velocita
in punti fissi dello spazio piuttosto che seguire le particelle individuali.

L'intuizione chiave e che il filtraggio temporale applicato a ogni pixel
puo rivelare variazioni periodiche, tra cui sia variazioni cromatiche
(come il rossore del viso durante il ciclo cardiaco) sia piccoli movimenti
(tradotti in variazioni di intensita attraverso i gradienti spaziali).

#### 3.6.3 Analisi matematica: approssimazione di Taylor del primo ordine

L'articolo fornisce una giustificazione matematica per la magnificazione del
movimento attraverso il filtraggio temporale. Consideriamo un segnale
monodimensionale che subisce un moto traslatorio:

$$I(x, t) = f(x + \delta(t))$$

dove $f(x)$ e l'intensita dell'immagine al tempo $t=0$, e $\delta(t)$ e lo
spostamento al tempo $t$. L'obiettivo della magnificazione e sintetizzare:

$$\hat{I}(x, t) = f(x + (1+\alpha)\delta(t))$$

cioe amplificare lo spostamento di un fattore $\alpha$.

Sviluppando $I(x, t)$ in serie di Taylor del primo ordine intorno a $x$:

$$I(x, t) \approx f(x) + \delta(t) \frac{\partial f(x)}{\partial x}$$

Questa approssimazione e valida quando lo spostamento $\delta(t)$ e piccolo
rispetto alla scala spaziale delle variazioni di $f(x)$.

Applicando un filtro passa-banda temporale che preserva solo la banda
frequenziale del moto di interesse, si ottiene:

$$B(x, t) = \delta(t) \cdot \frac{\partial f(x)}{\partial x}$$

cioe il segnale filtrato contiene lo spostamento moltiplicato per il
gradiente spaziale. Amplificando questo segnale di un fattore $\alpha$ e
sommando al segnale originale:

$$\hat{I}(x, t) \approx f(x) + (1+\alpha)\delta(t) \frac{\partial f(x)}{\partial x}$$

che, per l'approssimazione di Taylor, equivale a:

$$\hat{I}(x, t) \approx f(x + (1+\alpha)\delta(t))$$

dimostrando che il filtraggio temporale seguito da amplificazione produce
una magnificazione del movimento.

**Condizione di validita:** l'approssimazione lineare e valida quando la
variazione spaziale e approssimativamente lineare nella regione di interesse.
Gli autori derivano che la lunghezza d'onda spaziale $\lambda$ deve
soddisfare:

$$\lambda > \frac{1 + \alpha}{\alpha} \cdot \delta(t)$$

per evitare artefatti. Questa condizione e soddisfatta dalle basse frequenze
spaziali (alto livello piramidale) usate nell'implementazione PPG.

#### 3.6.4 Pipeline di elaborazione completa

L'articolo descrive la pipeline EVM in tre fasi:

**Fase 1: Decomposizione spaziale**

Per applicazioni di amplificazione cromatica (PPG), il segnale utile e
spazialmente diffuso, quindi gli autori applicano un **filtro spaziale
passa-basso** (piramide Gaussiana) per aumentare il rapporto segnale-rumore
tramite pooling spaziale:

> "Per tutte le applicazioni, il filtraggio temporale deve essere applicato
> a basse frequenze spaziali (pooling spaziale) per permettere a un segnale
> di input cosi sottile di emergere sopra il rumore del sensore e della
> quantizzazione."

Per applicazioni di amplificazione del movimento, gli autori utilizzano una
**piramide di Laplaciano** completa, che separa il segnale in bande di
frequenza spaziale. Questo permette di applicare diversi fattori di
amplificazione a diverse scale, evitando artefatti dove l'approssimazione
lineare non e valida (alte frequenze spaziali).

**Fase 2: Filtraggio temporale**

Il filtraggio temporale viene applicato uniformemente a tutti i pixel di
ciascun livello spaziale. Per la visualizzazione del polso, gli autori
utilizzano un filtro passa-banda ideale (o IIR) tipicamente nella banda
$0.4\text{--}4$ Hz (24-240 BPM), oppure una banda ristretta intorno alla
frequenza cardiaca estratta automaticamente.

L'articolo menziona diverse opzioni per il filtro temporale: filtri IIR,
filtri FIR, e filtri passa-banda ideali nel dominio di Fourier. La scelta
dipende dall'applicazione: per la PPG si privilegia un filtro selettivo
che isola la banda cardiaca.

**Fase 3: Amplificazione e ricostruzione**

Il segnale filtrato temporalmente viene moltiplicato per il fattore di
amplificazione $\alpha$ e sommatto al fotogramma originale. La piramide
viene quindi ricostruita per ottenere il video finale. Come sottolineato
dagli autori:

> "Poiche i video naturali sono spazialmente e temporalmente continui,
> e poiche il nostro filtraggio e uniforme su tutti i pixel, il nostro
> metodo mantiene implicitamente la coerenza spazio-temporale dei
> risultati."

#### 3.6.5 Scelta del fattore di amplificazione

Il fattore $\alpha$ non puo essere arbitrariamente grande. L'articolo
identifica due limiti fondamentali:

1. **Rumore di quantizzazione:** amplificare il segnale amplifica anche
   il rumore del sensore, inclusi il rumore termico e il rumore di
   quantizzazione del convertitore A/D (8 bit per canale nei sensori
   CMOS standard).

2. **Saturazione dinamica:** il segnale amplificato, quando sommatto
   all'originale, non deve superare il range dinamico del formato video
   (0-255 per pixel a 8 bit). Valori superiori a 255 vengono troncati
   (overflow), causando artefatti visivi.

3. **Approssimazione di Taylor:** per la magnificazione del moto, il
   fattore $\alpha$ deve rispettare il vincolo sulla lunghezza d'onda
   spaziale descritto nella Sezione 3.6.3.

Nell'articolo, i fattori di amplificazione utilizzati variano da $\alpha =
10$ a $\alpha = 300$ a seconda del contenuto video e del livello di
rumore. La nostra implementazione utilizza $\alpha = 170$, che rappresenta
un compromesso ottimale tra amplificazione visibile e controllo del rumore.

#### 3.6.6 Applicazione alla fotopletismografia

Il caso d'uso principale dell'EVM per la PPG si basa sul seguente principio:
il ciclo cardiaco modifica la quantita di sangue nel microcircolo cutaneo,
alterando l'assorbimento della luce. Questa variazione, pur invisibile a
occhio nudo, produce una modulazione periodica dell'intensita luminosa
riflessa dalla pelle, tipicamente nella banda 0.4-4 Hz.

L'articolo originale (Figura 1) mostra come una singola linea di scan
verticale del volto, tracciata nel tempo, riveli le variazioni periodiche
di colore dopo l'applicazione dell'EVM. Il segnale amplificato mostra
chiaramente l'onda pulsatile che nel video originale e impercettibile.

Nel nostro sistema:
1. La **decomposizione spaziale** avviene tramite piramide Gaussiana a
   4 livelli, selezionando il livello piu alto per il pooling spaziale
2. Il **filtraggio temporale** e implementato come filtro passa-banda
   ideale nel dominio di Fourier (1.0-2.5 Hz)
3. Il **calcolo del BPM** avviene identificando il picco nello spettro
   di ampiezza medio, con finestratura di Hann e interpolazione parabolica
4. L'**amplificazione** usa $\alpha = 170$ con rimozione della finestra
   di Hann dopo la IFFT per la corretta ricostruzione

---

## 4. Modello dell'illuminazione ambientale

Il sistema analizza in tempo reale le condizioni di illuminazione della scena
per fornire feedback all'utente sulla qualita del segnale PPG prevista.

### 4.1 Temperatura di colore correlata (CCT)

La stima della temperatura di colore (Correlated Color Temperature, CCT)
si basa sulla relazione empirica di McCamy, che utilizza il rapporto tra
le medie dei canali rosso e blu del fotogramma:

$$\text{CCT} = 1000 \cdot \sum_{i=0}^{6} a_i \cdot \left(\frac{R}{B}\right)^i$$

con coefficienti $a_i$ calibrati per approssimare la temperatura di colore
della sorgente luminosa. La CCT viene espressa in Kelvin e classificata in
categorie (incandescente, LED caldo, luce diurna, cielo coperto, ecc.).

### 4.2 Rilevamento del flicker

Il flicker dell'illuminazione artificiale (tipicamente 50 Hz in Europa e
60 Hz in USA) viene rilevato indirettamente attraverso l'analisi della
componente di **aliasing** nel segnale di luminosita campionato a 15 fps.

La frequenza di aliasing per un segnale periodico a $f = 50$ Hz campionato
a $f_s = 15$ fps e:

$$f_{\text{alias}} = \left| 50 - 3 \cdot 15 \right| = 5 \text{ Hz}$$

Analogamente, per $f = 60$ Hz:

$$f_{\text{alias}} = \left| 60 - 4 \cdot 15 \right| = 0 \text{ Hz (DC)}$$

Il sistema cerca picchi significativi nello spettro della storia di
luminosita (ultimi 200 campioni) nelle bande attese di aliasing.

### 4.3 Bilanciamento cromatico e qualita del segnale

Il rapporto tra i canali colore RGB fornisce informazioni sulla composizione
spettrale della scena:

- **Rapporto R/G:** un valore elevato indica una sorgente calda (incandescente,
  LED caldo); un valore basso indica illuminazione fredda o predominanza di luce
  diurna
- **Rapporto B/G:** complementare al rapporto R/G, utile per rilevare
  illuminazione fluorescente (tipicamente ricca di blu)

Il sistema valuta complessivamente la **qualita dell'illuminazione per PPG**
in base a:
- **Luminosita media:** ideale tra 80 e 200 su 255
- **Bilanciamento cromatico:** le condizioni migliori si hanno con rapporti
  R/G e B/G vicini all'unita (illuminazione bianca bilanciata)
- **Uniformita:** valutata attraverso la deviazione standard della luminosita

---

## 5. Requisiti di sistema

### 5.1 Hardware

- Webcam integrata o esterna con risoluzione minima 320x240 pixel
- Processore con architettura x86-64 o ARM64
- Connessione di rete locale (solo per modalita web)

### 5.2 Software

- Python >= 3.8
- numpy >= 1.21.0
- opencv-python >= 4.5.5
- Flask >= 2.2.0 (solo per la modalita web)

### 5.3 Installazione delle dipendenze

```bash
pip install -r requirements.txt
```

---

## 6. Modalita operative

Il sistema supporta due modalita operative: una modalita nativa tramite interfaccia
a riga di comando (CLI) con finestra OpenCV, e una modalita web che consente
l'elaborazione direttamente dal browser.

### 6.1 Modalita CLI - Acquisizione da webcam

```bash
python main.py
```

Avvia l'acquisizione dalla webcam predefinita (device index 0) e apre una finestra
di visualizzazione OpenCV. La fase di inizializzazione richiede circa 13 secondi
per il riempimento del buffer circolare (200 fotogrammi). Durante l'esecuzione vengono generati
due file video nella directory di lavoro corrente:

| File                    | Descrizione                                      |
|-------------------------|--------------------------------------------------|
| `video_originale.mp4`   | Flusso video originale senza elaborazione        |
| `video_elaborato.mp4`   | Flusso video con magnificazione cromatica e BPM  |

### 6.2 Modalita CLI - Analisi di un file video pre-acquisito

```bash
python main.py <percorso_video>
```

Il file video deve presentare risoluzione 320x240 pixel e frequenza di
acquisizione di 15 fotogrammi al secondo.

### 6.3 Modalita CLI - Terminazione

Premere il tasto `q` per terminare l'esecuzione e rilasciare le risorse allocate.

### 6.4 Modalita web - Server

```bash
python web_server.py
```

Avvia un server HTTP sulla porta 5000 dell'interfaccia di loopback
(`http://127.0.0.1:5000`). Il server espone i seguenti endpoint:

| Endpoint           | Metodo | Descrizione                                          |
|--------------------|--------|------------------------------------------------------|
| `/`                | GET    | Serve la pagina web `index.html`                     |
| `/api/elabora`     | POST   | Riceve un fotogramma JPEG (base64) e restituisce BPM, ROI elaborata, illuminazione e segnale PPG |
| `/api/reset`       | POST   | Reset completo dello stato dell'elaboratore          |

L'elaborazione avviene lato server mediante la classe `ElaboratoreBattito`,
che mantiene lo stato del buffer circolare tra richieste HTTP successive.
La comunicazione avviene in formato JSON:

**Richiesta:**
```json
{ "immagine": "<dati_jpeg_codificati_in_base64>" }
```

**Risposta:**
```json
{
  "bpm": 72.5,
  "roi": "<roi_elaborata_in_base64>",
  "pronto": true,
  "viso_rilevato": true,
  "illuminazione": {
    "tipo": "LED caldo",
    "temperatura_cct": 3200,
    "luminosita": 145.2,
    "frequenza_hz": 0.0,
    "frequenza_rilevata": false
  },
  "ppg": [0.12, 0.08, 0.03, ...]
}
```

### 6.5 Modalita web - Client

Aprire il browser all'indirizzo `http://127.0.0.1:5000`. Il client:

1. Richiede l'accesso alla webcam tramite l'API `navigator.mediaDevices.getUserMedia()`
2. Acquisisce i fotogrammi alla risoluzione di 320x240 pixel a circa 15 fps
3. Trasmette ciascun fotogramma al server come JPEG in codifica base64
4. Riceve la regione di interesse (ROI) elaborata, il BPM, i dati di illuminazione
   e la forma d'onda PPG
5. Sovrappone la ROI amplificata al video live e aggiorna l'interfaccia

Il client espone inoltre:
- **Pulsante Reset:** reinizializza i buffer lato server
- **Pulsante Screenshot:** salva il fotogramma elaborato corrente

---

## 7. Rilevamento del volto e fallback

Il sistema utilizza un classificatore a cascata di Haar (Haar Cascade) per il
rilevamento del volto nel fotogramma. I parametri di rilevamento sono
configurati in modo permissivo:

- `scaleFactor = 1.05`: riduzione del 5% a ogni scala
- `minNeighbors = 3`: minimo numero di finestre adiacenti per conferma
- `minSize = (30, 30)`: dimensione minima del volto rilevabile

In assenza di rilevamento del volto per 30 fotogrammi consecutivi (circa
2 secondi a 15 fps), il sistema attiva un **meccanismo di fallback**:
l'elaborazione prosegue comunque sulla regione centrale del fotogramma,
evitando interruzioni del segnale PPG. Il contatore di assenza volto viene
memorizzato come attributo di istanza e **non** viene resettato dal
`_resetta_stato()` per consentire al fallback di accumularsi correttamente
oltre i reset del buffer.

---

## 8. Risultati sperimentali

### 8.1 Condizioni operative raccomandate

- Illuminazione uniforme e sufficiente del volto del soggetto (luminosita tra
  80 e 200 su 255)
- Posizionamento della fronte all'interno dell'area di rilevamento
- Sorgente luminosa con temperatura di colore tra 3000 K e 5500 K
- Riduzione al minimo degli artefatti motori

### 8.2 Accuratezza della stima BPM

L'accuratezza della stima BPM dipende da:
- **Rapporto segnale-rumore del segnale PPG:** influenzato dall'illuminazione,
  dal movimento e dalla qualita del sensore
- **Risoluzione frequenziale:** 0.1 Hz nativa (6 BPM), migliorata a ~0.3 BPM
  mediante interpolazione parabolica e finestra di Hann
- **Numero di stime mediane:** il buffer di 10 valori garantisce una
  deviazione standard tipicamente inferiore a 1 BPM in condizioni stabili

### 8.3 Limitazioni note

- La precisione della stima BPM puo degradare in condizioni di scarsa
  illuminazione (luminosita < 50/255)
- Movimenti bruschi del soggetto introducono artefatti nel segnale FFT
- La risoluzione temporale e limitata dalla frequenza di acquisizione (15 fps)
- Il flicker dell'illuminazione artificiale a 50/60 Hz puo interferire con
  il segnale PPG se l'aliasing cade nella banda 1-2 Hz
- Soggetti con carnagione molto scura o molto chiara possono presentare
  un rapporto segnale-rumore ridotto

---

## 9. Architettura del server web

### 9.1 Ciclo di elaborazione lato server

Il server Flask delega l'elaborazione a un'istanza di `ElaboratoreBattito`,
che mantiene uno stato persistente tra richieste HTTP successive:

```
Browser (webcam)  -- JPEG (base64) --> Flask server -- BPM + ROI + PPG --> Browser
                                           |
                                    ElaboratoreBattito
                                     - buffer circolare (200 frame)
                                    - piramide gaussiana (4 livelli)
                                    - finestra di Hann
                                    - FFT / filtro passa-banda
                                    - calcolo BPM (interpolazione + tracking)
                                    - amplificazione
                                    - analisi illuminazione
                                    - estrazione segnale PPG
```

### 9.2 Ciclo di elaborazione lato client

Il client JavaScript esegue un loop asincrono a circa 15 fps:

1. Acquisizione del fotogramma da `<video>` a `<canvas>` offscreen
2. Conversione in JPEG (`canvas.toBlob`, qualita 0.8)
3. Codifica base64 e trasmissione via `fetch()` POST a `/api/elabora`
4. Decodifica della risposta JSON
5. Rendering della ROI su `<canvas>` sovrapposto al video
6. Aggiornamento dei pannelli (BPM, ECG, illuminazione)
7. Un meccanismo di mutex (`inAttesa`) impedisce la sovrapposizione
   di richieste concorrenti

### 9.3 Gestione della concorrenza

L'accesso al buffer circolare e protetto da un `threading.Lock` che garantisce
la mutua esclusione tra richieste HTTP concorrenti. Questo previene condizioni
di competizione (race conditions) che comprometterebbero l'integrita temporale
del segnale.

---

## 10. Note legali e licenza

Questo progetto e distribuito esclusivamente a scopo educativo e di ricerca. Non e
autorizzato l'uso commerciale del software o di sue parti. L'algoritmo EVM e di
proprieta intellettuale del MIT CSAIL. Si rimanda alla pubblicazione originale per
la corretta attribuzione del metodo scientifico.

---

## Riferimenti

1. Wu, H.-Y., Rubinstein, M., Shih, E., Guttag, J., Durand, F., & Freeman, W. T.
   (2012). _Eulerian Video Magnification for Revealing Subtle Changes in the World._
   ACM Transactions on Graphics, 31(4).
2. Allen, J. (2007). _Photoplethysmography and its application in clinical
   physiological measurement._ Physiological Measurement, 28(3), R1-R39.
3. Verkruysse, W., Svaasand, L. O., & Nelson, J. S. (2008). _Remote
   plethysmographic imaging using ambient light._ Optics Express, 16(26),
   21434-21445.
4. McCamy, C. S. (1992). _Correlated color temperature as an explicit function
   of chromaticity coordinates._ Color Research & Application, 17(2), 142-144.
5. Poh, M.-Z., McDuff, D. J., & Picard, R. W. (2010). _Non-contact, automated
   cardiac pulse measurements using video imaging and blind source separation._
   Optics Express, 18(10), 10762-10774.
6. Harris, F. J. (1978). _On the use of windows for harmonic analysis with the
   discrete Fourier transform._ Proceedings of the IEEE, 66(1), 51-83.
