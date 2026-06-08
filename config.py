import os
import json
from dotenv import load_dotenv

# Carrega as variáveis de ambiente do arquivo .env local
load_dotenv()

# --- CONFIGURAÇÕES DO SISTEMA ---
TAXA_AMOSTRAGEM = 44100
TAMANHO_BLOCO = 1024
LIMIAR_VOLUME_PALMA = 0.25  
LIMIAR_VOZ = 0.09          
TEMPO_SILENCIO_MAX = 1.8   
ARQUIVO_AUDIO = "comando_usuario.wav"
ARQUIVO_HISTORICO_DIARIO = "ultima_conversa.txt"
ARQUIVO_LEMBRETES = "lembretes.txt"
ARQUIVO_MEMORIA = "memoria_jarvis.txt"  
MUSICA_INTRO = "back_in_black.wav" 

# --- CONFIGURAÇÃO GEOGRÁFICA (SALVADOR - BAHIA) ---
LATITUDE = os.getenv('LATITUDE', '')  
LONGITUDE = os.getenv('LONGITUDE', '') 

# --- DICIONÁRIO DE CONTATOS (AGENDA DO JARVIS) ---
# A agenda pessoal agora é lida de um arquivo ignorado pelo git (contatos.json)
try:
    with open('contatos.json', 'r', encoding='utf-8') as f:
        AGENDA_CONTATOS = json.load(f)
except FileNotFoundError:
    AGENDA_CONTATOS = {}

# --- CREDENCIAIS DO SPOTIFY ---
SPOTIPY_CLIENT_ID = os.getenv('SPOTIPY_CLIENT_ID')
SPOTIPY_CLIENT_SECRET = os.getenv('SPOTIPY_CLIENT_SECRET')
SPOTIPY_REDIRECT_URI = 'http://127.0.0.1:8080/callback' 

# Constantes do Windows para controle de volume
WM_APPCOMMAND = 0x0319
APPCOMMAND_VOLUME_UP = 0x0A
APPCOMMAND_VOLUME_DOWN = 0x09
APPCOMMAND_VOLUME_MUTE = 0x08

MESES_MAPA = {
    "janeiro": 1, "fevereiro": 2, "marco": 3, "abril": 4, "maio": 5, "junho": 6,
    "julho": 7, "agosto": 8, "setembro": 9, "outubro": 10, "novembro": 11, "dezembro": 12
}