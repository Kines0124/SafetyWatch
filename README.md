# SafetyWatch

Sistema de monitoramento automatizado de EPIs (Equipamentos de Proteção Individual) que combina visão computacional, orquestração de workflows e LLMs para detectar violações de segurança e gerar respostas automatizadas em tempo real.

Este projeto integra o [DetectEPI](https://github.com/Kines0124/DetectEPI) — um modelo YOLOv8 fine-tuned para detecção de capacete e colete — com uma camada de orquestração e decisão, transformando uma simples inferência de modelo em um pipeline completo: detecção → decisão → alerta → registro → análise.

## Arquitetura