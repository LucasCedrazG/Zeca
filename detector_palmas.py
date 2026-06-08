import os
import subprocess
import time
import threading
import webbrowser
import unicodedata
import re
import ctypes
import numpy as np
import sounddevice as sd
from scipy.io import wavfile
from faster_whisper import WhisperModel
import spotipy
from spotipy.oauth2 import SpotifyOAuth
import pyautogui
from datetime import datetime
import requests
import xml.etree.ElementTree as ET
import random
import asyncio
import edge_tts
os.environ['PYGAME_HIDE_SUPPORT_PROMPT'] = "hide"
import pygame

from config import *

# Variáveis de estado interno
timestamps_palmas = []
historico_ruidos = []
esta_gravando = False
esta_processando = False
esta_falando = False
esta_tocando_intro = False
fala_lock = threading.Lock()
fala_count = 0

pygame.mixer.init()

# --- 1. UTILITÁRIOS DE SOM E STRINGS ---
def emitir_bip(frequencia=800, duracao=0.15):
    """Gera um tom senoidal limpo para sinalizar a escuta do microfone."""
    try:
        t = np.linspace(0, duracao, int(TAXA_AMOSTRAGEM * duracao), False)
        tom = np.sin(frequencia * t * 2 * np.pi)
        sd.play(tom, TAXA_AMOSTRAGEM)
        sd.wait()
    except Exception:
        pass

def alterar_volume_windows(comando_volume):
    hwnd = ctypes.windll.user32.GetForegroundWindow()
    if comando_volume == "subir":
        for _ in range(3):
            ctypes.windll.user32.SendMessageW(hwnd, WM_APPCOMMAND, 0, APPCOMMAND_VOLUME_UP << 16)
    elif comando_volume == "baixar":
        for _ in range(3):
            ctypes.windll.user32.SendMessageW(hwnd, WM_APPCOMMAND, 0, APPCOMMAND_VOLUME_DOWN << 16)
    elif comando_volume == "mutar":
        ctypes.windll.user32.SendMessageW(hwnd, WM_APPCOMMAND, 0, APPCOMMAND_VOLUME_MUTE << 16)

def falar(texto):
    """Faz o ZECA falar de forma assíncrona e segura."""
    global esta_falando, fala_count
    fala_count += 1
    esta_falando = True
    print(f"🤖 [ZECA Voz]: {texto}")
    def rodar_fala():
        global esta_falando, fala_count
        with fala_lock:
            try:
                # Gera o arquivo de áudio com a voz neural da Microsoft
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                # Voz masculina: "pt-BR-AntonioNeural" | Voz feminina: "pt-BR-FranciscaNeural"
                comunicado = edge_tts.Communicate(texto, "pt-BR-AntonioNeural", rate="+0%") # 0% é a velocidade normal. Mude para +10% ou -10% se quiser
                arquivo_temp = "zeca_fala.mp3"
                loop.run_until_complete(comunicado.save(arquivo_temp))
                
                # Reproduz o áudio com qualidade original
                pygame.mixer.music.load(arquivo_temp)
                pygame.mixer.music.play()
                
                while pygame.mixer.music.get_busy():
                    time.sleep(0.1)
                    
                pygame.mixer.music.unload()
            except Exception as e:
                print(f"⚠️ Erro no motor de voz neural: {e}")
        
        fala_count -= 1
        if fala_count == 0:
            time.sleep(0.2) # Pausa reduzida para o ZECA ouvir mais rápido
            if fala_count == 0:
                esta_falando = False
    threading.Thread(target=rodar_fala).start()

def remover_acentos(texto):
    return "".join(c for c in unicodedata.normalize('NFD', texto) if unicodedata.category(c) != 'Mn')

def capturar_fala_direta(prompt_personalizado=""):
    """Grava o microfone focado na resposta do usuário e filtra o áudio inicial."""
    print("\n🎙️ [ZECA] Aguardando sua resposta...")
    emitir_bip(800, 0.12)  
    audio_gravado = []
    silencio_acumulado = 0.0
    tempo_sem_falar = 0.0
    comecou_falar = False
    bloco_duracao = TAMANHO_BLOCO / TAXA_AMOSTRAGEM

    try:
        with sd.InputStream(channels=1, samplerate=TAXA_AMOSTRAGEM, blocksize=TAMANHO_BLOCO) as stream:
            # Limpa o buffer inicial por mais tempo para ignorar o eco da própria voz do ZECA
            for _ in range(25): 
                stream.read(TAMANHO_BLOCO)
            while True:
                dados, _ = stream.read(TAMANHO_BLOCO)
                audio_gravado.append(dados.copy())
                volume_atual = np.max(np.abs(dados))
                
                if volume_atual >= LIMIAR_VOZ:
                    comecou_falar = True
                    silencio_acumulado = 0.0
                else:
                    if comecou_falar:
                        silencio_acumulado += bloco_duracao
                    else:
                        tempo_sem_falar += bloco_duracao
                        
                if comecou_falar and silencio_acumulado >= TEMPO_SILENCIO_MAX: 
                    break
                if not comecou_falar and tempo_sem_falar >= 6.0:
                    break
                
                # SEGURANÇA: Limite de 15 segundos para evitar loop infinito
                if len(audio_gravado) > int(15.0 / bloco_duracao):
                    print("⚠️ Tempo limite de resposta atingido.")
                    break
    except Exception as e:
        print(f"⚠️ Erro no microfone interno: {e}")
        return ""

    emitir_bip(600, 0.1)  
    audio_completo = np.concatenate(audio_gravado, axis=0)
    wavfile.write("mensagem_temp.wav", TAXA_AMOSTRAGEM, audio_completo)
    try:
        prompt_msg = prompt_personalizado if prompt_personalizado else "Mensagem casual: E aí, tudo bem? Como você está? Já comeu? Sim, pode enviar."
        segmentos, info = modelo_ia.transcribe("mensagem_temp.wav", language="pt", initial_prompt=prompt_msg)
        
        texto_final = ""
        for s in segmentos:
            # Filtra segmentos onde a IA tem mais de 70% de certeza que é apenas ruído/silêncio
            if s.no_speech_prob < 0.7:
                texto_final += s.text
                
        texto_final = texto_final.strip()
        
        # Anti-alucinação: O Whisper Base costuma inventar essas frases no silêncio
        alucinacoes_comuns = ["o que a gente pode fazer", "obrigado por assistir", "inscreva-se", "deixe o like"]
        if any(a in texto_final.lower() for a in alucinacoes_comuns):
            return ""
            
        return texto_final
    except Exception as e:
        print(f"⚠️ Erro na transcrição direta: {e}")
        return ""

# --- 2. FUNÇÕES DE MEMÓRIA (MÓDULO 2) ---
def salvar_fato_memoria(texto_original, comando_limpo):
    try:
        fato = remover_acentos(texto_original.lower())
        for gatilho in ["guarde que", "guarda que", "lembre que", "lembra que", "grave que", "grava que", "zeca", "zeka", "seca"]:
            fato = re.sub(r'\b' + gatilho + r'\b', "", fato, flags=re.IGNORECASE)
        fato = fato.replace(",", "").replace(".", "").strip()
        
        if fato:
            with open(ARQUIVO_MEMORIA, "a", encoding="utf-8") as f:
                f.write(f"{comando_limpo}|{fato}\n")
            falar("Entendido, Lucas. Fato registrado na minha memória de longo prazo.")
        else:
            falar("Eu entendi o pedido de armazenamento, mas o fato não ficou claro.")
    except Exception as e:
        print(f"⚠️ Erro ao salvar memória: {e}")
        falar("Houve uma falha ao tentar acessar meus bancos de memória.")

def consultar_memoria(comando_limpo):
    try:
        if not os.path.exists(ARQUIVO_MEMORIA):
            falar("Meus bancos de dados de longo prazo estão vazios no momento.")
            return

        stopwords = {"zeca", "zeka", "seca", "quem", "o", "a", "os", "as", "que", "onde", "qual", "e", "foi", 
                     "de", "da", "do", "dos", "das", "um", "uma", "uns", "umas", 
                     "em", "no", "na", "nos", "nas", "para", "pro", "pra", "com", "por", "como", "sobre"}
        
        palavras_busca = [p for p in comando_limpo.split() if p not in stopwords]
        
        melhor_resposta = ""
        max_coincidencias = 0

        with open(ARQUIVO_MEMORIA, "r", encoding="utf-8") as f:
            for linha in f:
                if "|" in linha:
                    chave_armazenada, fato_armazenado = linha.strip().split("|")
                    chave_palavras = set(chave_armazenada.split())
                    coincidencias = sum(1 for p in palavras_busca if p in chave_palavras)
                    
                    if coincidencias > max_coincidencias:
                        max_coincidencias = coincidencias
                        melhor_resposta = fato_armazenado

        if max_coincidencias > 0 and melhor_resposta:
            falar(f"De acordo com meus registros: {melhor_resposta}")
        else:
            # --- INTERRUPÇÃO DO MÓDULO 3 (Se não achar o fato na memória, a IA responde de forma geral) ---
            responder_conversacao_inteligente(comando_limpo)
    except Exception as e:
        print(f"⚠️ Erro ao consultar memória: {e}")
        falar("Houve uma falha ao processar a varredura de dados.")

# --- 3. MÓDULO DE IA AVANÇADA (MÓDULO 3 - RESPOSTAS CONVERSACIONAIS) ---
def responder_conversacao_inteligente(comando_limpo):
    """Engine de IA conversacional local para interagir fora do script fixo."""
    frase = comando_limpo.replace("zeca", "").strip()
    
    # Respostas contextualizadas leves para simular uma IA Stark inteligente
    if any(p in frase for p in ["oi", "ola", "tudo bem", "como voce esta"]):
        falar("Estou operando com cem por cento de capacidade, Lucas. Tudo excelente por aqui.")
    elif any(p in frase for p in ["obrigado", "valeu", "show", "top"]):
        falar("Sempre às ordens, Lucas. É um prazer ajudar.")
    elif any(p in frase for p in ["quem e voce", "seu nome", "o que voce e"]):
        falar("Eu sou o ZECA, seu assistente virtual pessoal programado em Python.")
    else:
        falar(random.choice(["Deixe-me pensar um instante.", "Processando sua pergunta...", "Consultando minha rede neural."]))
        try:
            # Integração com o motor local Ollama
            url = "http://localhost:11434/api/generate"
            payload = {
                "model": "llama3.2",
                "prompt": f"Você é o ZECA, um assistente virtual inteligente e muito prestativo. Responda de forma curta, natural e em português do Brasil à seguinte pergunta/interação: '{frase}'",
                "stream": False
            }
            resposta_llm = requests.post(url, json=payload, timeout=30)
            if resposta_llm.status_code == 200:
                texto_llm = resposta_llm.json().get("response", "").strip()
                texto_llm = texto_llm.replace("*", "").replace("#", "") # Remove formatação markdown que a voz não sabe ler
                falar(texto_llm)
        except Exception as e:
            print(f"⚠️ Erro no LLM: {e}")
            falar("Minha rede neural está offline no momento. Certifique-se de que o motor Ollama está rodando no sistema.")

# --- COMPONENTES CLIMA E AGENDA ---
clima_cache = "Ainda estou sincronizando os dados do clima com o satélite."
previsao_chuva_hoje = False

def atualizar_clima_loop():
    """Motor invisível que atualiza o clima no fundo a cada 30 minutos"""
    global clima_cache, previsao_chuva_hoje
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
    
    # Tenta descobrir a localização atual dinamicamente pelo IP
    lat_atual, lon_atual = LATITUDE, LONGITUDE
    try:
        resposta_loc = requests.get("https://ipinfo.io/json", timeout=5)
        if resposta_loc.status_code == 200:
            dados_loc = resposta_loc.json()
            loc = dados_loc.get("loc", "")
            if loc and "," in loc:
                lat_atual, lon_atual = loc.split(",")
                print(f"📍 [ZECA] Localização dinâmica detectada: {dados_loc.get('city', 'Desconhecida')} ({lat_atual}, {lon_atual})")
    except Exception as e:
        print(f"⚠️ Não foi possível detectar a localização dinâmica. Usando coordenadas do config.py: {e}")
        
    url = f"https://api.open-meteo.com/v1/forecast?latitude={lat_atual}&longitude={lon_atual}&current_weather=true&daily=weathercode&timezone=auto"

    while True:
        try:
            resposta = requests.get(url, headers=headers, timeout=10)
            if resposta.status_code == 200:
                dados = resposta.json()
                clima_atual = dados.get("current_weather", {})
                temperatura = round(clima_atual.get("temperature", 25))
                codigo_clima = clima_atual.get("weathercode", 0)
                
                # Pega a previsão do dia inteiro e checa os códigos de chuva/tempestade
                codigo_diario = dados.get("daily", {}).get("weathercode", [0])[0]
                previsao_chuva_hoje = codigo_diario in [51, 53, 55, 61, 63, 65, 80, 81, 82, 95, 96, 99]
                
                if codigo_clima == 0: estado = "com ceu limpo"
                elif codigo_clima in [1, 2, 3]: estado = "parcialmente nublado"
                elif codigo_clima in [45, 48]: estado = "com neblina"
                elif codigo_clima in [51, 53, 55, 61, 63, 65]: estado = "com chuva"
                elif codigo_clima in [71, 73, 75, 77, 85, 86]: estado = "com neve"
                elif codigo_clima in [80, 81, 82]: estado = "com pancadas de chuva"
                elif codigo_clima in [95, 96, 99]: estado = "com risco de trovoada"
                else: estado = "estavel"
                
                clima_cache = f"Faz {temperatura} graus no momento e o tempo esta {estado}."
                time.sleep(1800) # Se deu certo, dorme por 30 minutos e só atualiza depois
                continue
        except Exception as e:
            print(f"🌪️ Erro no motor de clima em background: {e}")
        time.sleep(10) # Se não tem internet (ex: PC acabou de ligar), tenta de novo em 10 segundos

threading.Thread(target=atualizar_clima_loop, daemon=True).start()

def obter_previsao_tempo():
    global clima_cache
    return clima_cache

def obter_noticias(tema=None):
    """Busca as 3 principais manchetes do Google News Brasil via RSS. Suporta busca por temas."""
    try:
        if tema:
            tema_url = tema.replace(" ", "+")
            url = f"https://news.google.com/rss/search?q={tema_url}&hl=pt-BR&gl=BR&ceid=BR:pt-419"
        else:
            url = "https://news.google.com/rss?hl=pt-BR&gl=BR&ceid=BR:pt-419"
            
        headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
        resposta = requests.get(url, headers=headers, timeout=5)
        if resposta.status_code == 200:
            root = ET.fromstring(resposta.content)
            noticias = []
            for item in root.findall('.//item')[:3]: # Pega apenas o Top 3
                titulo = item.find('title').text
                # Limpa o nome do jornal no final do título (ex: " - G1") para ficar limpo na voz
                titulo = titulo.rsplit(" - ", 1)[0] 
                noticias.append(titulo)
            if noticias:
                if tema:
                    texto = f"Aqui estão as principais notícias sobre {tema}: "
                else:
                    texto = "Aqui estão as principais manchetes de agora: "
                    
                ordinais = ["Primeira", "Segunda", "Terceira"]
                for i, noti in enumerate(noticias):
                    texto += f"{ordinais[i]}. {noti}. "
                return texto
    except Exception as e:
        print(f"⚠️ Erro ao buscar notícias: {e}")
    return "Desculpe, não consegui sintonizar com os portais de notícias no momento."

def contar_lembretes_hoje():
    try:
        if os.path.exists(ARQUIVO_LEMBRETES):
            data_hoje = datetime.now().strftime("%Y-%m-%d")
            contador = 0
            with open(ARQUIVO_LEMBRETES, "r", encoding="utf-8") as f:
                for linha in f:
                    if data_hoje in linha:
                        contador += 1
            return contador
    except Exception as e:
        print(f"⚠️ Erro ao ler agenda: {e}")
    return 0

def rotina_saudacao_cinema():
    try:
        caminho_absoluto = os.path.join(os.path.dirname(os.path.abspath(__file__)), MUSICA_INTRO)
        
        # 1. Toca a música PRIMEIRO para dar feedback imediato ao usuário
        if os.path.exists(caminho_absoluto):
            print("🎸 Disparando introdução de cinema (Oculta via SoundPlayer)...")
            def tocar_oculto():
                global esta_tocando_intro
                esta_tocando_intro = True
                subprocess.run(["powershell", "-c", f"(New-Object System.Media.SoundPlayer '{caminho_absoluto}').PlaySync()"], creationflags=0x08000000)
                esta_tocando_intro = False
            threading.Thread(target=tocar_oculto, daemon=True).start()
            
            time.sleep(0.5) # Dá meio segundo para o som iniciar
            
        # 2. Enquanto a música toca no fundo, buscamos o clima e lembretes ganhando tempo!
        total_lembretes = contar_lembretes_hoje()
        
        texto_agenda = "Você não tem nenhum compromisso agendado para hoje."
        if total_lembretes == 1:
            texto_agenda = "Você possui 1 lembrete agendado para hoje."
        elif total_lembretes > 1:
            texto_agenda = f"Você possui {total_lembretes} lembretes agendados para hoje."

        alerta_chuva = " Ah, e um aviso importante: a previsão aponta chuva para hoje, não esqueça o guarda-chuva." if previsao_chuva_hoje else ""

        if os.path.exists(caminho_absoluto):
            falar(f"Olá, Lucas! Um novo dia para nós. {texto_agenda}{alerta_chuva} O que temos para hoje?")
            time.sleep(0.5)
            while esta_falando:
                time.sleep(0.2)
        else:
            falar(f"Olá, Lucas! Um novo dia para nós. {texto_agenda}{alerta_chuva} O que temos para hoje?")
    except Exception as e:
        print(f"⚠️ Erro ao processar áudio de cinema: {e}")
        falar("Ola, Lucas! Um novo dia para hoje?")
        
def verificar_saudacao_diaria():
    data_hoje = datetime.now().strftime("%Y-%m-%d")
    if not os.path.exists(ARQUIVO_HISTORICO_DIARIO):
        with open(ARQUIVO_HISTORICO_DIARIO, "w", encoding="utf-8") as f:
            f.write(data_hoje)
        rotina_saudacao_cinema()
        return True
    with open(ARQUIVO_HISTORICO_DIARIO, "r", encoding="utf-8") as f:
        ultima_data = f.read().strip()
    if ultima_data != data_hoje:
        with open(ARQUIVO_HISTORICO_DIARIO, "w", encoding="utf-8") as f:
            f.write(data_hoje)
        rotina_saudacao_cinema()
        return True
    return False

def monitorar_lembretes_loop():
    print("⏰ Monitor de Lembretes avançado ativo e rodando.")
    while True:
        try:
            if os.path.exists(ARQUIVO_LEMBRETES):
                momento_atual = datetime.now().strftime("%Y-%m-%d %H:%M")
                lembretes_mantidos = []
                disparou = False
                tarefa_disparada = ""

                with open(ARQUIVO_LEMBRETES, "r", encoding="utf-8") as f:
                    linhas = f.readlines()

                for linha in linhas:
                    if linha.strip():
                        partes = linha.strip().split("|")
                        if len(partes) == 2:
                            data_hora_tarefa, descricao = partes
                            if data_hora_tarefa <= momento_atual and not disparou:
                                disparou = True
                                tarefa_disparada = descricao
                            else:
                                lembretes_mantidos.append(linha)
                        else:
                            lembretes_mantidos.append(linha)

                if disparou:
                    with open(ARQUIVO_LEMBRETES, "w", encoding="utf-8") as f:
                        f.writelines(lembretes_mantidos)
                    emitir_bip(1000, 0.2)
                    time.sleep(0.1)
                    emitir_bip(1000, 0.2)
                    falar(f"Atencao Lucas, lembrete importante: {tarefa_disparada}")
        except Exception as e:
            print(f"⚠️ Erro no monitor de lembretes: {e}")
        time.sleep(15)

threading.Thread(target=monitorar_lembretes_loop, daemon=True).start()

# --- INICIALIZAÇÃO DA IA LOCAL ---
print("🤖 Carregando modelo de linguagem local (Whisper Base)...")
modelo_ia = WhisperModel("base", device="cpu", compute_type="int8")

print("🎵 Conectando ao serviço oficial do Spotify...")
escopo = "user-modify-playback-state user-read-playback-state"
sp = spotipy.Spotify(auth_manager=SpotifyOAuth(
    client_id=SPOTIPY_CLIENT_ID,
    client_secret=SPOTIPY_CLIENT_SECRET,
    redirect_uri=SPOTIPY_REDIRECT_URI,
    scope=escopo
))

print("✅ ZECA Pronto, configurado e com voz ativa!")

# --- 4. MOTOR PRINCIPAL DE INTERPRETAÇÃO DE TEXTO ---
def processar_comando_texto(texto_original):
    comando = remover_acentos(texto_original.lower().replace(".", "").replace("-", "").replace(",", "").replace("?", "").replace("  ", " ").strip())
    comando = comando.replace("jarvis", "zeca").replace("javis", "zeca").replace("javas", "zeca").replace("charves", "zeca").replace("chaves", "zeca").replace("zeka", "zeca").replace("seca", "zeca")
    
    if "de um ar assadraco" in comando or "ar assadraco" in comando:
        comando = comando.replace("de um ar assadraco", "gilmara cedraz").replace("ar assadraco", "gilmara cedraz")
        
    print(f"🔮 Interpretando comando limpo: '{comando}'")

    # --- GRAVAÇÃO DE MEMÓRIA (MÓDULO 2 - ATUALIZADO COM EXPR. DE POSSESSIVOS) ---
    if any(g in comando for g in ["guarde que", "guarda que", "lembre que", "lembra que", "grave que", "grava que"]) or comando.startswith(("meu ", "minha ")):
        if not any(l in comando for l in ["me lembre", "me lembra", "whatsapp", "agenda", "quem e", "qual e"]):
            salvar_fato_memoria(texto_original, comando)
            return

    # --- CONSULTA DE MEMÓRIA (MÓDULO 2) ---
    if any(g in comando for g in ["quem", "onde", "qual", "o que e", "o que foi"]) and not any(l in comando for l in ["youtube", "google", "spotify", "zeca"]):
        consultar_memoria(comando)

    # --- MOTOR DE CLIMA (MÓDULO 1) ---
    elif any(g in comando for g in ["vai chover", "chove hoje", "previsao de chuva", "preciso de guarda chuva", "preciso de guarda-chuva"]):
        if "sincronizando" in clima_cache:
            falar("Estou sincronizando com os satélites, pergunte novamente em alguns instantes.")
        elif previsao_chuva_hoje:
            falar("Sim, a previsão aponta chuva para hoje. É altamente recomendado levar um guarda-chuva.")
        else:
            falar("Pode ficar tranquilo. Não há previsão de chuva para hoje.")

    elif "previsao do tempo" in comando or "como esta o tempo" in comando or "como estar o tempo" in comando or "temperatura" in comando or "clima" in comando or "como esta o dia" in comando:
        texto_clima = obter_previsao_tempo()
        if "sincronizando" in texto_clima:
            falar("Estou com dificuldades para conectar aos satélites de clima. Por favor, tente novamente em alguns instantes.")
        else:
            falar(texto_clima)

    # --- MOTOR DE NOTÍCIAS ---
    elif any(g in comando for g in ["noticia", "noticias", "manchete", "manchetes", "o que esta acontecendo"]):
        tema = None
        if " sobre " in comando:
            tema = comando.split(" sobre ")[-1].strip()
        elif "noticias de " in comando:
            tema = comando.split("noticias de ")[-1].strip()
        elif "noticia de " in comando:
            tema = comando.split("noticia de ")[-1].strip()
            
        if tema:
            falar(f"Buscando as notícias mais recentes sobre {tema}, só um instante.")
            texto_noticias = obter_noticias(tema)
        else:
            falar("Buscando as manchetes mais recentes, só um instante.")
            texto_noticias = obter_noticias()
            
        falar(texto_noticias)

    # --- ENGENHO INTELIGENTE DO YOUTUBE ---
    elif "youtube" in comando and " por " in comando:
        partes = comando.split(" por ")
        termo_busca = partes[-1].strip()
        if termo_busca:
            falar(f"Entendido. Buscando por {termo_busca} no YouTube.")
            termo_url = termo_busca.replace(" ", "+")
            webbrowser.open(f"https://www.youtube.com/results?search_query={termo_url}")

    elif "youtube" in comando or "viu tubi" in comando or "viutubi" in comando or "abrir o youtube" in comando:
        falar("Com certeza, Lucas. Abrindo o YouTube agora.")
        webbrowser.open("https://www.youtube.com")

    # --- ENGENHO INTELIGENTE DO GOOGLE ---
    elif "google" in comando:
        termo_busca = ""
        if " por " in comando:
            termo_busca = comando.split(" por ")[-1].strip()
        elif " no google" in comando:
            frase_limpa = comando.replace("zeca", "").replace("no google", "")
            for verbo in ["pesquise ", "pesquisa ", "busque ", "buscar ", "procura ", "procurar ", " e "]:
                frase_limpa = frase_limpa.replace(verbo, "")
            termo_busca = frase_limpa.strip()
            
        if termo_busca:
            falar(f"Entendido. Buscando por {termo_busca} no Google.")
            webbrowser.open(f"https://www.google.com/search?q={termo_busca}")
        else:
            falar("Abrindo a pagina inicial do Google.")
            webbrowser.open("https://www.google.com")

    # --- LEITURA DE TEXTO SELECIONADO ---
    elif any(g in comando for g in ["leia o texto", "leia isso", "ler o texto", "ler a selecao", "leia a selecao", "ler isso"]):
        falar("Copiando o texto selecionado.")
        pyautogui.hotkey('ctrl', 'insert') # Usa Ctrl+Insert em vez de Ctrl+C para não matar o terminal
        time.sleep(0.3) # Dá um tempinho para o Windows registrar a cópia
        try:
            import pyperclip
            texto_selecionado = pyperclip.paste().strip()
            if texto_selecionado:
                # Limite de segurança para textos gigantes (lê cerca de 2 a 3 parágrafos)
                if len(texto_selecionado) > 2000:
                    texto_selecionado = texto_selecionado[:2000] + "... e o texto continua."
                falar(texto_selecionado)
            else:
                falar("Não encontrei nenhum texto selecionado na tela.")
        except ImportError:
            falar("O módulo de área de transferência não está instalado.")

    # --- ENGENHO MÁGICO DO WHATSAPP (LÓGICA CORRIGIDA E FLEXÍVEL) ---
    elif "whatsapp" in comando and "para" in comando:
        try:
            nome_final_whatsapp = None
            # 1. Procura ativamente na agenda para ignorar ruídos extras na frase
            for apelido, nome_real in AGENDA_CONTATOS.items():
                if re.search(r'\b' + apelido + r'\b', comando):
                    nome_final_whatsapp = nome_real
                    break
            
            # 2. Se for um contato que não está na agenda, pega apenas a primeira palavra após o "para"
            if not nome_final_whatsapp:
                partes_whats = comando.split(" para ")
                contato_ditado = partes_whats[-1].strip().split()[0] if partes_whats[-1].strip() else "Desconhecido"
                nome_final_whatsapp = contato_ditado.title()
            
            falar(f"Abrindo o WhatsApp de {nome_final_whatsapp}.")
            os.system("start whatsapp://"); time.sleep(3.5)
            pyautogui.hotkey('ctrl', 'f'); time.sleep(0.5); pyautogui.write(nome_final_whatsapp, interval=0.1); time.sleep(1.5)
            pyautogui.press('down'); pyautogui.press('enter'); time.sleep(0.5)
            
            frase_pergunta = "Qual a mensagem, Lucas?"
            while True:
                falar(frase_pergunta)
                while esta_falando:
                    time.sleep(0.1)
                time.sleep(0.3)
                corpo = capturar_fala_direta()
                print(f"📝 [Mensagem Capturada]: {corpo}")
                
                if not corpo:
                    falar("Não ouvi a mensagem. Cancelando envio para evitar erros.")
                    break
                    
                try:
                    import pyperclip
                    pyperclip.copy(corpo)
                    pyautogui.hotkey('ctrl', 'v')
                except ImportError:
                    pyautogui.write(remover_acentos(corpo), interval=0.03)
                
                falar("Deseja confirmar o envio?")
                while esta_falando:
                    time.sleep(0.1)
                time.sleep(0.3)
                conf = remover_acentos(capturar_fala_direta().lower())
                
                # --- FILTRO ANTI-ECO (Ignora números como '14:18') ---
                if re.match(r'^[\d\,\.\:\s]+$', conf):
                    conf = ""
                
                # --- GATILHOS FLEXÍVEIS ---
                gatilhos_confirmar = ["enviar", "sim", "pode", "confirmar", "envia", "pode enviar", "sim pode", "confirmado", "vai"]
                gatilhos_corrigir = ["corrigir", "editar", "errado", "mudar", "alterar", "coigir"]
                
                if any(x in conf for x in gatilhos_confirmar):
                    pyautogui.press('enter'); falar("Enviado."); break
                elif any(x in conf for x in gatilhos_corrigir):
                    pyautogui.hotkey('ctrl', 'a'); pyautogui.press('backspace'); falar("Pode ditar a nova mensagem."); continue
                else:
                    # Plano B: se não entendeu, pergunta de novo
                    falar("Não entendi bem. Enviar ou apagar?")
                    while esta_falando:
                        time.sleep(0.1)
                    time.sleep(0.3)
                    conf_retry = remover_acentos(capturar_fala_direta().lower())
                    if any(x in conf_retry for x in gatilhos_confirmar):
                        pyautogui.press('enter'); falar("Enviado."); break
                    else:
                        pyautogui.hotkey('ctrl', 'a'); pyautogui.press('backspace'); falar("Cancelado."); break
        except Exception as e: print(f"❌ Erro WhatsApp: {e}")

    # --- ROTINAS E MACROS ---
    elif any(g in comando for g in ["modo dev", "modo desenvolvedor", "modo de desenvolvimento"]):
        falar("Ativando o Modo Desenvolvedor, Lucas. Preparando o seu ambiente de trabalho.")
        
        # Abre os aplicativos sequencialmente
        os.system("code .")
        time.sleep(0.5)
        os.system("start chrome")
        time.sleep(0.5)
        os.system("start whatsapp://")
        time.sleep(1.0)
        
        # Configura o Spotify para tocar a Playlist
        try:
            print("🔍 [SPOTIFY] Buscando playlist de Lo-Fi/Trap para o Modo DEV...")
            resultados = sp.search(q="lofi trap", limit=1, type='playlist')
            if resultados['playlists']['items']:
                playlist_uri = resultados['playlists']['items'][0]['uri']
                print(f"🎵 [SPOTIFY] Iniciando playlist: {resultados['playlists']['items'][0]['name']}")
                
                devices = sp.devices()
                device_id = None
                
                if devices and devices.get('devices'):
                    for d in devices['devices']:
                        if d['is_active']:
                            device_id = d['id']
                            break
                            
                if not device_id:
                    os.system("start spotify")
                    time.sleep(4) # Espera o Spotify carregar no Windows
                    devices = sp.devices()
                    if devices and devices.get('devices'):
                        device_id = devices['devices'][0]['id']
                        
                if device_id:
                    sp.start_playback(device_id=device_id, context_uri=playlist_uri)
                else:
                    sp.start_playback(context_uri=playlist_uri)
        except Exception as e:
            print(f"❌ Erro ao iniciar música no Modo DEV: {e}")

    # --- RESTANTE DOS APLICATIVOS ---
    elif "abrir o vs code" in comando or "abrir vs code" in comando or "abrir codigo" in comando:
        falar("Inicializando o ambiente de desenvolvimento, Lucas.")
        os.system("code .")

    elif "abrir calculadora" in comando or "calculadora" in comando or "abri calculadora" in comando:
        falar("Abrindo a calculadora do sistema.")
        os.system("start calc")

    elif "configuracoes" in comando or "configuracao" in comando or "painel" in comando:
        falar("Abrindo as configuracoes do sistema, Lucas.")
        os.system("start ms-settings:")

    elif "abrir o discord" in comando or "abrir discord" in comando or "discord" in comando:
        falar("Conectando aos servidores do Discord.")
        os.system("start discord")

    elif "abrir a steam" in comando or "abrir steam" in comando or "steam" in comando:
        falar("Inicializando a Steam. Hora dos jogos, Lucas.")
        os.system("start steam")

    elif "abrir netflix" in comando or "netflix" in comando:
        falar("Abrindo a Netflix. Aproveite a sessao.")
        webbrowser.open("https://www.netflix.com")

    elif "gerenciador de tarefas" in comando or "gerenciador" in comando:
        falar("Conferindo os processos do sistema.")
        os.system("start taskmgr")

    elif "fechar o navegador" in comando or "fechar navegador" in comando or "fechar o chrome" in comando:
        falar("Fechando todas as abas abertas do navegador.")
        os.system("taskkill /f /im chrome.exe >nul 2>&1")
        os.system("taskkill /f /im msedge.exe >nul 2>&1")

    # --- CONTROLE DE HARDWARE ---
    elif "aumentar o volume" in comando or "aumentar volume" in comando or "subir o som" in comando:
        falar("Subindo o volume do sistema.")
        alterar_volume_windows("subir")

    elif "diminuir o volume" in comando or "diminuir volume" in comando or "abaixar o som" in comando:
        falar("Abaixando o volume do sistema.")
        alterar_volume_windows("baixar")

    elif "mutar o computador" in comando or "mutar o som" in comando or "tirar o som" in comando:
        falar("Alternando o mudo do Windows.")
        alterar_volume_windows("mutar")

    # --- MÓDULO: AGENDA INTELIGENTE DATA + HORA ---
    elif any(g in comando for g in ["lembrar", "lembre", "lembra", "lembro", "agendar", "agenda"]):
        try:
            agora_sistema = datetime.now()
            ano_alvo = agora_sistema.year
            mes_alvo = agora_sistema.month
            dia_alvo = agora_sistema.day
            
            match_data = re.search(r'dia\s+(\d+)\s+de\s+([a-z]+)', comando)
            if match_data:
                dia_alvo = int(match_data.group(1))
                mes_palavra = match_data.group(2)
                if mes_palavra in MESES_MAPA:
                    mes_alvo = MESES_MAPA[mes_palavra]
            else:
                match_apenas_dia = re.search(r'dia\s+(\d+)\b', comando)
                if match_apenas_dia:
                    dia_alvo = int(match_apenas_dia.group(1))

            hora = None
            minuto = 0
            
            # Busca inteligente de horário (Ignora números no meio da tarefa)
            match_hora = re.search(r'(?:as|às|nas|nos|para as|para às|pras)\s+(\d{1,2})(?:[\:he\s]+(\d{2}))?', comando)
            if not match_hora:
                match_hora = re.search(r'(\d{1,2})\s*(?:horas|hora|h|:|e)\s*(\d{2})?', comando)
                
            if match_hora:
                hora = int(match_hora.group(1))
                if match_hora.group(2):
                    minuto = int(match_hora.group(2))
            else:
                # Fallback antigo para números soltos
                numeros_hora = re.findall(r'\d+', re.sub(r'dia\s+\d+(\s+de\s+[a-z]+)?', '', comando))
                if numeros_hora:
                    hora = int(numeros_hora[0])
                    minuto = int(numeros_hora[1]) if len(numeros_hora) >= 2 else 0
                    if len(numeros_hora) == 1 and len(numeros_hora[0]) == 4:
                        hora = int(numeros_hora[0][0:2])
                        minuto = int(numeros_hora[0][2:4])

            if hora is not None:
                data_hora_formatada = f"{ano_alvo}-{mes_alvo:02d}-{dia_alvo:02d} {hora:02d}:{minuto:02d}"
                data_falada = f"{dia_alvo:02d}/{mes_alvo:02d}"
                horario_falado = f"{hora:02d}:{minuto:02d}"
                
                tarefa = texto_original
                for gatilho in ["me lembre de", "me lembrar de", "me lembra de", "me lembro de", "lembrar de", "lembre de", "lembra de", "agendar", "agenda", "zeca", "zeka", "seca"]:
                    tarefa = re.sub(r'\b' + gatilho + r'\b', "", tarefa, flags=re.IGNORECASE)
                
                tarefa = re.sub(r'dia\s+\d+.*', '', tarefa, flags=re.IGNORECASE)
                tarefa = re.sub(r'(as|às|nas|nos)\s+\d+.*', '', tarefa, flags=re.IGNORECASE)
                tarefa = re.sub(r'\b\d+\s*(horas|hora|minutos|minuto).*', '', tarefa, flags=re.IGNORECASE)
                tarefa = re.sub(r'\d+[-:]\d+.*', '', tarefa, flags=re.IGNORECASE)
                tarefa = tarefa.replace(",", "").replace(".", "").strip()
                
                if not tarefa:
                    tarefa = "Compromisso agendado"

                with open(ARQUIVO_LEMBRETES, "a", encoding="utf-8") as f:
                    f.write(f"{data_hora_formatada}|{tarefa}\n")
                
                if dia_alvo == agora_sistema.day and mes_alvo == agora_sistema.month:
                    falar(f"Agendado, Lucas. Vou te lembrar de {tarefa} hoje as {horario_falado}.")
                else:
                    falar(f"Agendado para o futuro, Lucas. Vou te lembrar de {tarefa} no dia {data_falada} as {horario_falado}.")
            else:
                falar("Eu entendi o pedido, mas faltou me dizer o horario de forma clara.")
        except Exception as e:
            print(f"❌ Erro ao criar lembrete avancado: {e}")
            falar("Houve uma falha ao tentar registrar esse compromisso na agenda.")

    elif "tocar" in comando or "spotify" in comando:
        musica = ""
        if "tocar" in comando:
            musica = comando.split("tocar")[-1].strip()

        palavras_remover = ["e ", "a ", "o ", "de ", "em ", "para ", "um ", "uma ", "com "]
        for pr in palavras_remover:
            if musica.startswith(pr):
                musica = musica[len(pr):].strip()

        try:
            if musica:
                termo_busca = musica
                if " de " in musica or " do " in musica:
                    conector = " de " if " de " in musica else " do "
                    partes = musica.split(conector)
                    nome_faixa = partes[0].strip()
                    nome_artista = partes[1].strip()
                    termo_busca = f"track:{nome_faixa} artist:{nome_artista}"
                
                print(f"🔍 [SPOTIFY] Buscando com filtro avancado: '{termo_busca}'")
                resultados = sp.search(q=termo_busca, limit=1, type='track')
                
                if resultados['tracks']['items']:
                    track = resultados['tracks']['items'][0]
                    track_uri = track['uri']
                    print(f"🎵 [SPOTIFY] Encontrado: {track['name']} - {track['artists'][0]['name']}")
                    falar(f"Soltando o som de {track['name']}.")
                    try:
                        sp.start_playback(uris=[track_uri])
                    except spotipy.exceptions.SpotifyException:
                        devices = sp.devices()
                        if devices['devices']:
                            sp.start_playback(device_id=devices['devices'][0]['id'], uris=[track_uri])
                else:
                    print("❌ Nenhuma musica encontrada.")
                    falar("Não encontrei essa musica no Spotify.")
            else:
                playback = sp.current_playback()
                if playback and playback['is_playing']:
                    falar("Pausando a musica.")
                    sp.pause_playback()
                else:
                    falar("Iniciando a reproducao.")
                    sp.start_playback()
        except Exception as e:
            print(f"❌ Erro no Spotify: {e}")

    else:
        # --- EXECUÇÃO DO MÓDULO 3 (Se cair fora do script fixo, a IA assume o controle) ---
        responder_conversacao_inteligente(comando)

# --- 5. MOTOR DE ESCUTA CONTÍNUA (VOICE ACTIVATION) ---
def escutar_continuamente():
    global esta_processando, esta_falando, esta_tocando_intro
    
    print("\n>>> ZECA Online. Diga 'Zeca' para me chamar...")
    bloco_duracao = TAMANHO_BLOCO / TAXA_AMOSTRAGEM
    
    with sd.InputStream(channels=1, samplerate=TAXA_AMOSTRAGEM, blocksize=TAMANHO_BLOCO) as stream:
        while True:
            if esta_processando or esta_falando or esta_tocando_intro:
                time.sleep(0.1)
                continue
                
            try:
                dados, _ = stream.read(TAMANHO_BLOCO)
            except sd.PortAudioError:
                continue
                
            volume_atual = np.max(np.abs(dados))
            
            # Se ouvir uma voz (passou do LIMIAR_VOZ de 0.09)
            if volume_atual >= LIMIAR_VOZ:
                audio_gravado = [dados.copy()]
                silencio_acumulado = 0.0
                
                while True:
                    try:
                        dados, _ = stream.read(TAMANHO_BLOCO)
                    except sd.PortAudioError:
                        continue
                        
                    audio_gravado.append(dados.copy())
                    vol = np.max(np.abs(dados))
                    
                    if vol >= LIMIAR_VOZ:
                        silencio_acumulado = 0.0
                    else:
                        silencio_acumulado += bloco_duracao
                        
                    if silencio_acumulado >= TEMPO_SILENCIO_MAX:
                        break
                    if len(audio_gravado) > int(15.0 / bloco_duracao): 
                        break
                        
                esta_processando = True
                audio_completo = np.concatenate(audio_gravado, axis=0)
                wavfile.write(ARQUIVO_AUDIO, TAXA_AMOSTRAGEM, audio_completo)
                
                try:
                    prompt_ajuda = "Zeca, Zeka, Seca, Gilmara Cedraz, Manuela Cedraz, Veigh, Cjota, KayBlack, MC Davi, trap brasileiro, funk, Spotify, tocar música, YouTube, pesquisar no youtube por, Google, no google por, hardware, lembrar, agendar, horas, dia, volume, VS Code, fechar, configurações, Discord, Steam, WhatsApp, para, mae, irma, enviar mensagem no whatsapp para, Netflix, Gerenciador, enviar, cancelar, corrigir, coigir, editar, apagar, previsão do tempo, como está o tempo, guarde que, guarda que, lembre que, quem é, onde fica."
                    segmentos, info = modelo_ia.transcribe(ARQUIVO_AUDIO, language="pt", initial_prompt=prompt_ajuda)
                    
                    texto_final = ""
                    for s in segmentos:
                        if s.no_speech_prob < 0.7:
                            texto_final += s.text
                    texto_final = texto_final.strip()
                    
                    texto_teste_alucinacao = texto_final.replace(".", "").replace("?", "").replace(",", "").strip().lower()
                    if texto_teste_alucinacao and texto_teste_alucinacao in prompt_ajuda.lower():
                        texto_final = ""
                        
                    if texto_final:
                        texto_lower = texto_final.lower()
                        gatilhos_zeca = ["zeca", "zeka", "seca"]
                        # Verifica se o nome do Zeca foi falado na frase
                        foi_chamado = any(re.search(r'\b' + g + r'\b', texto_lower) for g in gatilhos_zeca)
                        
                        if foi_chamado:
                            print(f"\n🗣️ [VOCÊ]: {texto_final}")
                            
                            primeira_do_dia = verificar_saudacao_diaria()
                            if not primeira_do_dia:
                                comando_limpo_wake = texto_lower
                                for g in gatilhos_zeca:
                                    comando_limpo_wake = re.sub(r'\b' + g + r'\b', "", comando_limpo_wake)
                                    
                                saudacoes = ["bom dia", "boa tarde", "boa noite", "oi", "ola", "vc esta ai", "voce esta ai", "salve", "pode me ajudar", "fala", "fala tu", "fala ai", "eae", "e ai", "tarde", "dia", "noite", "opa", "tudo bem"]
                                texto_sem_pontuacao = remover_acentos(comando_limpo_wake.replace(".", "").replace(",", "").replace("?", "").replace("!", "").strip())
                                
                                # Se você falou SÓ o nome dele ou uma saudação simples
                                if not texto_sem_pontuacao or any(texto_sem_pontuacao == s for s in saudacoes):
                                    respostas_prontidao = ["Sim, Lucas?", "Estou ouvindo.", "Pois não?", "Diga.", "Às ordens.", "Pode falar.", "Olá! Como posso ajudar?"]
                                    falar(random.choice(respostas_prontidao))
                                    while esta_falando:
                                        time.sleep(0.1)
                                        
                                    comando_continuacao = capturar_fala_direta(prompt_ajuda)
                                    if comando_continuacao:
                                        print(f"🗣️ [VOCÊ]: {comando_continuacao}")
                                        processar_comando_texto(comando_continuacao)
                                    else:
                                        falar("Não ouvi nenhum comando. Cancelando.")
                                else:
                                    # Se você falou tudo de uma vez (ex: "Zeca, abrir o YouTube")
                                    processar_comando_texto(texto_final)
                except Exception as e:
                    print(f"❌ Erro na IA: {e}")
                    
                esta_processando = False

# --- LOOP PRINCIPAL ---
try:
    escutar_continuamente()
except KeyboardInterrupt:
    print("\nSistema ZECA encerrado.")