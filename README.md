#  TCP vs R-UDP — Transferência de Arquivos com Validação Cruzada

![Python](https://img.shields.io/badge/Python-3.10%2B-blue) ![Docker](https://img.shields.io/badge/Docker-Compose-2496ED)

> **Link Vídeo Youtube:** 
> **Link Repositório Github:**
> **Disciplina:** Redes de Computadores II — UFPI  
> **Aluno:** Pedro Henrique Silva Rodrigues
> **Matrícula:** 20249011446 
> **Implementação:** Cliente/Servidor para transferência de arquivos em **TCP** e **UDP Confiável (R-UDP)**  
> **Diferencial:** Cabeçalho de autenticação personalizado (`X-Custom-Auth`), simulação de rede com `tc`, benchmark automatizado e análise estatística com Pandas/Matplotlib

---

##  Sumário

- [1. O Problema](#1-o-problema)
- [2. Arquitetura do Projeto](#2-arquitetura-do-projeto)
- [3. Estrutura de Arquivos](#3-estrutura-de-arquivos)
- [4. Protocolo de Aplicação](#4-protocolo-de-aplicação)
  - [4.1 Cabeçalho X-Custom-Auth](#41-cabeçalho-x-custom-auth)
  - [4.2 Formato do Quadro (Frame)](#42-formato-do-quadro-frame)
  - [4.3 Tipos de Mensagem](#43-tipos-de-mensagem)
- [5. Modo TCP](#5-modo-tcp)
  - [5.1 Fluxo de Funcionamento](#51-fluxo-de-funcionamento)
  - [5.2 Lógica de Implementação](#52-lógica-de-implementação)
- [6. Modo R-UDP (UDP Confiável)](#6-modo-r-udp-udp-confiável)
  - [6.1 Fluxo de Funcionamento](#61-fluxo-de-funcionamento)
  - [6.2 Mecanismo Stop-and-Wait](#62-mecanismo-stop-and-wait)
  - [6.3 Timeout e Retransmissão](#63-timeout-e-retransmissão)
  - [6.4 Verificação de Integridade (CRC32)](#64-verificação-de-integridade-crc32)
- [7. Pré-requisitos](#7-pré-requisitos)
- [8. Configuração de Identificação (Obrigatório)](#8-configuração-de-identificação-obrigatório)
- [9. Como Rodar — Modo Docker (com Simulação de Rede)](#10-como-rodar--modo-docker-com-simulação-de-rede)
  - [9.1 Cenários de Rede (A, B, C)](#101-cenários-de-rede-a-b-c)
  - [9.2 Execução Manual no Docker](#102-execução-manual-no-docker)
  - [9.3 Benchmark Automatizado (10–30+ Rodadas)](#103-benchmark-automatizado-1030-rodadas)
- [10. Análise de Resultados](#11-análise-de-resultados)
  - [10.1 Estatísticas e Gráficos](#111-estatísticas-e-gráficos)
  - [10.2 Validação Cruzada com Wireshark/tcpdump](#112-validação-cruzada-com-wiresharktcpdump)

---

## 1. O Problema

O objetivo deste trabalho é **implementar e comparar dois sistemas de transferência de arquivos**:

| Modo | Transporte | Característica |
|------|-----------|----------------|
| **TCP** | TCP nativo | Confiabilidade garantida pelo próprio protocolo TCP (controle de fluxo, controle de erros, entrega ordenada) |
| **R-UDP** | UDP + camada de confiabilidade | UDP puro, porém com uma **camada de confiabilidade implementada na aplicação**: números de sequência, ACKs, timeout, retransmissão e CRC32 |

Além da implementação, o projeto permite:

-  **Simular condições adversas de rede** (perda de pacotes e latência) usando `tc` no Docker
-  **Validar as métricas da aplicação** cruzando os logs com capturas de tráfego (Wireshark/tcpdump)
-  **Gerar análises comparativas** com tabelas de vazão (mínima, média, máxima, desvio padrão) e gráficos

---

## 2. Arquitetura do Projeto

```
┌─────────────────────────────────────────────────────────────────────┐
│                        DOCKER NETWORK                               │
│                                                                     │
│  ┌───────────────┐              ┌───────────────┐                   │
│  │   SERVIDOR    │              │   CLIENTE     │                   │
│  │  (receptor)   │◄────────────►│  (transmissor)│                   │
│  │               │   TCP ou     │               │                   │
│  │ ┌───────────┐ │    UDP       │ ┌───────────┐ │                   │
│  │ │ tcpdump   │ │              │ │    tc     │ │  ← Simula perda   │
│  │ │ (captura) │ │              │ │ (netem)   │ │     e latência    │
│  │ └───────────┘ │              │ └───────────┘ │                   │
│  └──────┬────────┘              └──────┬────────┘                   │
│         │                              │                            │
│         ▼                              ▼                            │
│  ┌──────────────┐              ┌──────────────┐                     │
│  │  /data/inbox │              │ /data/       │                     │
│  │ (arquivos    │              │ payload.bin  │                     │
│  │  recebidos)  │              │ (arquivo 1MB)│                     │
│  └──────────────┘              └──────────────┘                     │
│                                                                     │
└──────────────────────────────┬──────────────────────────────────────┘
                               │
                               ▼
                    ┌──────────────────────┐
                    │   results/ (volume)   │
                    │  ┌──────────────────┐ │
                    │  │ metrics_app.csv   │ │  ← Métricas da aplicação
                    │  │ pcaps/           │ │  ← Capturas .pcap
                    │  │ inbox/           │ │  ← Arquivos recebidos
                    │  │ plots/           │ │  ← Gráficos gerados
                    │  └──────────────────┘ │
                    └──────────────────────┘
```

### Fluxo de Dados (Visão Simplificada)

```
CLIENTE (sender)                          SERVIDOR (receiver)
     │                                        │
     │  ── 1. META (nome, tamanho) ──────────►│
     │  ◄─────── ACK(0) ───────────────────── │
     │                                        │
     │  ── 2. DATA(seq=1) ──────────►┐        │
     │  ◄──── ACK(1) ────────────────┘        │
     │  ── 3. DATA(seq=2) ──────────►┐        │
     │  ◄──── ACK(2) ────────────────┘        │
     │  ... (até arquivo completo)            │
     │                                        │
     │  ── N. FIN ───────────────────────────►│
     │  ◄──── ACK(N) ─────────────────────────│
```

> **Modo TCP:** Os passos são os mesmos (Stop-and-Way na camada de aplicação), mas o ACK é garantido pelo TCP subjacente.  
> **Modo R-UDP:** Se o ACK não chegar dentro do **timeout**, o cliente **retransmite** o pacote.

---

## 3. Estrutura de Arquivos

```
raiz/
│
├── src/                          # Código-fonte principal
│   ├── __init__.py               # Torna src/ um pacote Python
│   ├── server.py                 #  Servidor (ponto de entrada)
│   ├── client.py                 #  Cliente (ponto de entrada)
│   ├── tcp_mode.py               #  Lógica de transferência TCP
│   ├── rudp_mode.py              #  Lógica de transferência R-UDP (Stop-and-Wait)
│   ├── framing.py                #  Enquadramento de aplicação (empacota/desempacota)
│   ├── auth_header.py            #  Geração/verificação do X-Custom-Auth
│   ├── config.py                 #  Carrega MATRICULA e NOME_ALUNO (.env / variáveis)
│   └── metrics_log.py            #  Geração de CSV/JSONL com métricas
│
├── scripts/                      # Scripts auxiliares
│   ├── docker_client_run.sh      #  Aplica tc e executa cliente no container
│   ├── benchmark_loop.sh         #  Loop automatizado de benchmarks
│   ├── analyze_results.py        #  Estatísticas e gráficos (Pandas/Matplotlib)
│   └── pcap_to_csv.py            #  Converte .pcap → CSV (tshark)
│
├── results/                      # Resultados gerados (criado ao rodar)
│   ├── metrics_app.csv           # Métricas de todas as execuções
│   ├── inbox/                    # Arquivos recebidos pelo servidor
│   ├── pcaps/                    # Capturas .pcap (tcpdump)
│   └── plots/                    # Gráficos e CSVs de estatísticas
│       ├── stats_summary.csv     # Tabela completa (min/média/max/std)
│       ├── tcp/                  # Gráficos do TCP
│       ├── rudp/                 # Gráficos do R-UDP
│       └── compare/              # Gráficos comparativos TCP vs R-UDP
│
├── Dockerfile                    #  Imagem Ubuntu + Python + iproute2
├── docker-compose.yml            #  Orquestração servidor + cliente
├── requirements.txt              # Dependências Python
├── .env                          #  Suas credenciais (não versionado)
├── env.example                   #  Modelo para o .env
├── .gitignore                    # Arquivos ignorados pelo Git
└── README.md                     #  Este arquivo
```

### Descrição Detalhada de Cada Arquivo

####  `src/` — Lógica Central

| Arquivo | Responsabilidade |
|---------|-----------------|
| **`server.py`** | Parser de argumentos, inicializa logger e delega para `tcp_run_server()` ou `rudp_run_server()` |
| **`client.py`** | Parser de argumentos, gera arquivo de teste (se necessário), mede tempo/vazão e delega para `tcp_send_file()` ou `rudp_send_file()` |
| **`tcp_mode.py`** | Implementa a transferência sobre TCP com **Stop-and-Wait na camada de aplicação**: envia um quadro, espera ACK, envia o próximo. Usa `TcpStreamDecoder` para reconstruir quadros do stream TCP |
| **`rudp_mode.py`** | Implementa a transferência sobre UDP com **Stop-and-Wait real**: envia datagrama, aguarda ACK com `select()`, retransmite em caso de timeout. CRC32 validado no receptor |
| **`framing.py`** | Define o formato binário de cada quadro: linha de auth + cabeçalho binário (seq, tipo, tamanho, CRC32) + payload. Contém `TcpStreamDecoder` para delimitar quadros em um stream TCP |
| **`auth_header.py`** | Gera a linha `X-Custom-Auth: <SHA256(Matricula+Nome)>` em hexadecimal, visível no Wireshark |
| **`config.py`** | Carrega as variáveis `MATRICULA` e `NOME_ALUNO` do ambiente ou do arquivo `.env` |
| **`metrics_log.py`** | Funções utilitárias para escrever linhas em CSV e JSONL com as métricas de cada transferência |

####  `scripts/` — Automação

| Script | Função |
|--------|--------|
| **`docker_client_run.sh`** | Executado **dentro** do container cliente. Aplica as regras de `tc` na interface `eth0`, gera um payload aleatório de 1 MB e chama `python -m src.client` |
| **`benchmark_loop.sh`** | Orquestra múltiplas execuções: para cada modo (TCP/R-UDP) e cenário (A/B/C), executa N rodadas, capturando pcaps com tcpdump no servidor |
| **`analyze_results.py`** | Lê o CSV de métricas, calcula estatísticas (min/média/max/desvio padrão) agrupadas por cenário e modo, e gera gráficos comparativos |
| **`pcap_to_csv.py`** | Usa `tshark` para extrair de cada .pcap as métricas da rede (bytes no fio, duração, vazão) e junta em um CSV para validação cruzada |

---

## 4. Protocolo de Aplicação

### 4.1 Cabeçalho X-Custom-Auth

Toda mensagem trocada entre cliente e servidor **deve** conter uma linha de texto com o hash SHA-256 da matrícula concatenada com o nome do aluno.

```
X-Custom-Auth: a8f5f167f44f4964e6c998d13e2b7c7c8e2b...\r\n
```

**Por quê?** O valor é fixo por aluno e aparece **em texto claro** nos pacotes, permitindo identificar o tráfego no Wireshark com um filtro simples:

```
tcp contains "X-Custom-Auth"
# ou
udp contains "X-Custom-Auth"
```

**Verificação:** O receptor calcula o hash localmente e compara com o valor recebido. Se divergir, o pacote é rejeitado.

### 4.2 Formato do Quadro (Frame)

Cada quadro (frame) tem esta estrutura:

```
┌─────────────────────────────────────────────────────────────┐
│  X-Custom-Auth: <SHA256 hex>\r\n   ← Linha de autenticação  │
├─────────────────────────────────────────────────────────────┤
│  seq (4 bytes, uint32)                                      │
│  typ (1 byte, enum: DATA=0, ACK=1, FIN=2, META=3)         │
│  payload_len (2 bytes, uint16)                              │
│  crc32 (4 bytes, uint32)  ← CRC32 do payload               │
├─────────────────────────────────────────────────────────────┤
│  payload (payload_len bytes)                                │
└─────────────────────────────────────────────────────────────┘
```

**Total:** 11 bytes de cabeçalho binário + comprimento da linha de auth (+/- 70 bytes) + payload.

### 4.3 Tipos de Mensagem

| Tipo | Código | Finalidade |
|------|--------|-----------|
| **META** | 3 | Primeira mensagem: contém JSON com `{"name":"arquivo.txt","size":1024}` |
| **DATA** | 0 | Bloco de dados do arquivo |
| **ACK** | 1 | Confirmação de recebimento (contém o `seq` que está sendo confirmado) |
| **FIN** | 2 | Sinaliza fim da transmissão |

---

## 5. Modo TCP

### 5.1 Fluxo de Funcionamento

Mesmo usando TCP (que já é confiável), a aplicação implementa um **Stop-and-Wait na camada de aplicação**:

```
CLIENT                              SERVER
  │                                    │
  │──── META(seq=0, nome/tamanho) ────►│
  │◄─────────── ACK(seq=0) ───────────│
  │                                    │
  │──── DATA(seq=1, bloco 32KB) ─────►│
  │◄─────────── ACK(seq=1) ───────────│
  │──── DATA(seq=2, bloco 32KB) ─────►│
  │◄─────────── ACK(seq=2) ───────────│
  │           ...                      │
  │──── FIN(seq=N) ──────────────────►│
  │◄─────────── ACK(seq=N) ───────────│
```

### 5.2 Lógica de Implementação

- Usa `socket.SOCK_STREAM` (TCP)
- O cliente envia um quadro e **bloqueia** até receber o ACK correspondente
- O `TcpStreamDecoder` (em `framing.py`) faz a **delimitação dos quadros** no stream contínuo TCP — como TCP não preserva limites de mensagem, o decodificador lê byte a byte até encontrar a linha de auth + cabeçalho completo
- Como o TCP já garante entrega ordenada e sem perdas, as retransmissões nunca ocorrem na prática; o Stop-and-Wait serve apenas para controle de fluxo na camada de aplicação

---

## 6. Modo R-UDP (UDP Confiável)

### 6.1 Fluxo de Funcionamento

```
CLIENT                              SERVER
  │                                    │
  │──── META(seq=0, nome/tamanho) ────►│
  │◄─────────── ACK(seq=0) ────────────│
  │                                    │
  │──── DATA(seq=1, bloco ~1KB) ──────►│
  │          [timeout=2s]              │
  │◄─────────── ACK(seq=1) ────────────│
  │                                    │
  │──── DATA(seq=2, bloco ~1KB) ──────►│
  │           PACOTE PERDIDO!          │
  │           timeout expira           │
  │──── DATA(seq=2) ─── RETRANSMISSÃO ►│
  │◄─────────── ACK(seq=2) ────────────│
  │                                    │
  │           ...                      │
  │──── FIN(seq=N) ───────────────────►│
  │◄─────────── ACK(seq=N) ────────────│
```

### 6.2 Mecanismo Stop-and-Wait

O **Stop-and-Wait** é o algoritmo de controle de fluxo mais simples:

1. O transmissor envia **um** pacote
2. **Para** e espera a confirmação (ACK)
3. Só envia o **próximo** após receber o ACK do anterior

**Vantagem:** Simples de implementar.  
**Desvantagem:** Ineficiente em redes de alto latency (o "canal" fica ocioso durante o tempo de ida-e-volta).

### 6.3 Timeout e Retransmissão

- O cliente usa a chamada `select()` com timeout para aguardar o ACK
- Se o ACK não chegar dentro do prazo (padrão: **2 segundos**), o cliente **retransmite** o mesmo pacote
- O número máximo de retentativas é **1000** — após isso, a transferência falha com `TimeoutError`
- O servidor trata **duplicatas**: se receber um `seq` já confirmado, reenvia o ACK e descarta o dado

### 6.4 Verificação de Integridade (CRC32)

Cada payload tem seu CRC32 anexado no cabeçalho binário:

- **Transmissor:** calcula `zlib.crc32(payload)` antes de enviar
- **Receptor:** calcula o CRC32 do payload recebido e compara com o valor no cabeçalho
- Se divergir → pacote corrompido → **descartado** (o transmissor vai retransmitir por timeout)

---

## 7. Pré-requisitos

| Ferramenta | Versão Mínima | Para quê |
|-----------|--------------|----------|
| **Python** | 3.10+ | Executar cliente e servidor |
| **pip** | — | Instalar dependências |
| **Docker Desktop** (ou Docker Engine + Compose v2) | — | Cenários com `tc` (recomendado) |
| **Git** (opcional) | — | Clonar o repositório |
| **Wireshark / tshark** (opcional) | — | Validação cruzada com capturas |

> 💡 **Usuários Windows:** O caminho mais simples é usar o **WSL2** com Ubuntu ou o **Docker Desktop** com terminal bash integrado. Os comandos abaixo funcionam em Linux, macOS e WSL.

---

## 8. Configuração de Identificação (Obrigatório)

O protocolo exige que **cliente e servidor** tenham a mesma matrícula e nome para gerar o hash `X-Custom-Auth`.

### Via arquivo `.env` (recomendado)

Crie um arquivo `.env` na raiz do projeto (modelo em `env.example`):

```env
MATRICULA=2023123456
NOME_ALUNO=Seu Nome Completo
```

> O `.env` está no `.gitignore` e **não** vai para o Git.

### Via variável de ambiente (Linux/macOS/WSL)

```bash
export MATRICULA="2023123456"
export NOME_ALUNO="Seu Nome" ou
set -o allexport; source .env; set +o allexport
```

### Verificação

```bash
echo "$NOME_ALUNO"
echo "$MATRICULA"
# Saída esperada: ('2023123456', 'Seu Nome')
```

---

## 9. Como Rodar — Modo Docker (com Simulação de Rede)

### 9.1 Cenários de Rede (A, B, C)

Os cenários simulam diferentes condições de rede usando o comando `tc qdisc netem` dentro do container cliente:

| Cenário | Atraso (delay) | Perda de Pacotes | Comando `tc` |
|---------|---------------|-------------------|--------------|
| **A** | 10 ms | 0% | `delay 10ms loss 0%` |
| **B** | 50 ms | 5% | `delay 50ms loss 5%` |
| **C** | 100 ms | 10% | `delay 100ms loss 10%` |

### 9.2 Execução Manual no Docker

**Passo 1 — Suba o servidor:**

```bash
export MATRICULA="..." NOME_ALUNO="..."
export TRANSFER_MODE=tcp    # ou rudp
docker compose up --build server
```

**Passo 2 — Execute o cliente (em outro terminal):**

```bash
export MATRICULA="..." NOME_ALUNO="..."
export SCENARIO=B           # A, B ou C
export TRANSFER_MODE=tcp    # mesmo modo do servidor
export RUN_ID=1
docker compose run --rm client
```

O cliente:
1. Aplica as regras de `tc` na interface `eth0` (simulando o cenário escolhido)
2. Gera um payload aleatório de **1 MB**
3. Envia para o servidor
4. Registra as métricas em `/data/metrics_app.csv` (mapeado para `results/metrics_app.csv` no host)

### 9.3 Benchmark Automatizado (10–30+ Rodadas)

O script `scripts/benchmark_loop.sh` executa **N transferências** para cada combinação de modo (TCP/R-UDP) e cenário (A/B/C):

```bash
# 15 rodadas por combinação (total: 2 modos × 3 cenários × 15 = 90 execuções)
export MATRICULA="..." NOME_ALUNO="..."
./scripts/benchmark_loop.sh 15
```

**O que ele faz:**

```
Para cada MODO (tcp, rudp):
  1. Sobe o servidor no modo correto
  2. Instala tcpdump no servidor
  3. Para cada CENÁRIO (A, B, C):
     Para cada RODADA (1..N):
      a. Inicia tcpdump no servidor
      b. Executa o cliente (com tc e payload)
      c. Para o tcpdump → salva .pcap
  4. Derruba o servidor
```

**Personalização:**

```bash
# Apenas TCP, cenários A e C, 20 rodadas
export MODES="tcp"
export SCENARIOS="A C"
./scripts/benchmark_loop.sh 20
```

---

## 10. Análise de Resultados

### 10.1 Estatísticas e Gráficos

Após rodar o benchmark, use o script de análise:

```bash
python scripts/analyze_results.py results/metrics_app.csv
```

**O que ele gera:**

```
results/plots/
├── stats_summary.csv        # Tabela completa com todas as estatísticas
├── stats_throughput.csv     # Vazão: min, mean, max, std por cenário/modo
├── stats_duration.csv       # Tempo: min, mean, max, std por cenário/modo
├── tcp/
│   ├── throughput_tcp_lines.png   # Vazão TCP (4 painéis: min/média/max/std)
│   ├── duration_tcp_lines.png     # Tempo TCP
│   ├── throughput_tcp_mean.png    # Gráfico individual: vazão média TCP
│   └── ...
├── rudp/
│   ├── throughput_rudp_lines.png  # Vazão R-UDP
│   ├── duration_rudp_lines.png    # Tempo R-UDP
│   └── ...
└── compare/
    ├── throughput_mean_compare.png    # Comparação TCP vs R-UDP: vazão média
    ├── throughput_max_compare.png     # Comparação TCP vs R-UDP: vazão máxima
    ├── duration_std_compare.png       # Comparação TCP vs R-UDP: desvio padrão tempo
    └── ...
```

**Exemplo de tabela gerada:**

| scenario | mode | runs | throughput_min | throughput_mean | throughput_max | throughput_std |
|----------|------|------|---------------|----------------|---------------|---------------|
| A | tcp | 15 | 850.2 | 892.7 | 921.3 | 18.4 |
| A | rudp | 15 | 12.3 | 14.1 | 15.8 | 1.2 |
| B | tcp | 15 | 420.1 | 445.6 | 468.9 | 15.2 |
| B | rudp | 15 | 2.1 | 2.8 | 3.5 | 0.4 |
| C | tcp | 15 | 280.3 | 301.2 | 325.7 | 14.1 |
| C | rudp | 15 | 0.8 | 1.2 | 1.9 | 0.3 |

> 💡 Os valores acima são ilustrativos. Os resultados reais dependem do hardware, da configuração de rede e do cenário simulado.

### 10.2 Validação Cruzada com Wireshark/tcpdump

Para validar as métricas da aplicação, compare os dados do CSV com a captura de rede.

**Passo 1 — Capture durante a transferência**

Com o benchmark, os pcaps são salvos automaticamente em `results/pcaps/<modo>/<cenario>/`.

**Passo 2 — Filtre o tráfego no Wireshark**

```
tcp contains "X-Custom-Auth"   # para TCP
udp contains "X-Custom-Auth"   # para R-UDP
```

**Passo 3 — Compare as métricas**

| Métrica | No CSV (aplicação) | No Wireshark (rede) |
|---------|-------------------|---------------------|
| Duração | `duration_sec` | Diferença entre primeiro e último pacote |
| Volume | `bytes_app` (payload útil) | Soma dos `frame.len` (inclui cabeçalhos IP/TCP/UDP) |
| Vazão | `throughput_mbps` | Calculada a partir dos bytes no fio |

**Passo 4 — Gere CSV automático dos pcaps (requer tshark)**

```bash
python scripts/pcap_to_csv.py
# Gera: results/pcap_summary.csv
```

O script usa `tshark` para extrair de cada .pcap:
- Número de pacotes (direção cliente → servidor)
- Bytes totais no fio
- Duração da conversa
- Vazão na camada de rede

Com `pcap_summary.csv` e `metrics_app.csv`, é possível fazer a **validação cruzada** lado a lado no Pandas, Excel ou ferramenta de análise.

---

>  **UFPI — Campus Senador Helvídio Nunes de Barros**  
>  **Curso: Sistemas de Informação**  
>  **Disciplina: Redes de Computadores II**
