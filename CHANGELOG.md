# Histórico de versões da GridForce

Cada versão publicada em Produção tem um número (maior.menor.correção), a data e a descrição das alterações.
As alterações são primeiro publicadas e testadas no ambiente de Qualidade.

## 0.11.0 (2026-11-24)
- Montagem PV: fixo ou com seguidor (1 eixo horizontal N-S a rodar E-O, 1 eixo inclinado, 2 eixos). O perfil de produção vem do PVGIS para o tipo escolhido. Projetos já gravados continuam como fixo.

## 0.10.0 (2026-11-23)
- Licenciamento e ligação à rede como custo de investimento separado do equipamento.
- O&M e seguro em EUR/ano ou EUR/dia.
- Capex do equipamento: escolha explícita entre "calculado por EUR/kWp e EUR/kWh" e "valor fixo por variante"; quadro "Capex total usado na simulação" no separador 4.
- Separador 2 mostra a potência de pico PV (kWp) e a potência AC do inversor.
- Cenário base e valor incremental: comparar uma variante com a base ou com outra variante (VAL e TIR incrementais, cashflow relativo).
- Campo Cenário e "Cenários lado a lado" ao correr vários projetos (ex.: Investment Grade e Ultra Conservative).
- Tabela de preços aplicados por ano (mercados, PPA, aFRR/mFRR, O&M, seguro), também no Excel e no relatório.
- Fluxos de energia entre ativos e emissões evitadas (fator da rede 470 g CO2/kWh por omissão).
- "Gravar como..." para gravar uma nova versão ou um projeto novo sem substituir o original.
- Value stack com uma cor por fonte de valor e nota sobre a venda em mercado com PPA.

## 0.9.1 (2026-11-20)
- Botão "Novo projeto": limpa os campos próprios do projeto nos separadores 1 a 4 e mantém valores típicos nos restantes; avisa o que falta preencher antes de correr.
- Ao abrir outro projeto, todos os campos passam a mostrar os valores desse projeto, e mudar de língua já não apaga o que se escreveu.

## 0.9.0 (2026-11-20)
- Relatório Word da variante escolhida, em português ou inglês: resumo, energia (balanço, perfis mensal e diário), análise comercial (value stack, cashflow, custos, contas anuais, financiamento), sensibilidades e cenários P90/P50/P10, comparação de variantes, pressupostos e auditoria.
- Guia rápido para quem testa, dentro da aplicação e em Word, em português e inglês.

## 0.8.1 (2026-11-19)
- Contentor Docker e publicação automática da imagem, para alojamento próprio no Azure.
- "Perfil tipo de centro comercial" passa a chamar-se "Perfil tipo C&I" (os projetos guardados continuam a abrir).

## 0.8.0 (2026-11-19)
- Biblioteca de projetos partilhada (repositório privado), com guardar, abrir, apagar e "Selecionar todos".
- Botões "Guardar projeto na biblioteca" e "Descarregar projeto (.json)", incluindo diagrama de carga.
- Interface e Excel em inglês (seletor Português / English).
- VAL e TIR identificados também como NPV e IRR.
- Aviso 30 dias antes de a chave da biblioteca expirar.
- Ambientes de Qualidade e Produção, número de versão visível e este histórico.

## 0.7.0 (2026-11-19)
- Sensibilidades (tornado) de capex, opex, preços de energia, PPA, capacidade aFRR e ativações.
- Cenários P90/P50/P10 com preços OMIE de anos anteriores (Monte Carlo).
- Horizonte de despacho dia a dia (mais realista) ou semanal.
- Financiamento: dívida (anuidade ou amortização constante), DSCR mínimo, IRC com prejuízos reportados, TIR e VAL do acionista.
- Dados: anos OMIE fechados lidos dos ficheiros anuais; pedidos ENTSO-E mais robustos; cache de preços públicos.

## 0.6.0 (2026-11-19)
- Bateria: eficiências de carga e descarga, disponibilidade, consumos auxiliares.
- Degradação por ciclos e calendário, fim de vida, augmentation e substituição do PCS.
- Comissão do agregador/BSP, escalada de preços, valor residual, EBITDA, LCOS, contas anuais e auditoria da execução.
- Ajuste manual dos preços de capacidade aFRR.

## 0.5.0 (2026-11-19)
- Mercado intradiário contínuo (OMIE) e reserva mFRR (ativação, ENTSO-E).
- Limite de ciclos por dia da bateria.

## 0.4.0 (2026-11-19)
- aFRR com preços ENTSO-E e taxa de ofertas aceites.
- Abrir vários projetos .json e correr a carteira de uma vez; legendas dos gráficos corrigidas.

## 0.3.0 (2026-11-19)
- Parques sem consumo, venda PV a preço fixo (PPA), capex adicional, O&M e seguro.
- Abrir projeto a partir de ficheiro .json.

## 0.2.0 (2026-11-18)
- Identidade visual Enforce e tema escuro.

## 0.1.0 (2026-11-18)
- Primeira versão: motor de simulação PV + bateria (OMIE, PVGIS, tarifas ERSE) e interface Streamlit.
