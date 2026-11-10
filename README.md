# SAJ IOP Solar — Home Assistant Integration

[![HACS Custom](https://img.shields.io/badge/HACS-Custom-41BDF5.svg)](https://github.com/hacs/integration)
[![HA Version](https://img.shields.io/badge/HA-2024.1%2B-blue.svg)](https://www.home-assistant.io/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

Integração nativa para monitorar micro inversores **SAJ** via portal [iop.saj-electric.com](https://iop.saj-electric.com) no Home Assistant.

> Comunicação direta com a API REST do portal SAJ — sem scraping, sem Selenium, sem add-ons extras.

---

## ✨ Recursos

| Categoria | Sensores |
|-----------|----------|
| **Por Inversor** | Potência atual (W), Energia hoje/mês/ano/total (kWh), Tensão/Corrente/Frequência da rede, Status, Receita do dia |
| **Planta (agregado)** | Potência total, Pico de potência, Energia hoje/total, Dispositivos online, Receita hoje/total |

- ⚡ **10 sensores por inversor + 8 da planta**, criados automaticamente
- 🔋 Compatível com o **Energy Dashboard** do HA
- 🌐 Traduções em **Português (BR)** e **Inglês**
- 🔒 Autenticação segura (AES-ECB + JWT)
- 🔄 Polling automático a cada 5 minutos

## 🔌 Dispositivos Suportados

Testado com:
- **SAJ M2-2.25K-S4** (Micro Inversor)

Deve funcionar com qualquer dispositivo registrado no portal iop.saj-electric.com.

---

## 📦 Instalação via HACS

### Repositório Privado (Custom)

1. Abra o **HACS** no Home Assistant
2. Vá em **Integrações** → menu ⋮ → **Repositórios personalizados**
3. Adicione a URL do repositório:
   ```
   https://github.com/DBSN-code/SAJ-Home_Assistant
   ```
4. Selecione a categoria **Integração**
5. Clique em **Adicionar**
6. Procure "SAJ IOP Solar" e instale
7. **Reinicie o Home Assistant**

---

## ⚙️ Configuração

1. Vá em **Configurações** → **Dispositivos e Serviços**
2. Clique em **+ Adicionar Integração**
3. Procure **"SAJ IOP Solar"**
4. Insira seu email e senha do portal SAJ
5. A integração detecta automaticamente sua planta e inversores

---

## 📊 Entidades Criadas

### Planta Solar
| Sensor | Tipo | Unidade |
|--------|------|---------|
| Potência total | Power | W |
| Pico de potência | Power | W |
| Energia total hoje | Energy | kWh |
| Energia total produzida | Energy | kWh |
| Dispositivos online | - | - |
| Total de dispositivos | - | - |
| Receita total hoje | - | R$ |
| Receita total | - | R$ |

### Por Micro Inversor
| Sensor | Tipo | Unidade |
|--------|------|---------|
| Potência | Power | W |
| Energia hoje | Energy | kWh |
| Energia este mês | Energy | kWh |
| Energia este ano | Energy | kWh |
| Energia total | Energy | kWh |
| Tensão da rede | Voltage | V |
| Corrente da rede | Current | A |
| Frequência da rede | Frequency | Hz |
| Estado | Enum | online/offline/alarm |
| Receita hoje | - | R$ |

---

## 🏗️ Arquitetura

```
custom_components/saj_iop/
├── __init__.py          # Setup da integração
├── api.py               # Cliente API REST (aiohttp)
├── config_flow.py       # Wizard de configuração UI
├── const.py             # Constantes
├── coordinator.py       # DataUpdateCoordinator
├── entity.py            # Entidades base
├── manifest.json        # Metadados HA
├── sensor.py            # Plataforma de sensores
├── strings.json         # Strings de tradução
└── translations/
    ├── en.json           # Inglês
    └── pt-BR.json        # Português (BR)
```

### API

A integração se comunica diretamente com a API REST do portal SAJ:
- **Autenticação:** Login v2, senha encriptada com AES-ECB e token Bearer.
- **API v2:** Login, estatísticas de energia da planta e fluxo de potência usam JSON com assinatura `X-Sign` (HMAC-SHA256 sobre os metadados e o MD5 do corpo enviado).
- **API v1:** Lista de plantas, lista de dispositivos e detalhes dos inversores mantêm as rotas compatíveis e a assinatura SHA1/MD5 anterior.
- **Sessão:** Uma tentativa de renovação quando a SAJ informa sessão expirada; requisições limitadas a 30 segundos.
- **Polling:** A cada 5 minutos (configurável)

### Compatibilidade com o portal atual (0.1.1)

O portal SAJ passou a usar `/dev-api/api/v2/sys/user/login`. O login antigo
retornava `10002 / Please login first`; as antigas rotas de resumo e fluxo da
planta retornavam texto indicando interface indisponível. A versão 0.1.1 usa
o protocolo atual nesses pontos e preserva os identificadores das entidades,
as unidades e os históricos existentes.

As seções `PV_ENERGY` e `REVENUE` de `getPlantEnergyStatistics` fornecem energia
em kWh e receita; `getDeviceEnergyFlowDiagram.totalPvPower` fornece potência em W.
Os contadores consideram os dispositivos devolvidos pela SAJ, inclusive registros
antigos offline, e os estados normal/alarme contam como online. Leituras ausentes
ficam desconhecidas, em vez de gerar zeros artificiais no histórico.

Atualize os arquivos da integração e reinicie o Home Assistant para carregar o
código Python novo. Não é necessário excluir ou cadastrar novamente a integração.

### Testes

Com `aiohttp` e `pycryptodome` instalados:

```bash
python -m unittest discover -s tests -p test_api.py -v
```

Para testar também o coordenador e os contratos das entidades, execute
`python -m unittest discover -s tests -v` em um ambiente com as dependências do
Home Assistant instaladas. Os testes não acessam contas reais nem alteram uma
instância em execução. A assinatura tem um vetor de referência calculado
separadamente com o módulo `crypto` do Node.js.

---

## 📝 Licença

[MIT](LICENSE)
