"""
Server web per monitoraggio battito cardiaco via browser.
Fornisce un'interfaccia web che utilizza la webcam del browser
e invia i fotogrammi al backend per l'elaborazione.
"""

import base64
import logging
import threading

import cv2
import numpy as np
from flask import Flask, jsonify, render_template, request

import config
from signal_processor import (
    amplifica_segnale,
    applica_filtro_passa_banda,
    applica_hann,
    calcola_bpm,
    calcola_maschera_frequenze,
    calcola_luminosita,
    calcola_temperatura_colore,
    classifica_illuminazione,
    costruisci_piramide_gaussiana,
    rileva_frequenza_illuminazione,
    ricostruisci_fotogramma,
)

_cascade_volto = cv2.CascadeClassifier(
    cv2.data.haarcascades + "haarcascade_frontalface_default.xml"
)

STORIA_LUMINOSITA_MAX = 150
STORIA_PPG_MAX = 300


class ElaboratoreBattito:
    """
    Mantiene lo stato dell'elaborazione tra richieste successive.
    Ogni chiamata a `elabora_fotogramma` processa un nuovo frame
    aggiornando il buffer circolare interno.
    """

    def __init__(self):
        self._lock = threading.Lock()
        self._resetta_stato()

    def _resetta_stato(self):
        """Reinizializza tutti i buffer e contatori."""
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
        self.valori_bpm_validi = 0
        self.storia_luminosita = []
        self.storia_ppg = []

    def resetta(self):
        """Reset completo dello stato (thread-safe)."""
        with self._lock:
            self._conteggio_senza_volto = 0
            self._resetta_stato()

    def elabora_fotogramma(self, frame):
        """
        Elabora un singolo fotogramma: rileva volto, estrae ROI, aggiorna buffer,
        applica FFT, filtraggio, amplificazione, calcolo BPM e analisi illuminazione.
        Restituisce (bpm, roi, pronto, viso_rilevato, dati_illuminazione).
        """
        with self._lock:
            return self._elabora_fotogramma_interno(frame)

    def _rileva_volto(self, frame):
        """
        Rileva la presenza di un volto nel frame.
        Usa parametri permissivi e fallback: se non trova volto per
        parecchi frame consecutivi, processa comunque per evitare blocchi.
        """
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        volti = _cascade_volto.detectMultiScale(
            gray, scaleFactor=1.05, minNeighbors=3, minSize=(30, 30)
        )
        trovato = len(volti) > 0

        if trovato:
            self._conteggio_senza_volto = 0
            return True

        self._conteggio_senza_volto = getattr(self, '_conteggio_senza_volto', 0) + 1
        if self._conteggio_senza_volto >= 30:
            return True
        return False

    def _analizza_illuminazione(self, frame):
        """Analizza illuminazione: temperatura colore, luminosita, frequenza flicker."""
        temperatura = calcola_temperatura_colore(frame)
        luminosita = calcola_luminosita(frame)
        self.storia_luminosita.append(luminosita)
        if len(self.storia_luminosita) > STORIA_LUMINOSITA_MAX:
            self.storia_luminosita = self.storia_luminosita[-STORIA_LUMINOSITA_MAX:]

        frequenza, amp_flicker, has_flicker = rileva_frequenza_illuminazione(
            self.storia_luminosita, config.FOTOGRAMMI_AL_SECONDO
        )
        tipo = classifica_illuminazione(temperatura, frequenza, has_flicker)

        return {
            "temperatura_cct": int(temperatura),
            "luminosita": round(luminosita, 1),
            "frequenza_hz": frequenza,
            "frequenza_rilevata": has_flicker,
            "tipo": tipo,
        }

    def _elabora_fotogramma_interno(self, frame):
        viso_rilevato = self._rileva_volto(frame)

        dati_luce = self._analizza_illuminazione(frame)

        if not viso_rilevato:
            self._resetta_stato()
            return 0, frame, False, False, dati_luce, []

        area_rilevamento = self._estrae_centro(frame)

        self.buffer_video[self.indice_buffer] = costruisci_piramide_gaussiana(
            area_rilevamento, config.LIVELLI_PIRAMIDE + 1
        )[config.LIVELLI_PIRAMIDE]

        buffer_windowed = applica_hann(self.buffer_video)
        fft = np.fft.fft(buffer_windowed, axis=0)
        fft_filtrata = applica_filtro_passa_banda(fft, self.maschera)

        bpm = None
        if self.indice_buffer % config.INTERVALLO_CALCOLO_BPM == 0:
            for idx in range(config.DIMENSIONE_BUFFER):
                self.media_fft[idx] = np.abs(fft_filtrata[idx]).mean()
            bpm = calcola_bpm(self.media_fft, self.frequenze)
            self.buffer_bpm[self.indice_bpm] = bpm
            self.indice_bpm = (self.indice_bpm + 1) % config.DIMENSIONE_BUFFER_BPM
            self.conteggio_calcoli += 1
            self.valori_bpm_validi = min(
                self.valori_bpm_validi + 1, config.DIMENSIONE_BUFFER_BPM
            )
            if self.conteggio_calcoli > config.DIMENSIONE_BUFFER_BPM:
                self.bpm_pronto = True

        segnale_amplificato = amplifica_segnale(
            fft_filtrata, config.ALFA_AMPLIFICAZIONE
        )

        valore_ppg = float(np.mean(segnale_amplificato[self.indice_buffer]))
        self.storia_ppg.append(valore_ppg)
        if len(self.storia_ppg) > STORIA_PPG_MAX:
            self.storia_ppg = self.storia_ppg[-STORIA_PPG_MAX:]

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

        bpm_medio = (
            self.buffer_bpm[: self.valori_bpm_validi].mean()
            if self.valori_bpm_validi > 0
            else 0
        )
        return bpm_medio, fotogramma_uscita, self.bpm_pronto, True, dati_luce, self.storia_ppg[-60:]

    def _estrae_centro(self, frame):
        """Estrae la porzione centrale del frame, ridimensionandola se necessario."""
        altezza, larghezza = frame.shape[:2]
        if altezza != config.RISOLUZIONE_ALTEZZA or larghezza != config.RISOLUZIONE_LARGHEZZA:
            frame = cv2.resize(
                frame, (config.RISOLUZIONE_LARGHEZZA, config.RISOLUZIONE_ALTEZZA)
            )
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
    la ROI elaborata, il BPM corrente, il flag volto e dati illuminazione.
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

    bpm, roi_elaborata, pronto, viso_rilevato, dati_luce, segnale_ppg = (
        elaboratore.elabora_fotogramma(frame)
    )

    if viso_rilevato:
        _, buffer_jpeg = cv2.imencode(
            ".jpg", roi_elaborata, [cv2.IMWRITE_JPEG_QUALITY, 85]
        )
        roi_base64 = base64.b64encode(buffer_jpeg).decode("utf-8")
    else:
        roi_base64 = None

    return jsonify({
        "bpm": round(bpm, 1),
        "roi": roi_base64,
        "pronto": pronto,
        "viso_rilevato": viso_rilevato,
        "illuminazione": dati_luce,
        "ppg": [round(v, 2) for v in segnale_ppg],
    })


@app.route("/api/reset", methods=["POST"])
def resetta():
    """Reset completo dello stato dell'elaboratore."""
    elaboratore.resetta()
    return jsonify({"ok": True})


if __name__ == "__main__":
    print("Server avviato su http://127.0.0.1:5000")
    print("Apri il browser e connettiti all'indirizzo sopra.")
    app.run(host="127.0.0.1", port=5000, debug=False)
