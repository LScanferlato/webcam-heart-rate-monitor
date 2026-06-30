"""
Elaborazione del segnale per il rilevamento del battito cardiaco.
Implementa la piramide gaussiana, la FFT, il filtraggio passa-banda
e l'analisi dell'illuminazione.
"""

import numpy as np
import cv2


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


def calcola_bpm(fft_media, frequenze):
    """
    Calcola il BPM dalla FFT media trovando il picco di frequenza dominante.
    Ignora il componente DC (indice 0) per evitare che domini il picco.
    """
    copia = fft_media.copy()
    copia[0] = 0
    indice_picco = np.argmax(copia)
    frequenza_dominante = frequenze[indice_picco]
    return 60.0 * frequenza_dominante


def amplifica_segnale(fft_filtrata, alfa):
    """
    Amplifica il segnale filtrato e lo riporta nel dominio spaziale.
    """
    segnale_amplificato = np.real(np.fft.ifft(fft_filtrata, axis=0))
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
