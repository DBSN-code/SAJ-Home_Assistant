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

- ⚡ **18 sensores** criados automaticamente (10 por inversor + 8 da planta)
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
- **Autenticação:** Senha encriptada com AES-ECB + JWT Bearer Token
- **Assinatura:** SHA1(MD5(params + secret_key))
- **Endpoints:** Login, Plant List, Device List, Device Info, Energy Flow
- **Polling:** A cada 5 minutos (configurável)

---

## 📝 Licença

[MIT](LICENSE)
