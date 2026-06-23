"""
Server web per monitoraggio battito cardiaco via browser.
Fornisce un'interfaccia web che utilizza la webcam del browser
e invia i fotogrammi al backend per l'elaborazione.
"""

import base64
import io
import logging

import cv2
import numpy as np
from flask import Flask, jsonify, render_template, request

import config
from signal_processor import (
    amplifica_segnale,
    applica_filtro_passa_banda,
    calcola_bpm,
    calcola_maschera_frequenze,
    costruisci_piramide_gaussiana,
    ricostruisci_fotogramma,
)


class ElaboratoreBattito:
    """
    Mantiene lo stato dell'elaborazione tra richieste successive.
    Ogni chiamata a `elabora_fotogramma` processa un nuovo frame
    aggiornando il buffer circolare interno.
    """

    def __init__(self):
        primo_fotogramma = np.zeros(
            (config.AREA_ALTEZZA, config.AREA_LARGHEZZA, config.CANALI_VIDEO)
        )
        primo_livello = costruisci_piramide_gaussiana(
            primo_fotogramma, config.LIVELLI_PIRAMIDE + 1
        )[config.LIVELLI_PIRAMIDE]

        self.buffer_video = np.zeros(
            (
                config.DIMENSIONE_BUFFER,
                primo_livello.shape[0],
                primo_livello.shape[1],
                config.CANALI_VIDEO,
            )
        )
        self.frequenze, self.maschera = calcola_maschera_frequenze(
            config.DIMENSIONE_BUFFER,
            config.FOTOGRAMMI_AL_SECONDO,
            config.FREQUENZA_MINIMA,
            config.FREQUENZA_MASSIMA,
        )
        self.media_fft = np.zeros(config.DIMENSIONE_BUFFER)
        self.buffer_bpm = np.zeros(config.DIMENSIONE_BUFFER_BPM)
        self.indice_buffer = 0
        self.indice_bpm = 0
        self.conteggio_calcoli = 0
        self.bpm_pronto = False

    def elabora_fotogramma(self, frame):
        """
        Elabora un singolo fotogramma: estrae ROI, aggiorna buffer,
        applica FFT, filtraggio, amplificazione e calcolo BPM.
        Restituisce BPM, ROI elaborata e flag di prontezza.
        """
        area_rilevamento = self._estrae_centro(frame)

        self.buffer_video[self.indice_buffer] = costruisci_piramide_gaussiana(
            area_rilevamento, config.LIVELLI_PIRAMIDE + 1
        )[config.LIVELLI_PIRAMIDE]

        fft = np.fft.fft(self.buffer_video, axis=0)
        fft_filtrata = applica_filtro_passa_banda(fft, self.maschera)

        bpm = None
        if self.indice_buffer % config.INTERVALLO_CALCOLO_BPM == 0:
            for idx in range(config.DIMENSIONE_BUFFER):
                self.media_fft[idx] = np.real(fft[idx]).mean()
            bpm = calcola_bpm(self.media_fft, self.frequenze)
            self.buffer_bpm[self.indice_bpm] = bpm
            self.indice_bpm = (self.indice_bpm + 1) % config.DIMENSIONE_BUFFER_BPM
            self.conteggio_calcoli += 1
            if self.conteggio_calcoli > config.DIMENSIONE_BUFFER_BPM:
                self.bpm_pronto = True

        segnale_amplificato = amplifica_segnale(
            fft_filtrata, config.ALFA_AMPLIFICAZIONE
        )
        fotogramma_amplificato = ricostruisci_fotogramma(
            segnale_amplificato,
            self.indice_buffer,
            config.LIVELLI_PIRAMIDE,
            config.AREA_ALTEZZA,
            config.AREA_LARGHEZZA,
        )

        fotogramma_uscita = area_rilevamento + fotogramma_amplificato
        fotogramma_uscita = cv2.convertScaleAbs(fotogramma_uscita)

        self.indice_buffer = (self.indice_buffer + 1) % config.DIMENSIONE_BUFFER

        bpm_medio = self.buffer_bpm.mean() if self.bpm_pronto else 0
        return bpm_medio, fotogramma_uscita, self.bpm_pronto

    def _estrae_centro(self, frame):
        """Estrae la porzione centrale del frame, ridimensionandola se necessario."""
        altezza, larghezza = frame.shape[:2]
        if altezza != config.RISOLUZIONE_ALTEZZA or larghezza != config.RISOLUZIONE_LARGHEZZA:
            frame = cv2.resize(frame, (config.RISOLUZIONE_LARGHEZZA, config.RISOLUZIONE_ALTEZZA))
            altezza, larghezza = config.RISOLUZIONE_ALTEZZA, config.RISOLUZIONE_LARGHEZZA
        inizio_y = altezza // 2 - config.AREA_ALTEZZA // 2
        fine_y = inizio_y + config.AREA_ALTEZZA
        inizio_x = larghezza // 2 - config.AREA_LARGHEZZA // 2
        fine_x = inizio_x + config.AREA_LARGHEZZA
        return frame[inizio_y:fine_y, inizio_x:fine_x]


app = Flask(__name__)
elaboratore = ElaboratoreBattito()
logging.basicConfig(level=logging.INFO)


@app.route("/")
def index():
    """Serve la pagina web principale."""
    return render_template("index.html")


@app.route("/api/elabora", methods=["POST"])
def elabora():
    """
    Endpoint REST: riceve un fotogramma JPEG in base64 e restituisce
    la ROI elaborata (sempre in base64) e il BPM corrente.
    """
    dati = request.get_json()
    if not dati or "immagine" not in dati:
        return jsonify({"errore": "Nessun fotogramma ricevuto"}), 400

    try:
        dati_jpeg = base64.b64decode(dati["immagine"])
        array_np = np.frombuffer(dati_jpeg, np.uint8)
        frame = cv2.imdecode(array_np, cv2.IMREAD_COLOR)
        if frame is None:
            raise ValueError("Immagine non valida")
    except Exception as e:
        return jsonify({"errore": f"Decodifica fallita: {e}"}), 400

    bpm, roi_elaborata, pronto = elaboratore.elabora_fotogramma(frame)

    _, buffer_jpeg = cv2.imencode(".jpg", roi_elaborata, [cv2.IMWRITE_JPEG_QUALITY, 85])
    roi_base64 = base64.b64encode(buffer_jpeg).decode("utf-8")

    return jsonify({"bpm": round(bpm, 1), "roi": roi_base64, "pronto": pronto})


if __name__ == "__main__":
    print(f"Server avviato su http://127.0.0.1:5000")
    print("Apri il browser e connettiti all'indirizzo sopra.")
    app.run(host="127.0.0.1", port=5000, debug=False)
