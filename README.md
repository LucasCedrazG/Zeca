# 🤖 Assistente Virtual ZECA

O **ZECA** é um assistente virtual pessoal desenvolvido em Python, inspirado no JARVIS. Ele utiliza reconhecimento de voz avançado, inteligência artificial local e diversas automações para facilitar o uso do computador no dia a dia.

## ✨ Funcionalidades

- **🗣️ Escuta e Fala Natural**: Utiliza `faster-whisper` para entender comandos de voz (mesmo offline) e `edge-tts` (Vozes Neurais da Microsoft) para respostas fluídas.
- **🧠 Memória de Longo Prazo**: É capaz de guardar e resgatar informações ditas a ele pelo usuário.
- **💬 IA Conversacional**: Integração com o motor local **Ollama** (Llama 3.2) para responder perguntas complexas e manter conversas fora dos scripts programados.
- **🎵 Integração com Spotify**: Busca, toca e pausa músicas e playlists na sua conta.
- **📱 Automação de WhatsApp**: Envia mensagens automáticas ditadas por voz para seus contatos.
- **🌦️ Clima e Notícias**: Busca previsão do tempo com base em geolocalização e lê as principais manchetes do Brasil via Google News.
- **⏰ Agenda Inteligente**: Marca lembretes usando dias e horários, e avisa o usuário quando o momento chegar.
- **💻 Controle do Sistema**: Controla volume, abre aplicativos (VS Code, Discord, Steam, etc.), lê textos selecionados e faz pesquisas no Google/YouTube.
- **👨‍💻 Modo Desenvolvedor**: Prepara seu ambiente de trabalho abrindo ferramentas e colocando uma playlist Lofi no Spotify.

## 🚀 Como Rodar o Projeto

### 1. Pré-requisitos
* Python 3.8+ instalado na máquina.
* Ter o Ollama instalado para rodar os modelos conversacionais localmente.
* Conta de Desenvolvedor no Spotify para obter as credenciais da API.

### 2. Instalação
Clone o repositório e instale as dependências:

```bash
git clone https://github.com/SeuUsuario/SeuRepositorio.git
cd SeuRepositorio
pip install -r requirements.txt
```

### 3. Configuração do Ambiente (`.env`)
Crie um arquivo chamado `.env` na raiz do projeto baseado no `.env.example`:

```env
SPOTIPY_CLIENT_ID=seu_client_id_aqui
SPOTIPY_CLIENT_SECRET=seu_client_secret_aqui
LATITUDE=-12.9711
LONGITUDE=-38.5108
```

### 4. Configuração da Agenda de Contatos
Crie um arquivo `contatos.json` na raiz do projeto com os contatos para a automação do WhatsApp:

```json
{
    "apelido": "Nome Real no WhatsApp",
<<<<<<< HEAD
    "mae": "Maria Silva"
=======
    "mae": "Nome da sua mãe no WhatsApp"
>>>>>>> fc8710251c1fb872561795aee871f6bce7a5086a
}
```

### 5. Executando o Motor de IA
Abra um terminal separado e certifique-se de que o motor de respostas conversacionais está rodando:
```bash
ollama run llama3.2
```

### 6. Iniciando o Assistente
Rode o script principal:
```bash
python detector_palmas.py
```
Pronto! Apenas diga **"Zeca"** para acordá-lo e falar o seu comando.

---

*Desenvolvido com ☕ e Python.*
