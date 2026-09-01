# SafetyWatch

Sistema de monitoramento automatizado de EPIs (Equipamentos de Proteção Individual) que combina visão computacional, orquestração de workflows e LLMs para detectar violações de segurança e gerar respostas automatizadas em tempo real.

Este projeto integra o [DetectEPI](https://github.com/Kines0124/DetectEPI) — um modelo YOLOv8 fine-tuned para detecção de capacete e colete — com uma camada de orquestração e decisão, transformando uma simples inferência de modelo em um pipeline completo: detecção → decisão → alerta → registro → análise.

## Arquitetura

```
[Câmera/Vídeo]
    → DetectEPI (YOLOv8, servido via FastAPI)
    → Webhook → n8n
         → Lógica de decisão (severidade, confiança, reincidência)
         → LLM gera relatório de incidente em linguagem natural
         → Notificação (Slack/Telegram/E-mail)
         → Persistência (PostgreSQL)
    → Dashboard de métricas e monitoramento
```

## Por que dois repositórios separados

O DetectEPI é um projeto de Machine Learning independente e versionado por conta própria — ele documenta seu próprio ciclo de treino, validação e limitações. O SafetyWatch consome o DetectEPI como um **serviço**, através de uma imagem Docker publicada e versionada no GitHub Container Registry, não como código importado. Isso reflete como sistemas reais compõem modelos de ML como dependências de infraestrutura, e não como acoplamento direto de código.

```yaml
detectepi:
  image: ghcr.io/kines0124/detectepi:v1.1.1
```

## Stack

| Componente | Tecnologia |
|---|---|
| Detecção de EPI | YOLOv8 (via [DetectEPI](https://github.com/Kines0124/DetectEPI)), servido com FastAPI |
| Orquestração | n8n |
| Geração de relatórios | LLM (LangChain/API) |
| Persistência | PostgreSQL |
| Containerização | Docker Compose |
| CI/CD | GitHub Actions (no repositório DetectEPI) |

## Como rodar

**Pré-requisitos:** Docker Desktop instalado e rodando.

1. Clone o repositório:
   ```bash
   git clone https://github.com/Kines0124/SafetyWatch.git
   cd SafetyWatch
   ```

2. Copie o arquivo de variáveis de ambiente e edite com suas credenciais:
   ```bash
   cp .env.example .env
   ```

3. Suba os serviços:
   ```bash
   docker compose up -d
   ```

4. Acesse:
   - DetectEPI (API de detecção): `http://localhost:8000/docs`
   - n8n (orquestração de workflows): `http://localhost:5678`

## Status do projeto

Em desenvolvimento ativo, como parte de um processo de aprendizado guiado combinando DevOps, MLOps e automação com IA.

- [x] Modelo de detecção (DetectEPI) versionado e publicado como imagem Docker no GHCR
- [x] Pipeline de CI/CD para build e publicação automática da imagem
- [x] Esqueleto de orquestração (docker-compose com DetectEPI + n8n + PostgreSQL)
- [ ] Workflow de decisão no n8n (roteamento por severidade/confiança)
- [ ] Geração de relatórios de incidente via LLM
- [ ] Dashboard de monitoramento
- [ ] Documentação final de arquitetura e limitações

## Limitações conhecidas

O modelo de detecção (DetectEPI) apresenta domain shift em vídeos externos ao dataset de treino — especificamente na detecção de capacetes, que se torna inconsistente sob variação de ângulo, iluminação e compressão, mesmo quando visível a olho nu. A detecção de colete permanece confiável nesses mesmos cenários. Mais detalhes sobre o comportamento do modelo, experimentos realizados e mitigações (thresholds de confiança por classe) estão documentados no [README do DetectEPI](https://github.com/Kines0124/DetectEPI).

## Licença

MIT