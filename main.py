"""
Monitoraggio battito cardiaco da webcam.
Basato sull'algoritmo di magnificazione del colore del MIT CSAIL.
"""

import argparse
import sys

import cv2
import numpy as np

import config
from signal_processor import (
    amplifica_segnale,
    applica_filtro_passa_banda,
    calcola_bpm,
    calcola_maschera_frequenze,
    costruisci_piramide_gaussiana,
    ricostruisci_fotogramma,
)


def inizializza_webcam(percorso_video=None):
    """Inizializza la webcam o apre un file video."""
    percorso = 0 if percorso_video is None else percorso_video
    sorgente = cv2.VideoCapture(percorso)
    if not sorgente.isOpened():
        if percorso_video is not None:
            print(f"ERRORE: Impossibile aprire il file video '{percorso_video}'.")
        else:
            print("ERRORE: Impossibile accedere alla webcam. Verifica che sia connessa.")
        sys.exit(1)
    sorgente.set(3, config.RISOLUZIONE_LARGHEZZA)
    sorgente.set(4, config.RISOLUZIONE_ALTEZZA)
    return sorgente


def inizializza_scrittore_video(nome_file, codice=None):
    """Inizializza un writer per salvare video su disco."""
    if codice is None:
        codice = cv2.VideoWriter_fourcc(*config.CODIFICA_VIDEO)
    writer = cv2.VideoWriter()
    writer.open(
        nome_file,
        codice,
        config.FOTOGRAMMI_AL_SECONDO,
        (config.RISOLUZIONE_LARGHEZZA, config.RISOLUZIONE_ALTEZZA),
        True,
    )
    return writer


def calcola_centro_rilevamento(frame, larghezza_area, altezza_area):
    """Estrae la porzione centrale del frame per l'elaborazione."""
    altezza_frame, larghezza_frame = frame.shape[:2]
    inizio_y = altezza_frame // 2 - altezza_area // 2
    fine_y = inizio_y + altezza_area
    inizio_x = larghezza_frame // 2 - larghezza_area // 2
    fine_x = inizio_x + larghezza_area
    return frame[inizio_y:fine_y, inizio_x:fine_x]


def disegna_interfaccia(frame, bpm_pronto, bpm_medio, conteggio_fotogrammi):
    """Disegna l'interfaccia utente: box di rilevamento e informazioni BPM."""
    altezza_frame, larghezza_frame = frame.shape[:2]
    inizio_x = larghezza_frame // 2 - config.AREA_LARGHEZZA // 2
    inizio_y = altezza_frame // 2 - config.AREA_ALTEZZA // 2
    fine_x = inizio_x + config.AREA_LARGHEZZA
    fine_y = inizio_y + config.AREA_ALTEZZA

    cv2.rectangle(
        frame,
        (inizio_x, inizio_y),
        (fine_x, fine_y),
        config.COLORE_CASELLA,
        config.SPESSORE_CASELLA,
    )

    if bpm_pronto:
        testo_bpm = f"BPM: {int(bpm_medio)}"
        cv2.putText(
            frame,
            testo_bpm,
            config.POSIZIONE_BPM,
            cv2.FONT_HERSHEY_SIMPLEX,
            config.DIMENSIONE_CARATTERE,
            config.COLORE_TESTO,
            config.SPESSORE_CARATTERE,
        )
    else:
        cv2.putText(
            frame,
            "Calcolo BPM in corso...",
            config.POSIZIONE_CARICAMENTO,
            cv2.FONT_HERSHEY_SIMPLEX,
            config.DIMENSIONE_CARATTERE,
            config.COLORE_TESTO,
            config.SPESSORE_CARATTERE,
        )


def esegui_monitoraggio(percorso_video=None):
    """Loop principale di acquisizione ed elaborazione."""
    webcam = inizializza_webcam(percorso_video)
    sorgente_video = percorso_video is not None

    scrittore_originale = None
    if not sorgente_video:
        scrittore_originale = inizializza_scrittore_video(config.NOME_VIDEO_ORIGINALE)

    scrittore_elaborato = inizializza_scrittore_video(config.NOME_VIDEO_ELABORATO)
    primo_fotogramma = np.zeros(
        (config.AREA_ALTEZZA, config.AREA_LARGHEZZA, config.CANALI_VIDEO)
    )
    primo_livello = costruisci_piramide_gaussiana(
        primo_fotogramma, config.LIVELLI_PIRAMIDE + 1
    )[config.LIVELLI_PIRAMIDE]
    buffer_video = np.zeros(
        (
            config.DIMENSIONE_BUFFER,
            primo_livello.shape[0],
            primo_livello.shape[1],
            config.CANALI_VIDEO,
        )
    )

    frequenze, maschera = calcola_maschera_frequenze(
        config.DIMENSIONE_BUFFER,
        config.FOTOGRAMMI_AL_SECONDO,
        config.FREQUENZA_MINIMA,
        config.FREQUENZA_MASSIMA,
    )

    media_fft = np.zeros(config.DIMENSIONE_BUFFER)
    buffer_bpm = np.zeros(config.DIMENSIONE_BUFFER_BPM)
    indice_buffer = 0
    indice_bpm = 0
    conteggio_calcoli_bpm = 0
    bpm_pronto = False
    valori_bpm_validi = 0

    try:
        while True:
            fotogramma_disponibile, fotogramma = webcam.read()
            if not fotogramma_disponibile or fotogramma is None:
                break

            if fotogramma.shape[0] != config.RISOLUZIONE_ALTEZZA or \
                    fotogramma.shape[1] != config.RISOLUZIONE_LARGHEZZA:
                fotogramma = cv2.resize(fotogramma, (config.RISOLUZIONE_LARGHEZZA, config.RISOLUZIONE_ALTEZZA))

            fotogramma_originale = fotogramma.copy()
            if scrittore_originale:
                scrittore_originale.write(fotogramma_originale)

            area_rilevamento = calcola_centro_rilevamento(
                fotogramma, config.AREA_LARGHEZZA, config.AREA_ALTEZZA
            )

            buffer_video[indice_buffer] = costruisci_piramide_gaussiana(
                area_rilevamento, config.LIVELLI_PIRAMIDE + 1
            )[config.LIVELLI_PIRAMIDE]

            fft = np.fft.fft(buffer_video, axis=0)
            fft_filtrata = applica_filtro_passa_banda(fft, maschera)

            if indice_buffer % config.INTERVALLO_CALCOLO_BPM == 0:
                for indice in range(config.DIMENSIONE_BUFFER):
                    media_fft[indice] = np.abs(fft_filtrata[indice]).mean()
                bpm = calcola_bpm(media_fft, frequenze)
                buffer_bpm[indice_bpm] = bpm
                indice_bpm = (indice_bpm + 1) % config.DIMENSIONE_BUFFER_BPM
                conteggio_calcoli_bpm += 1
                valori_bpm_validi = min(valori_bpm_validi + 1, config.DIMENSIONE_BUFFER_BPM)
                if conteggio_calcoli_bpm > config.DIMENSIONE_BUFFER_BPM:
                    bpm_pronto = True

            segnale_amplificato = amplifica_segnale(fft_filtrata, config.ALFA_AMPLIFICAZIONE)
            fotogramma_amplificato = ricostruisci_fotogramma(
                segnale_amplificato,
                indice_buffer,
                config.LIVELLI_PIRAMIDE,
                config.AREA_ALTEZZA,
                config.AREA_LARGHEZZA,
            )

            fotogramma_uscita = area_rilevamento + fotogramma_amplificato
            fotogramma_uscita = cv2.convertScaleAbs(fotogramma_uscita)

            indice_buffer = (indice_buffer + 1) % config.DIMENSIONE_BUFFER

            inizio_y = config.AREA_ALTEZZA // 2
            fine_y = config.RISOLUZIONE_ALTEZZA - config.AREA_ALTEZZA // 2
            inizio_x = config.AREA_LARGHEZZA // 2
            fine_x = config.RISOLUZIONE_LARGHEZZA - config.AREA_LARGHEZZA // 2

            fotogramma[inizio_y:fine_y, inizio_x:fine_x] = fotogramma_uscita
            bpm_medio = buffer_bpm[:valori_bpm_validi].mean() if valori_bpm_validi > 0 else 0
            disegna_interfaccia(fotogramma, bpm_pronto, bpm_medio, conteggio_calcoli_bpm)

            scrittore_elaborato.write(fotogramma)

            if not sorgente_video:
                cv2.imshow("Monitoraggio Battito Cardiaco", fotogramma)
                if cv2.waitKey(1) & 0xFF == ord("q"):
                    break
    finally:
        webcam.release()
        cv2.destroyAllWindows()
        scrittore_elaborato.release()
        if scrittore_originale:
            scrittore_originale.release()


def main():
    """Punto di ingresso principale con parsing degli argomenti."""
    analizzatore = argparse.ArgumentParser(
        description="Monitoraggio del battito cardiaco usando la webcam"
    )
    analizzatore.add_argument(
        "video",
        nargs="?",
        default=None,
        help="Percorso di un file video da analizzare (opzionale)",
    )
    args = analizzatore.parse_args()
    esegui_monitoraggio(args.video)


if __name__ == "__main__":
    main()
