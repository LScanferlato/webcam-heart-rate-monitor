"""
Elaborazione del segnale per il rilevamento del battito cardiaco.
Implementa la piramide gaussiana, la FFT, il filtraggio passa-banda
e l'analisi dell'illuminazione.
"""

import numpy as np
import cv2


# Finestra di Hann precalcolata per ridurre la dispersione spettrale
_HANN_WINDOW = None


def _ottieni_hann(dimensione):
    global _HANN_WINDOW
    if _HANN_WINDOW is None or len(_HANN_WINDOW) != dimensione:
        _HANN_WINDOW = np.hanning(dimensione)
    return _HANN_WINDOW


def applica_hann(buffer):
    """Applica la finestra di Hann lungo l'asse temporale (axis=0)."""
    hann = _ottieni_hann(buffer.shape[0])
    forma = [buffer.shape[0]] + [1] * (buffer.ndim - 1)
    return buffer * hann.reshape(forma)


def rimuovi_hann(segnale, dimensione):
    """Rimuove l'effetto della finestra di Hann (con protezione divisione per zero)."""
    hann = _ottieni_hann(dimensione)
    forma = [dimensione] + [1] * (segnale.ndim - 1)
    hann_reshaped = hann.reshape(forma)
    soglia = 0.1
    hann_safe = np.where(hann_reshaped < soglia, soglia, hann_reshaped)
    return segnale / hann_safe


def costruisci_piramide_gaussiana(frame, livelli):
    """
    Costruisce una piramide gaussiana con il numero di livelli specificato.
    """
    piramide = [frame]
    for _ in range(livelli):
        frame = cv2.pyrDown(frame)
        piramide.append(frame)
    return piramide


def ricostruisci_fotogramma(piramide, indice, livelli, altezza_originale, larghezza_originale):
    """
    Ricostruisce un fotogramma dalla piramide gaussiana applicando pyrUp.
    """
    fotogramma_filtrato = piramide[indice]
    for _ in range(livelli):
        fotogramma_filtrato = cv2.pyrUp(fotogramma_filtrato)
    return fotogramma_filtrato[:altezza_originale, :larghezza_originale]


def calcola_maschera_frequenze(dimensione_buffer, fotogrammi_al_secondo, freq_min, freq_max):
    """
    Crea una maschera booleana per il filtro passa-banda.
    Mantiene solo le frequenze comprese tra freq_min e freq_max Hz.
    """
    frequenze = (fotogrammi_al_secondo * np.arange(dimensione_buffer)) / dimensione_buffer
    maschera = (frequenze >= freq_min) & (frequenze <= freq_max)
    return frequenze, maschera


def applica_filtro_passa_banda(fft, maschera):
    """
    Applica un filtro passa-banda azzerando le frequenze fuori dalla maschera.
    """
    fft_filtrata = fft.copy()
    fft_filtrata[~maschera] = 0
    return fft_filtrata


def calcola_bpm(fft_media, frequenze, bpm_riferimento=None):
    """
    Calcola il BPM dalla FFT media trovando il picco di frequenza dominante
    con interpolazione parabolica per accuratezza sub-bin.
    Ignora il componente DC (indice 0).

    Se bpm_riferimento e' fornito, cerca il picco entro ±20 BPM
    dal riferimento per evitare salti a frequenze spurie.
    Se la finestra di ricerca non contiene picchi validi,
    fa automaticamente fallback alla ricerca globale.
    """
    copia = fft_media.copy()
    copia[0] = 0

    if bpm_riferimento is not None and bpm_riferimento > 0:
        freq_riferimento = bpm_riferimento / 60.0
        delta_freq = 20.0 / 60.0
        cerca_da = max(0, freq_riferimento - delta_freq)
        cerca_a = min(frequenze[-1], freq_riferimento + delta_freq)
        maschera_ricerca = (frequenze >= cerca_da) & (frequenze <= cerca_a)
        if maschera_ricerca.any():
            k_ristretto = int(np.argmax(copia * maschera_ricerca))
            picco_ristretto = copia[k_ristretto]
            # Usa il picco ristretto solo se la magnitudine e' significativa
            # rispetto al picco principale (almeno 70%)
            k_globale = int(np.argmax(copia))
            picco_globale = copia[k_globale]
            if picco_globale > 0 and picco_ristretto / picco_globale >= 0.7:
                k = k_ristretto
            else:
                k = k_globale
        else:
            k = int(np.argmax(copia))
    else:
        k = int(np.argmax(copia))

    # Interpolazione parabolica sub-bin
    if 1 <= k <= len(copia) - 2:
        y0, y1, y2 = float(copia[k-1]), float(copia[k]), float(copia[k+1])
        denom = 2.0 * y1 - y0 - y2
        if denom != 0 and y1 > max(y0, y2):
            delta = 0.5 * (y2 - y0) / denom
            if abs(delta) <= 1.0:
                k_interp = k + delta
                f_low = frequenze[int(np.floor(k_interp))]
                f_high = frequenze[int(np.ceil(k_interp))]
                frac = k_interp - np.floor(k_interp)
                frequenza_dominante = f_low + frac * (f_high - f_low)
                return 60.0 * frequenza_dominante

    frequenza_dominante = frequenze[k]
    return 60.0 * frequenza_dominante


def amplifica_segnale(fft_filtrata, alfa):
    """
    Amplifica il segnale filtrato e lo riporta nel dominio spaziale.
    Rimuove la finestra di Hann applicata prima della FFT.
    """
    segnale_amplificato = np.real(np.fft.ifft(fft_filtrata, axis=0))
    segnale_amplificato = rimuovi_hann(segnale_amplificato, segnale_amplificato.shape[0])
    return segnale_amplificato * alfa


# --- Analisi illuminazione ---

def calcola_temperatura_colore(frame):
    """
    Stima la temperatura di colore correlata (CCT) in Kelvin
    dalla media dei canali B e R del frame (relazione di McCamy).
    """
    media_b = np.mean(frame[:, :, 0].astype(np.float64))
    media_r = np.mean(frame[:, :, 2].astype(np.float64))

    if media_b == 0:
        return 6500.0

    rapporto = media_r / media_b
    if rapporto < 0.5:
        rapporto = 0.5
    elif rapporto > 2.0:
        rapporto = 2.0

    cct = 1000 * (
        -251.3 * rapporto**6
        + 1664.2 * rapporto**5
        - 4012.5 * rapporto**4
        + 3862.9 * rapporto**3
        - 1566.7 * rapporto**2
        + 375.9 * rapporto
        + 20.4
    )

    if cct < 1000:
        cct = 1000.0
    elif cct > 12000:
        cct = 12000.0

    return round(cct, 0)


def calcola_luminosita(frame):
    """Restituisce la luminosita media (0-255) del frame in scala di grigi."""
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    return float(np.mean(gray))


def rileva_frequenza_illuminazione(storia_luminosita, fps):
    """
    Analizza la FFT della storia di luminosita per rilevare
    frequenze di flicker dell'illuminazione (tipicamente 50/60 Hz).
    A 15 fps il Nyquist e' 7.5 Hz, quindi il flicker della rete
    (50/60 Hz) si manifesta come aliasing.
    Restituisce (frequenza_picco_hz,ampiezza_picco,has_flicker).
    """
    n = len(storia_luminosita)
    if n < 20:
        return 0.0, 0.0, False

    segnale = np.array(storia_luminosita, dtype=np.float64)
    segnale -= segnale.mean()

    fft = np.fft.rfft(segnale)
    magnitudine = np.abs(fft)

    frequenze = np.fft.rfftfreq(n, d=1.0 / fps)
    magnitudine[0] = 0

    if magnitudine.max() == 0:
        return 0.0, 0.0, False

    indice_picco = np.argmax(magnitudine)
    freq_picco = frequenze[indice_picco]
    amp_picco = magnitudine[indice_picco]

    soglia_flicker = magnitudine.max() * 0.15
    has_flicker = amp_picco > soglia_flicker and freq_picco > 0.5

    return round(float(freq_picco), 2), round(float(amp_picco), 2), bool(has_flicker)


def classifica_illuminazione(temperatura_cct, frequenza_hz, has_flicker):
    """
    Classifica il tipo di illuminazione in base alla temperatura
    di colore e alla presenza di flicker.
    """
    if frequenza_hz > 0:
        if 45 <= frequenza_hz <= 55 or 90 <= frequenza_hz <= 110:
            return "Neon/fluorescente (50 Hz)"
        if 55 < frequenza_hz <= 65 or 110 < frequenza_hz <= 130:
            return "Neon/fluorescente (60 Hz)"

    if has_flicker:
        if temperatura_cct < 3500:
            return "Fluorescente caldo"
        elif temperatura_cct < 5000:
            return "Fluorescente neutro"
        else:
            return "Fluorescente freddo"

    if temperatura_cct < 2800:
        return "Incandescente"
    elif temperatura_cct < 3500:
        return "LED caldo"
    elif temperatura_cct < 5000:
        return "Fluorescente/LED neutro"
    elif temperatura_cct < 5500:
        return "Luce diurna"
    else:
        return "Cielo coperto/ombra"
