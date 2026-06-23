"""
Elaborazione del segnale per il rilevamento del battito cardiaco.
Implementa la piramide gaussiana, la FFT e il filtraggio passa-banda.
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
    """
    indice_picco = np.argmax(fft_media)
    frequenza_dominante = frequenze[indice_picco]
    return 60.0 * frequenza_dominante


def amplifica_segnale(fft_filtrata, alfa):
    """
    Amplifica il segnale filtrato e lo riporta nel dominio spaziale.
    """
    segnale_amplificato = np.real(np.fft.ifft(fft_filtrata, axis=0))
    return segnale_amplificato * alfa
