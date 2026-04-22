# SAJ IOP Solar — Contexto do Projeto

## Visão Geral
Integração customizada para Home Assistant que monitora micro inversores SAJ
via API REST nativa do portal [iop.saj-electric.com](https://iop.saj-electric.com).

- **Repositório:** https://github.com/DBSN-code/SAJ-Home_Assistant
- **Autor:** DBSN-code
- **Versão:** 0.1.0
- **Licença:** MIT

## Hardware
- **2x Micro Inversores SAJ M2-2.25K-S4** (4.5 kW total)
  - "Sala" — SN: M2S4225J2421E91629
  - "Garagem" — SN: M2S4225J2413E41786
- **Planta:** "Bairro Novo" — UID: CB7780471209466F8315CE1CE3B4E92B

## Ambiente Home Assistant
- **Instalação:** Home Assistant Container (LXC no Proxmox)
- **Core:** 2026.4.1
- **HACS:** Instalado
- **MQTT:** Instalado (outro LXC, não utilizado ainda)

## Arquitetura da API SAJ

### Autenticação
- **URL Base:** `https://iop.saj-electric.com/dev-api/api/v1`
- **Senha:** Encriptada com **AES-ECB** (chave: `ec1840a7c53cf0709eb784be480379b6`)
- **Token:** JWT Bearer, expira em ~72h (259199s)
- **Renovação:** Automática via `_ensure_authenticated()`

### Assinatura de Requisições
Todas as requisições precisam de uma assinatura calculada assim:
1. Coletar pares `key=value` (excluindo `signature` e `signParams`)
2. Remover valores vazios/nulos
3. Ordenar por char code ASCII (lexicográfico)
4. Juntar com `&`
5. Append `&key=ktoKRLgQPjvNyUZO8lVc9kU1Bsip6XIe`
6. MD5 do resultado
7. SHA1 do MD5 (uppercase)

**Diferença GET vs POST:**
- **GET:** Assina TODOS os parâmetros (extra + comuns)
- **POST:** Assina APENAS os parâmetros comuns (appProjectName, clientDate, lang, timeStamp, random, clientId)

### Parâmetros Comuns (toda requisição)
```
appProjectName = "elekeeper"
clientId = "esolar-monitor-admin"
clientDate = "YYYY-MM-DD"
timeStamp = <unix_ms>
random = <32_char_alphanumeric>
lang = "en"
```

### Endpoints Utilizados
| Endpoint | Método | Descrição |
|----------|--------|-----------|
| `/sys/login` | POST | Login (retorna JWT) |
| `/monitor/plant/getPlantList` | GET | Lista de plantas |
| `/monitor/home/getPlantGridOverviewInfo` | GET | Visão geral da planta |
| `/monitor/home/getDeviceEneryFlowData` | GET | Fluxo de energia |
| `/monitor/device/getDeviceList` | GET | Lista de dispositivos |
| `/monitor/device/getOneDeviceInfo` | GET | Detalhes de 1 inversor |
| `/monitor/weather/getCurrentWeather` | GET | Clima atual |

## Entity IDs no Home Assistant

### Planta "Bairro Novo"
| Sensor | Entity ID |
|--------|-----------|
| Potência total | `sensor.bairro_novo_potencia_total` |
| Energia total hoje | `sensor.bairro_novo_energia_total_hoje` |
| Energia total produzida | `sensor.bairro_novo_energia_total_produzida` |
| Potência de pico | `sensor.bairro_novo_potencia_de_pico` |
| Dispositivos online | `sensor.bairro_novo_dispositivos_online` |
| Total de dispositivos | `sensor.bairro_novo_total_de_dispositivos` |
| Receita total hoje | `sensor.bairro_novo_receita_total_hoje` |
| Receita total | `sensor.bairro_novo_receita_total` |

### Inversor "Sala"
| Sensor | Entity ID |
|--------|-----------|
| Potência | `sensor.sala_potencia` |
| Energia hoje | `sensor.sala_energia_hoje` |
| Energia este mês | `sensor.sala_energia_este_mes` |
| Energia este ano | `sensor.sala_energia_este_ano` |
| Energia total | `sensor.sala_energia_total` |
| Tensão da rede | `sensor.sala_tensao_da_rede` |
| Corrente da rede | `sensor.sala_corrente_da_rede` |
| Frequência da rede | `sensor.sala_frequencia_da_rede` |
| Estado | `sensor.sala_estado` |
| Receita hoje | `sensor.sala_receita_hoje` |

### Inversor "Garagem"
Mesmo padrão: `sensor.garagem_*` (substituir `sala` por `garagem`)

## Estrutura do Projeto
```
SAJ-Home_Assistant/
├── custom_components/saj_iop/   # Integração HA
│   ├── __init__.py              # Setup
│   ├── api.py                   # Cliente API REST
│   ├── config_flow.py           # Wizard de configuração
│   ├── const.py                 # Constantes
│   ├── coordinator.py           # DataUpdateCoordinator
│   ├── entity.py                # Entidades base
│   ├── sensor.py                # 18 sensores
│   ├── manifest.json            # Metadados HA
│   ├── strings.json             # Strings tradução
│   ├── icon.png                 # Ícone 256x256
│   ├── icon@2x.png              # Ícone 512x512
│   ├── logo.png                 # Logo
│   └── translations/            # PT-BR + EN
├── dev/                         # Desenvolvimento (não commitado)
│   ├── scripts/                 # Scripts de teste e captura
│   ├── analysis/                # Resultados de análise
│   └── captured_data/           # Dados capturados do portal
├── docs/                        # Documentação extra
│   ├── dashboard_solar.yaml     # Dashboard Lovelace
│   └── M2 2.25K-S4...pdf       # Datasheet do inversor
├── .gitignore
├── hacs.json
├── LICENSE
├── README.md
└── CONTEXT.md                   # ← Este arquivo
```

## Decisões Técnicas
1. **API REST nativa** (não web scraping) — mais estável e eficiente
2. **pycryptodome** para AES-ECB — necessário para encriptar senha
3. **aiohttp** — já disponível no HA, assíncrono
4. **DataUpdateCoordinator** — polling a cada 5 minutos
5. **state_class: total_increasing** — compatível com Energy Dashboard
6. **Traduções PT-BR** — entity IDs gerados em português pelo HA

## Histórico de Desenvolvimento
- **Fase 1:** Mapeamento da API via Playwright (captura HTTP)
- **Fase 2:** Cliente API Python (api.py) — algoritmo de assinatura decifrado
- **Fase 3:** Integração HA completa (config_flow, coordinator, sensor)
- **Fase 4:** GitHub + HACS (repo público)
- **Fase 5:** Instalação e testes no HA ✅
