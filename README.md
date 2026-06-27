# Miniservidor Web HTTP/1.1 + DNS Local + TCP/R-UDP

![Python](https://img.shields.io/badge/Python-3.10%2B-blue) ![Docker](https://img.shields.io/badge/Docker-Compose-2496ED)

> **Link Vídeo Youtube:** [Vídeo](https://youtu.be/UiMdeLDJmEU) <br>
> **Link Repositório Github:** [Repositório](https://github.com/phsrod/Trabalho02-Redes02Master) <br>
> **Link Relatório:** [Relatório](https://www.overleaf.com/read/ftcckjzxfzqz#148068) <br>
> **Disciplina:** Redes de Computadores II — UFPI  <br>
> **Aluno:** Pedro Henrique Silva Rodrigues <br>
> **Matrícula:** 20249011446 <br>

Evolução do projeto de transferência de arquivos: um **Cliente Web** que resolve nomes via **DNS simplificado (UDP)**, depois faz **HTTP GET** ao **Servidor Web**, utilizando alternativamente **TCP nativo** ou **R-UDP** (camada de confiabilidade Stop-and-Wait implementada na aplicação).

O projeto inclui benchmark automatizado com simulação de perda e atraso via `tc netem`, além de scripts de análise que calculam vazão, duração e taxa de erro baseada em retransmissões.

---

## Descrição do problema

O trabalho consiste em implementar e comparar dois protocolos de transporte para transferência de arquivos HTTP em uma arquitetura cliente-servidor: o **TCP nativo** e um protocolo **R-UDP** (Stop-and-Wait) implementado na camada de aplicação.

O cliente deve resolver o nome do servidor via um **servidor DNS simplificado** (também implementado) antes de realizar a requisição HTTP GET. O servidor Web deve ser capaz de atender requisições tanto por TCP quanto por R-UDP.

O ambiente é executado em contêineres Docker, com o servidor Web submetido a diferentes condições de rede simuladas via `tc netem` (atraso e perda de pacotes). Um benchmark automatizado executa 10 rodadas para cada combinação de protocolo (TCP/R-UDP), cenário de rede (A/B/C) e tamanho de arquivo (100k/500k/1m), totalizando 180 execuções.

A partir das execuções, são extraídas métricas de:
- **Vazão** (Mbps)
- **Duração** da transferência (s)
- **Taxa de erro** baseada em retransmissões observadas

---

## Sumário

- [Arquitetura](#arquitetura)
- [Lógica de funcionamento](#lógica-de-funcionamento)
  - [Fluxo TCP](#fluxo-tcp)
  - [Fluxo R-UDP](#fluxo-r-udp)
- [Cenários de rede](#cenários-de-rede)
- [Estrutura do projeto](#estrutura-do-projeto)
- [Configuração](#configuração)
- [Benchmark automatizado](#benchmark-automatizado)
- [Análise dos resultados](#análise-dos-resultados)
- [Protocolos](#protocolos)
  - [DNS simplificado (UDP)](#dns-simplificado-udp)
  - [HTTP/1.1](#http11)
  - [TCP nativo](#tcp-nativo)
  - [R-UDP (Stop-and-Wait)](#r-udp-stop-and-wait)
- [Validação com Wireshark](#validação-com-wireshark)

---

## Arquitetura

```
┌─────────────────────────────────────────────────────┐
│                  CLIENTE                             │
│              (172.28.0.20)                           │
│                                                      │
│  1. Pergunta ao DNS: "Qual o IP de www.web.local?"  │
│     ─────────────────── UDP :53 ───────────────►     │
│     ◄─── "O IP é 172.28.0.10" ─────────────────     │
│                                                      │
│  2. Faz HTTP GET no servidor WEB:                    │
│     ──── TCP :8080 ou R-UDP :8080 ─────────────►    │
│     ◄─── HTTP/1.1 200 OK + arquivo ─────────────    │
│                                                      │
│  Gera: metrics_app.csv, transfers.log, pcaps/        │
└──────────────────────┬──────────────────────────────┘
                       │
                       │  rede Docker 172.28.0.0/16
                       │
         ┌─────────────┴─────────────┐
         ▼                           ▼
┌──────────────────┐  ┌───────────────────────────────┐
│   SERVIDOR DNS    │  │      SERVIDOR WEB              │
│   (172.28.0.2)    │  │      (172.28.0.10)             │
│                   │  │                                │
│  Zona hosts.txt:  │  │  tc netem delay + loss         │
│  www.web.local →  │  │  (Cenários A/B/C)              │
│  172.28.0.10      │  │                                │
│                   │  │  HTTP/1.1 via TCP ou R-UDP      │
│  Escuta UDP :53   │  │  Escuta porta :8080             │
└──────────────────┘  │  Serve arquivos de /app/www/    │
                       │  Gera: transfers.log            │
                       └───────────────────────────────┘
```

A arquitetura é composta por três contêineres independentes, cada um com uma função específica:

1. **Cliente** (172.28.0.20) — Inicia o processo resolvendo o nome `www.web.local` através de uma consulta DNS. Com o IP do servidor em mãos, realiza uma requisição HTTP GET para baixar um arquivo, podendo usar **TCP nativo** ou **R-UDP** como protocolo de transporte. Durante a execução, o cliente registra métricas de desempenho (duração, vazão, sucesso/erro) no arquivo CSV `metrics_app.csv`, eventos detalhados no `transfers.log` e captura todo o tráfego de rede com `tcpdump` para análise posterior.

2. **Servidor DNS** (172.28.0.2) — Servidor DNS simplificado que escuta na porta UDP 53. Mantém uma zona estática definida no arquivo `hosts.txt`, que mapeia o nome `www.web.local` para o IP `172.28.0.10`. Quando recebe uma consulta, responde com o IP correspondente.

3. **Servidor Web** (172.28.0.10) — Servidor HTTP/1.1 que escuta na porta 8080, capaz de atender requisições tanto por TCP quanto por R-UDP. É nele que o `tc qdisc netem` é aplicado para simular as condições de rede de cada cenário (atraso e perda de pacotes). Serve os arquivos do diretório `www/` e também registra eventos no `transfers.log`.

Todos os contêineres compartilham o volume `./results:/data`, que armazena CSVs de métricas, logs de transferência e capturas PCAP.

---

## Lógica de funcionamento

### Fluxo TCP

O TCP nativo gerencia a conexão, retransmissões e ordenação dos pacotes de forma transparente através do kernel do sistema operacional.

```
 CLIENTE (web_client.py)              SERVIDOR (web_server.py)
    │                                      │
    │  1. DNS resolve www.web.local        │
    │  ────────── UDP :53 ─────────────►   │
    │  ◄───────── UDP :53 ─────────────     │
    │                                      │
    │  2. socket.create_connection()       │
    │  ──── SYN ──────────────────────►    │  TCP handshake
    │  ◄─── SYN+ACK ───────────────────     │  (kernel gerencia)
    │  ──── ACK ──────────────────────►    │
    │                                      │
    │  3. conn.sendall(HTTP request)       │
    │  ──── GET /arquivo ─────────────►    │
    │                                      │
    │                          4. parse_request()
    │                          5. read_file_bytes()
    │                          6. build_response()
    │                                      │
    │              7. conn.sendall(resp)   │
    │  ◄─── HTTP/1.1 200 OK + body ──────  │
    │                                      │
    │  8. _recv_http_message()             │
    │     (recv em loop até Content-Length) │
    │  9. parse_response()                 │
    │  10. Retorna (duração, bytes, corpo) │
    │                                      │
    │  Fim: socket fechado automaticamente │
```

**Detalhamento:**
1. O cliente chama `socket.create_connection((host, 8080))`, que realiza o handshake TCP de 3 vias (SYN, SYN+ACK, ACK) gerido pelo kernel
2. Com a conexão estabelecida, o cliente envia a requisição HTTP com `conn.sendall(request)` — o kernel empacota os dados em segmentos TCP
3. O servidor aceita a conexão com `sock.accept()`, lê a requisição via `_recv_http_message()` e processa com `parse_request()`
4. O servidor lê o arquivo, monta a resposta HTTP e envia com `conn.sendall(payload)`
5. O cliente lê a resposta em loop com `conn.recv(65536)`, acumulando os dados até atingir o `Content-Length` do cabeçalho HTTP
6. Se um segmento TCP for perdido, o kernel do lado do servidor o retransmite automaticamente usando RTO (Retransmission Timeout) e SACK (Selective Acknowledgment) — tudo transparente para a aplicação

### Fluxo R-UDP

No R-UDP, a confiabilidade é implementada na própria aplicação através do mecanismo **Stop-and-Wait**: cada quadro é enviado, o remetente aguarda um ACK por 0,5s e, se não receber, retransmite o mesmo quadro (até 1000 tentativas).

```
 CLIENTE (http_rudp.py)                   SERVIDOR (http_rudp.py)
    │                                          │
    │  1. DNS resolve www.web.local            │
    │  ────────── UDP :53 ─────────────►       │
    │  ◄───────── UDP :53 ─────────────         │
    │                                          │
    │  2. _send_sw(seq=0, META, req HTTP)      │
    │  ──── [META seq=0] ─────────────────►    │
    │  ◄─── [ACK seq=0] ──────────────────     │
    │                                          │
    │                              3. parse_request()
    │                              4. read_file_bytes()
    │                                          │
    │              5. _send_sw(seq=1, META, hdrs)
    │  ◄─── [META seq=1] ──────────────────    │
    │  ──── [ACK seq=1] ─────────────────►    │
    │                                          │
    │    6. Para cada chunk de 1000 bytes:     │
    │       _send_sw(seq=N, DATA, chunk)       │
    │  ◄─── [DATA seq=N] ─────────────────    │
    │  ──── [ACK seq=N] ─────────────────►    │
    │         ⋮  (N = 2, 3, 4, ...)           │
    │                                          │
    │              7. _send_sw(seq=F, FIN)     │
    │  ◄─── [FIN seq=F] ──────────────────    │
    │  ──── [ACK seq=F] ─────────────────►    │
    │                                          │
    │  8. parse_response()                     │
    │  9. Retorna (duração, bytes, corpo)      │
    │                                          │

     Caso de perda (ex: ACK do servidor c/ perda de 5%):

    │                                          │
    │  ──── [META seq=0] ─────────────────►    │
    │                              ┌─ netem drop ─► (perdido)
    │  ──── [META seq=0] ─────────────────►    │  ← retransmissão
    │                              │ após 0,5s timeout
    │  ◄─── [ACK seq=0] ──────────────────     │
    │                                          │
```

**Detalhamento:**
1. O cliente cria um socket UDP e envia a requisição HTTP dentro de um quadro **META** (seq=0) através da função `_send_sw()`
2. `_send_sw()`: (a) empacota o quadro via `pack_frame()` com autenticação, seq, tipo, CRC32; (b) envia com `sock.sendto()`; (c) aguarda ACK por 0,5s via `select()`; (d) se timeout, retransmite (até 1000x), registrando cada retransmissão no `transfers.log`
3. O servidor recebe o META via `_recv_sw()` — que valida CRC32 e autenticação; se o quadro for inválido, é ignorado (e o cliente retransmitirá por timeout)
4. O servidor envia a resposta: primeiro um **META** (seq=1) com os cabeçalhos HTTP, depois N quadros **DATA** (seq=2, 3, ...) com o corpo em chunks de 1000 bytes, e por fim um **FIN** para finalizar
5. O cliente confirma cada quadro recebido com um **ACK**; se receber um quadro duplicado (por exemplo, se o ACK foi perdido e o servidor retransmitiu), o cliente reenvia o ACK e descarta o dado duplicado
6. A função `_recv_sw()` no cliente trata quadros fora de ordem: se receber um quadro com seq anterior ao esperado, envia o ACK novamente (evita que o servidor fique retransmitindo indefinidamente)
7. Ao receber o **FIN**, o cliente monta o corpo HTTP completo a partir dos fragmentos, parseia a resposta e retorna

---

## Cenários de rede

O `tc qdisc netem` é aplicado na interface de rede do **servidor Web**, simulando diferentes condições de enlace:

| Cenário | Delay (ms) | Perda de pacotes |
|:-------:|:----------:|:----------------:|
| **A** | 10 | 0% |
| **B** | 50 | 5% |
| **C** | 100 | 10% |

---

## Estrutura do projeto

Abaixo, a árvore completa do diretório com todos os arquivos e suas respectivas descrições:

```
raiz/
│
├── .env                           # Variáveis de ambiente (MATRICULA, NOME_ALUNO)
├── .env.example                   # Modelo para o arquivo .env
├── .gitattributes                 # Configuração de atributos Git
├── .gitignore                     # Arquivos ignorados pelo Git
├── docker-compose.yml             # Orquestração de contêineres (dns, web, client)
├── Dockerfile                     # Imagem Python 3.10 com código e scripts
├── hosts.txt                      # Zona DNS estática (www.web.local → 172.28.0.10)
├── README.md                      # Documentação do projeto
├── requirements.txt               # Dependências Python (pandas, matplotlib, numpy)
│
├── docs/                          # Documentos complementares
│   ├── Capturas de Tela (X-CUSTOM-AUTH)/       # Capturas de tela que provam o X-CUSTOM-AUTH
│   ├── Segundo Trabalho - 3ª Avaliac&#807;a&#771;o.pdf   # Documento com especificações do trabalho
│   └── Relatório___2º_Trabalho__RC2_.pdf       # Relatório template SBC
│
├── results/                       # Resultados das execuções (CSVs, PCAPs, gráficos)
│   ├── transfers.log              # Arquivo de logs
│   ├── pcap_summary.csv           # Métricas de todas as execuções (wireshark)
│   ├── metrics_app.csv            # Métricas de todas as execuções (aplicação)
│   ├── pcaps/                     # Capturas .pcap (tcpdump)
│   └── plots/                     # Gráficos e CSVs de estatísticas
│       └── compare/               # Gráficos comparativos TCP vs R-UDP
│
├── scripts/                       # Scripts de automação e análise
│   ├── __init__.py                # Torna scripts/ um pacote Python
│   ├── analyze_results.py         # Estatísticas e gráficos (Pandas/Matplotlib)
│   ├── benchmark_loop.sh          # Benchmark automatizado (180 execuções)
│   ├── calculate_error_rate.py    # Taxa de erro baseada em retransmissões
│   ├── docker_client_run.sh       # Entry point do contêiner cliente
│   ├── generate_www_files.sh      # Geração de arquivos de teste (100k/500k/1m)
│   └── pcap_to_csv.py             # Extração de métricas dos PCAPs (tshark)
│
├── src/                           # Código-fonte principal
│   ├── __init__.py                # Torna src/ um pacote Python
│   ├── auth_header.py             # Geração/verificação do X-Custom-Auth (SHA256)
│   ├── client.py                  # Entry point legado (redireciona para web_client.py)
│   ├── config.py                  # Carrega variáveis de ambiente do .env
│   ├── dns_client.py              # Cliente DNS com timeout e retransmissão (UDP)
│   ├── dns_protocol.py            # Formato binário do DNS simplificado
│   ├── dns_server.py              # Servidor DNS (escuta em UDP :53)
│   ├── framing.py                 # Enquadramento R-UDP (META/DATA/ACK/FIN, CRC32)
│   ├── http_common.py             # Funções HTTP compartilhadas (parser, auth, leitura)
│   ├── http_rudp.py               # GET HTTP sobre R-UDP (Stop-and-Wait)
│   ├── http_tcp.py                # GET HTTP sobre TCP nativo
│   ├── metrics_log.py             # Registro de métricas em CSV
│   ├── server.py                  # Entry point legado (redireciona para web_server.py)
│   ├── web_client.py              # Ponto de entrada do cliente Web (DNS + HTTP)
│   └── web_server.py              # Ponto de entrada do servidor Web (:8080)
│
└── www/                           # Document root do servidor Web
    └── index.html                 # Página inicial
```

### `src/` — Lógica central

| Arquivo | Função / Responsabilidade |
|---------|---------------------------|
| `dns_protocol.py` | Define o formato binário do DNS simplificado: empacota/desempacota consultas (ID, nome) e respostas (ID, nome, IPv4) |
| `dns_server.py` | Servidor DNS que escuta em UDP :53, consulta o `hosts.txt` e responde com o IP mapeado |
| `dns_client.py` | Cliente DNS que envia consulta UDP, implementa timeout e retransmissão na aplicação (até 5 tentativas) |
| `http_common.py` | Funções compartilhadas entre TCP e R-UDP: parser de requisição/resposta HTTP/1.1, geração do cabeçalho `X-Custom-Auth`, leitura de arquivos do diretório `www/` |
| `http_tcp.py` | Implementa o GET HTTP sobre TCP nativo (`socket.create_connection`); recebe a resposta completa via `recv()` até `Content-Length` |
| `http_rudp.py` | Implementa o GET HTTP sobre R-UDP (Stop-and-Wait); gerencia envio de quadros META/DATA/FIN, timeout de 0,5s e retransmissão (até 1000 tentativas) |
| `web_client.py` | Ponto de entrada do cliente: recebe argumentos (modo, domínio, cenário), resolve DNS via `dns_client`, executa HTTP GET via `http_tcp` ou `http_rudp`, e registra métricas no CSV |
| `web_server.py` | Ponto de entrada do servidor Web: escuta em :8080 no modo TCP ou R-UDP, processa requisições GET, aplica autenticação `X-Custom-Auth` e serve arquivos do `www/` |
| `framing.py` | Define o enquadramento R-UDP: constantes `MsgType` (META/DATA/ACK/FIN), empacotamento/desempacotamento com CRC32 e linha de autenticação |
| `auth_header.py` | Gera e verifica o cabeçalho `X-Custom-Auth: SHA256(Matrícula+Nome)` presente em cada quadro e nas mensagens HTTP |
| `metrics_log.py` | Funções para registro de métricas: `build_row()` monta o dicionário com campos (duração, vazão, sucesso, erro); `append_csv_row()` escreve no CSV |
| `config.py` | Carrega as variáveis de ambiente `MATRICULA` e `NOME_ALUNO` do arquivo `.env` |

### `scripts/` — Automação e análise

| Arquivo | Função / Responsabilidade |
|---------|---------------------------|
| `generate_www_files.sh` | Gera os arquivos de teste `test_100k.bin`, `test_500k.bin` e `test_1m.bin` com dados aleatórios no diretório `www/files/` |
| `docker_client_run.sh` | Script de entrada do contêiner cliente: lê variáveis de ambiente (SCENARIO, TRANSFER_MODE, FILE_SIZE) e invoca `web_client.py` com os parâmetros corretos |
| `benchmark_loop.sh` | Benchmark automatizado completo: itera por modos (tcp/rudp), cenários (A/B/C) e tamanhos (100k/500k/1m); aplica `tc netem`, inicia `tcpdump`, executa o cliente, coleta PCAPs e métricas |
| `analyze_results.py` | Gera estatísticas agregadas e gráficos comparativos (duração, vazão, taxa de erro) a partir do `metrics_app.csv`; aceita `--retransmission-csv` para incorporar a taxa de erro real nos gráficos |
| `calculate_error_rate.py` | Calcula a taxa de erro real baseada em retransmissões: TCP via `tshark` nos PCAPs, R-UDP via contagem de eventos `"retransmit"` no `transfers.log` |
| `pcap_to_csv.py` | Extrai métricas dos PCAPs (contagem de pacotes, bytes, duração, vazão) usando `tshark` e gera `results/pcap_summary.csv` |

### Demais arquivos

| Arquivo | Descrição |
|---------|-----------|
| `hosts.txt` | Zona DNS estática: mapeia `www.web.local → 172.28.0.10` |
| `www/` | Document root do servidor Web (index.html + arquivos de teste) |
| `docker-compose.yml` | Orquestração dos contêineres (dns, web, client) com rede 172.28.0.0/16 e volume compartilhado `./results:/data` |
| `Dockerfile` | Imagem Python 3.10 com o código-fonte e scripts |
| `requirements.txt` | Dependências Python (pandas, matplotlib, numpy) |
| `.env` | Variáveis de ambiente: `MATRICULA` e `NOME_ALUNO` |

---

## Configuração

Crie `.env` na raiz do projeto:

```env
MATRICULA=20249011446
NOME_ALUNO=Pedro Henrique Silva Rodrigues
```

---

## Benchmark automatizado

O experimento combina os seguintes parâmetros, totalizando 180 execuções:

| Parâmetro | Valores |
|-----------|---------|
| **Protocolos** | TCP e R-UDP |
| **Cenário A** | 10 ms de atraso, 0% de perda |
| **Cenário B** | 50 ms de atraso, 5% de perda |
| **Cenário C** | 100 ms de atraso, 10% de perda |
| **Arquivos** | 100 KB, 500 KB e 1 MB |

O script `benchmark_loop.sh` executa rodadas completas para todas as combinações:

```bash
export MATRICULA="..." NOME_ALUNO="..."
./scripts/benchmark_loop.sh 10    # 10 rodadas por combinação
```

O benchmark:
1. Sobe os contêineres DNS + Web no modo atual (TCP ou R-UDP)
2. Instala `tcpdump` no contêiner cliente
3. Para cada combinação (tamanho × cenário × run):
   - Aplica `tc netem` no servidor Web com delay e perda do cenário
   - Inicia `tcpdump` no cliente
   - Executa `web_client.py` que faz DNS + HTTP GET
   - Salva o PCAP e a métrica no CSV
4. Gera `results/metrics_app.csv` e `results/pcaps/`

---

## Análise dos resultados

### Taxa de erro via retransmissões

```bash
python scripts/calculate_error_rate.py --csv results/metrics_app.csv --transfers-log results/transfers.log --pcap-dir results/pcaps --out results/retransmission_rate.csv
```

### Métricas básicas e gráficos

```bash
python scripts/analyze_results.py results/metrics_app.csv --retransmission-csv results/retransmission_rate.csv
```

Gera em `results/plots/`:
- `compare/duration_combined.png` — duração média (TCP | R-UDP)
- `compare/throughput_mean_combined.png` — vazão média
- `compare/error_rate_combined.png` — taxa de erro
- `stats_summary.csv`, `stats_throughput.csv`, `stats_duration.csv`

---

## Protocolos

### DNS simplificado (UDP)

Formato binário próprio (não segue RFC 1035):

| Campo | Tamanho | Descrição |
|-------|:-------:|-----------|
| ID | 2B | Identificador único da consulta |
| name_len | 1B | Tamanho do nome DNS |
| name | variável | Nome DNS (ex: `www.web.local`) |
| IPv4 | 4B | *(resposta)* Endereço IP |

- Consulta: `ID | name_len | name`
- Resposta: `ID | name_len | name | IPv4`
- Zona estática em `hosts.txt`: `www.web.local 172.28.0.10`
- Cliente implementa **timeout e retransmissão** na aplicação (UDP não tem confiabilidade)

### HTTP/1.1

Requisição GET com cabeçalho de autenticação:

```
GET /arquivo HTTP/1.1
Host: www.web.local
X-Custom-Auth: SHA256(Matrícula+Nome)

```

Resposta:

```
HTTP/1.1 200 OK
Content-Type: application/octet-stream
Content-Length: 100000
X-Custom-Auth: SHA256(Matrícula+Nome)

[body]
```

### TCP nativo

`http_tcp.py` — Utiliza soquetes TCP do Python (`socket.create_connection`).

- Conexão padrão TCP com handshake de 3 vias
- Recebe a resposta HTTP completa via `recv()` até `Content-Length`
- Retransmissões gerenciadas pelo kernel do sistema operacional
- Beneficia-se de ACKs cumulativos, **SACK** (Selective Acknowledgment) e controle de congestão

### R-UDP (Stop-and-Wait)

`http_rudp.py` + `framing.py` — Camada de confiabilidade sobre UDP, reutilizada da avaliação anterior.

#### Quadros

| Tipo | Valor | Descrição |
|:----:|:-----:|-----------|
| META | 3 | Metadados da requisição/resposta HTTP |
| DATA | 0 | Fragmento do corpo da resposta (1000 bytes) |
| ACK | 1 | Confirmação de recebimento |
| FIN | 2 | Finalização da transferência |

#### Formato do quadro

```
X-Custom-Auth: <SHA256>\r\n     ← autenticação (82 bytes fixos)
seq (4B) | typ (1B) | plen (2B) | crc32 (4B) | payload
```

- `seq`: número de sequência (uint32)
- `typ`: tipo do quadro (META/DATA/ACK/FIN)
- `plen`: tamanho do payload (uint16)
- `crc32`: checksum CRC-32 do payload
- `payload`: dados do quadro

#### Funcionamento

1. **Cliente** envia requisição HTTP em quadro META (seq=0)
2. **Servidor** responde com cabeçalhos HTTP em META (seq=1), seguido de N quadros DATA (seq=2, 3, ...) e um FIN
3. Cada quadro é enviado via `_send_sw()`: envia, espera ACK por 0,5s; se timeout, retransmite (até 1000 tentativas)
4. **Cliente** confirma cada quadro com ACK; se receber quadro duplicado, reenvia o ACK
5. CRC32 valida a integridade do payload em cada quadro

---

## Validação com Wireshark

Filtro sugerido para acompanhar o fluxo completo:

```
udp.port == 53 || tcp.port == 8080 || udp.port == 8080
```

Sequência esperada:

```
1. UDP :53   → Consulta DNS (cliente → DNS)
2. UDP :53   → Resposta DNS  (DNS → cliente)
3. TCP/UDP :8080 → Handshake/quadros HTTP
4. TCP/UDP :8080 → Dados HTTP + confirmações
5. TCP/UDP :8080 → Finalização
```

