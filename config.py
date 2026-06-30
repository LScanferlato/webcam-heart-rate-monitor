"""
Configurazione del monitoraggio battito cardiaco da webcam.
Tutti i parametri modificabili sono raccolti qui.
"""

# --- Parametri webcam ---
RISOLUZIONE_LARGHEZZA = 320
RISOLUZIONE_ALTEZZA = 240

# --- Parametri area di rilevamento ---
AREA_LARGHEZZA = 160
AREA_ALTEZZA = 120
CANALI_VIDEO = 3

# --- Parametri video ---
FOTOGRAMMI_AL_SECONDO = 15

# --- Parametri di magnificazione colore ---
LIVELLI_PIRAMIDE = 3
ALFA_AMPLIFICAZIONE = 170
FREQUENZA_MINIMA = 1.0
FREQUENZA_MASSIMA = 2.0
DIMENSIONE_BUFFER = 150

# --- Parametri calcolo BPM ---
INTERVALLO_CALCOLO_BPM = 15
DIMENSIONE_BUFFER_BPM = 10

# --- Parametri codifica video ---
CODIFICA_VIDEO = 'mp4v'
ESTENSIONE_VIDEO = '.mp4'
NOME_VIDEO_ORIGINALE = 'video_originale' + ESTENSIONE_VIDEO
NOME_VIDEO_ELABORATO = 'video_elaborato' + ESTENSIONE_VIDEO

# --- Parametri visualizzazione ---
COLORE_CASELLA = (0, 255, 0)
SPESSORE_CASELLA = 3
COLORE_TESTO = (255, 255, 255)
DIMENSIONE_CARATTERE = 1
SPESSORE_CARATTERE = 2
POSIZIONE_CARICAMENTO = (20, 30)
POSIZIONE_BPM = (AREA_LARGHEZZA // 2 + 5, 30)
