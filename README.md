# SafetyWatch

SafetyWatch é um sistema de monitoramento automatizado de EPIs (Equipamentos de Proteção Individual) que combina visão computacional, orquestração de workflows e um LLM para detectar violações de segurança em vídeo, agrupá-las em incidentes coerentes e gerar relatórios e alertas automáticos por e-mail. O projeto integra o [DetectEPI](https://github.com/Kines0124/DetectEPI), um modelo YOLOv8 fine-tuned para detecção de capacete e colete, como serviço de inferência, e constrói em cima dele uma camada completa de decisão, agregação temporal e comunicação.

## Sumário

- [Como Funciona](#como-funciona)
- [Por que Dois Repositórios Separados](#por-que-dois-repositórios-separados)
- [Stack](#stack)
- [Agregação de Incidentes: de Detecções Isoladas a Eventos Coerentes](#agregação-de-incidentes-de-detecções-isoladas-a-eventos-coerentes)
- [Workflow de Decisão (n8n)](#workflow-de-decisão-n8n)
- [Geração de Relatórios via LLM](#geração-de-relatórios-via-llm)
- [Modelo de Dados](#modelo-de-dados)
- [Dashboard de Monitoramento](#dashboard-de-monitoramento)
- [Como Rodar](#como-rodar)
- [Licença](#licença)

## Como Funciona

Um script (`frame_producer.py`) lê um vídeo frame a frame, simulando uma câmera em tempo real, e envia cada frame amostrado para o DetectEPI, servido como API via FastAPI. Quando uma violação é detectada, o script mantém um incidente aberto em memória, agregando detecções ao longo do tempo em vez de tratá-las como eventos isolados. Esse incidente é comunicado ao n8n em três momentos do seu ciclo de vida (abertura, atualização periódica por heartbeat, e encerramento) via webhook. O n8n decide se a violação é significativa o suficiente para notificar, persiste o histórico completo no PostgreSQL, gera um relatório em linguagem natural através de um LLM e envia esse relatório por e-mail. Um dashboard em Power BI, conectado diretamente ao banco, oferece visão agregada sobre a frequência, duração e confiança das detecções ao longo do tempo.

## Por que Dois Repositórios Separados

O DetectEPI é um projeto de Machine Learning independente, com seu próprio ciclo de treino, validação e documentação de limitações. O SafetyWatch consome o DetectEPI como um **serviço**, através de uma imagem Docker publicada e versionada no GitHub Container Registry, não como código importado:

```yaml
detectepi:
  image: ghcr.io/kines0124/detectepi:v1.1.1
```

Essa separação reflete como sistemas reais compõem modelos de ML como dependências de infraestrutura versionadas, em vez de acoplamento direto de código, e permite que os dois projetos evoluam (e sejam avaliados) de forma independente.

## Stack

| Componente | Tecnologia |
|---|---|
| Detecção de EPI | YOLOv8 ([DetectEPI](https://github.com/Kines0124/DetectEPI)), servido via FastAPI |
| Simulação de stream | Python + OpenCV (`frame_producer.py`) |
| Orquestração e decisão | n8n |
| Geração de relatórios | LLM via OpenRouter (`openrouter/free`) |
| Notificação | E-mail (SMTP) |
| Persistência | PostgreSQL |
| Visualização | Power BI |
| Containerização | Docker Compose |
| CI/CD | GitHub Actions (no repositório DetectEPI) |

## Agregação de Incidentes: de Detecções Isoladas a Eventos Coerentes

A primeira versão do pipeline enviava um evento ao n8n para cada frame com violação detectada. Isso se mostrou inadequado assim que testado com vídeo real: uma única pessoa sem colete, visível ao longo de 30 segundos de vídeo, gerava dezenas de eventos praticamente idênticos, inflando o banco de dados sem necessidade e, mais adiante, teria disparado o mesmo número de chamadas ao LLM e e-mails duplicados sobre a mesma ocorrência.

A solução foi tratar cada violação como um **incidente com ciclo de vida**, não como uma sequência de detecções soltas. O `frame_producer.py` mantém um único incidente aberto por vez, agrupando qualquer classe de violação sob o mesmo evento (uma "quebra de regra" geral, não um incidente por classe). Assim, capacete e colete ausentes simultaneamente na mesma pessoa geram um único relatório, não dois.

**Parâmetros de controle:**

```python
GAP_TOLERANCE = 8.0        # segundos sem detecção até considerar o incidente encerrado
HEARTBEAT_INTERVAL = 600.0 # 10 minutos, intervalo de atualização para incidentes longos
```

- **`GAP_TOLERANCE` (8s):** cobre falhas momentâneas de detecção (variação de ângulo, iluminação, ou o próprio domain shift documentado no DetectEPI) sem fechar e reabrir o mesmo incidente a cada oscilação. O trade-off é conhecido: uma tolerância curta demais fragmentaria incidentes contínuos em vários; uma tolerância longa demais poderia fundir duas ocorrências de pessoas diferentes que se revezam rapidamente na cena.
- **`HEARTBEAT_INTERVAL` (10min):** resolve o caso de uma violação que nunca é resolvida enquanto a câmera está ligada. Sem um mecanismo de heartbeat, um incidente que dura horas nunca dispararia notificação, já que o relatório só seria gerado no fechamento. A cada 10 minutos de violação contínua, um evento `ongoing` é emitido, garantindo que situações prolongadas sejam sinalizadas antes do fim.

Cada classe dentro de um incidente acumula `max_confidence` (maior confiança já observada) e `max_concurrent` (maior número de detecções simultâneas da mesma classe em um único frame). Esse último valor é uma métrica defensável de "quantas pessoas ao mesmo tempo", já que múltiplas detecções da mesma classe num único frame correspondem, de fato, a objetos distintos (o NMS do YOLO já elimina caixas duplicadas do mesmo objeto).

## Workflow de Decisão (n8n)

O workflow recebe os eventos do `frame_producer.py` via webhook e aplica a seguinte lógica:

```
Webhook → Normalizar Payload → Incidente é Novo?
                                    ├─[sim]─→ Criar Incidente (Postgres INSERT)
                                    └─[não]─→ Atualizar Incidente (Postgres UPDATE)
                                                  └─→ Duração Suficiente para Notificar?
                                                          ├─[sim]─→ Montar Resumo → Gerar Relatório (LLM) → Enviar E-mail
                                                          └─[não]─→ (apenas registrado, sem notificação)
```

Todo incidente é persistido no banco, independentemente de gerar notificação. Um filtro de duração mínima (8 segundos) evita alertas sobre detecções isoladas de um único frame, prováveis falsos positivos, sem descartar o dado, que permanece disponível para o dashboard e para uma futura análise de ruído do modelo.

A severidade de uma violação não é decidida por um corte binário automático. Essa decisão foi deliberadamente delegada ao LLM na etapa seguinte, que comenta a confiança da detecção em linguagem natural no próprio relatório, em vez de um `if` classificando "confirmado" ou "incerto" de forma rígida.

## Geração de Relatórios via LLM

Cada evento que passa no filtro de duração é resumido em texto simples (evitando problemas de serialização de JSON aninhado dentro de um prompt) e enviado para a API de chat completions do OpenRouter, usando o modelo roteador `openrouter/free`, que seleciona automaticamente, a cada chamada, um modelo gratuito disponível no momento, evitando depender de um nome de modelo específico que pode ser descontinuado.

O prompt instrui o modelo a reportar apenas os dados fornecidos, sem inferir ou completar informações ausentes. Essa foi uma medida necessária após observar, durante o desenvolvimento, que modelos menores tendem a preencher lacunas de forma confiante em vez de sinalizar dado ausente.

## Modelo de Dados

A tabela `incidents` no PostgreSQL guarda uma linha por incidente, identificado por um `incident_id` (UUID gerado pelo produtor) com constraint de unicidade, atualizada nos eventos `ongoing` e `closed` em vez de duplicada. A coluna `classes` armazena um objeto JSONB com uma entrada por classe envolvida no incidente, permitindo que um único registro represente uma violação múltipla (por exemplo, capacete e colete ausentes ao mesmo tempo).

## Dashboard de Monitoramento

Construído em Power BI, conectado diretamente ao PostgreSQL. A coluna JSONB `classes` é normalizada em uma tabela separada (`Incident_Classes`, relacionada 1:N com `Incidents`) via Power Query, evitando que incidentes com múltiplas classes distorçam métricas agregadas como duração média.

- **Visão Geral:** total de incidentes, duração média, máximo de pessoas simultâneas, violações por classe, incidentes ao longo do tempo, duração por incidente.
- **Confiança do Modelo:** confiança média das detecções ao longo do tempo, um proxy simples para acompanhar possível degradação do modelo em produção (data drift), além de uma tabela detalhada de incidentes para investigação pontual.

## Como Rodar

**Pré-requisitos:** Docker Desktop instalado e rodando.

1. Clone o repositório e configure as variáveis de ambiente:
   ```bash
   git clone https://github.com/Kines0124/SafetyWatch.git
   cd SafetyWatch
   cp .env.example .env
   # edite o .env com suas credenciais do Postgres
   ```

2. Suba os serviços:
   ```bash
   docker compose up -d
   ```
   Isso sobe o DetectEPI, o PostgreSQL e o n8n, e importa automaticamente a estrutura do workflow salva em `workflows/SafetyWatch.json`.

3. **Reconecte as credenciais no n8n** (`localhost:5678`). O workflow importado não traz credenciais sensíveis (Postgres, OpenRouter, SMTP) por design, então elas precisam ser recriadas manualmente na interface antes de publicar o workflow.

4. Rode o produtor de frames, apontando para um arquivo de vídeo local:
   ```bash
   python frame_producer.py
   ```

5. Acesse o DetectEPI em `localhost:8000/docs` e o n8n em `localhost:5678`.

**Nota de manutenção:** ao editar o workflow diretamente na interface do n8n, reexporte o arquivo `workflows/SafetyWatch.json` e commite a atualização. Ele é a fonte de verdade versionada do workflow, e não é sincronizado automaticamente com o volume Docker.

## Licença

MIT