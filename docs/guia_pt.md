# Guia rápido do GridForce

O GridForce dimensiona e simula projetos de painéis solares (PV) e baterias em Portugal. Calcula o autoconsumo, a venda e compra nos mercados diário e intradiário do OMIE e a participação nos serviços de sistema da REN (aFRR e mFRR), e transforma tudo num investment case: VAL (NPV), TIR (IRR), payback e contas anuais.

Este guia explica o essencial para testar e validar projetos. Demora cerca de 10 minutos a ler.

## Antes de começar

- **Qualidade e Produção.** Há duas versões da aplicação. A de **Qualidade** (faixa amarela no topo) serve para testar melhorias novas e tem a sua própria biblioteca de projetos. A de **Produção** é a versão aprovada. Os resultados de uma e de outra podem diferir enquanto há melhorias em teste.
- **Língua.** Escolhe Português ou English no canto superior direito. Os projetos guardados não mudam com a língua.
- **Versão.** A versão em uso está no fundo da página, em "Histórico de versões", com a descrição de cada alteração.

## 1. Abrir ou criar um projeto

Abre **Biblioteca de projetos**, no topo da página.

1. Em **Projetos da biblioteca a abrir**, escolhe um ou mais projetos (ou usa **Selecionar todos**).
2. Também podes carregar ficheiros de projeto (.json) do teu computador e guardá-los na biblioteca.
3. Com vários projetos abertos, escolhe em **Projeto a mostrar nos separadores** qual queres ver e editar. O botão **Correr os N projetos** simula todos de uma vez e mostra a carteira no separador 5.

A biblioteca é partilhada com toda a equipa. **Guardar com o mesmo nome substitui o projeto existente**, por isso, quando fizeres alterações para testar, muda o nome (por exemplo "Lousal - teste Ana"). **Apagar da biblioteca** não se pode desfazer.

Para começar um projeto novo, carrega em **➕ Novo projeto** (por cima dos separadores). Os campos próprios do projeto ficam vazios (nome, localização, consumo, custos unitários, preço fixo e variantes) e os restantes ficam com valores típicos, que deves confirmar. Se faltar algum campo obrigatório, a aplicação diz qual antes de correr.

## 2. Preencher os separadores

**1. Local e consumo.** Nome, cenário (opcional, ex.: Investment Grade), latitude e longitude (a produção PV vem do PVGIS para essas coordenadas). Em **Consumo do local** escolhe um perfil tipo C&I com o consumo anual, carrega um diagrama de carga (de preferência no modelo Excel que se descarrega ali mesmo, horário ou de 15 minutos; também aceita CSV com uma coluna em kW) ou escolhe "Sem consumo" para parques só de produção e armazenamento. Indica os limites de importação e de injeção na rede, se existirem.

**2. PV e bateria.** Inclinação, azimute (180 = sul), perdas, rácio DC/AC, degradação e custos unitários do PV. Para a bateria: eficiência, janela de SOC, perda de capacidade, custo de desgaste, limite de ciclos por dia e custos. Os blocos "Mais parâmetros da bateria" e "Degradação, fim de vida e substituições" têm opções avançadas (degradação por ciclos, reposição de capacidade, substituição do PCS).

**3. Mercados, tarifas e finanças.**

- **Mercados:** período de preços OMIE (os 12 meses até à data escolhida), arbitragem no diário, aFRR, intradiário e mFRR. Nos serviços de sistema, a taxa de ativação e as "ofertas aceites" têm grande impacto. A GridCog usa 50% de ofertas aceites.
- **Tarifas:** nível de tensão (tarifas de acesso ERSE), outros custos na compra e venda do PV ao mercado ou a preço fixo (PPA).
- **Finanças:** ano de início, duração, taxa de desconto, licenciamento e ligação à rede (separado do capex do equipamento), custos de O&M e seguro (em EUR/ano ou EUR/dia), fator de emissões da rede, escalada de preços e valor residual. Em **Financiamento e impostos** podes juntar dívida e IRC. Com estes a zero, o caso é antes de impostos e só com capital próprio, como na GridCog.
- **Modo rápido** simula o 1.º e o último ano e interpola os restantes. É suficiente para comparar variantes. Desliga-o para uma corrida final mais rigorosa.

**4. Variantes.** Uma linha por configuração a comparar: kWp de PV, kWh e kW de bateria. Se souberes o capex total de uma variante, escreve-o em "Capex total (EUR)". Nesse caso substitui o cálculo pelos custos unitários. Para ver o valor da bateria, junta uma linha só com PV.

## 3. Correr e ler os resultados

Carrega em **Correr simulação**. Uma simulação demora normalmente entre 15 segundos e 2 minutos, conforme o número de variantes e de mercados. O separador **5. Resultados** mostra:

- **Melhor variante, VAL, TIR e payback**, e a tabela **Resumo das variantes** com todos os indicadores.
- **Value stack:** o que cada fonte de valor ganha ou perde no 1.º ano face à base, que é o mesmo local sem os novos ativos.
- **Cashflow descontado acumulado:** o ponto onde cruza o zero é o payback descontado.
- **Despacho num dia:** escolhe uma variante e um dia para ver o que fazem o PV, a bateria e a rede, com o preço OMIE.
- **Contas anuais:** receitas, opex, EBITDA, capex, cashflow e, se houver financiamento, imposto, juros, DSCR e cashflow do acionista.
- **Riscos e sensibilidades:** o gráfico tornado mostra quanto muda o VAL quando cada fator sobe ou desce. **Correr cenários de preços** volta a simular com os preços dos anos anteriores e dá o P90, P50 e P10 do VAL. P90 é o valor mais prudente.
- **Energia no 1.º ano** e **Cenário base e valor incremental:** compara uma variante com a base (sem ativos) ou com outra variante (ex.: PV + bateria face a só PV), com o VAL e a TIR incrementais e o cashflow relativo ano a ano.
- **Preços aplicados por ano:** preços médios de mercado (diário, intradiário, aFRR, mFRR), PPA, O&M e seguro usados em cada ano.
- **Fluxos de energia entre ativos e emissões evitadas:** PV para a rede, PV para a bateria, bateria para a rede, etc., e as toneladas de CO2 evitadas.
- Ao correr vários projetos de uma vez, **Cenários lado a lado** mostra os totais de cada cenário (ex.: Investment Grade e Ultra Conservative) e cada parque em cada cenário.
- **Auditoria da execução:** versão do motor, dados usados e verificações automáticas do balanço de energia e dos limites.

Para gravar uma nova versão ou um projeto novo a partir de um existente, usa **Gravar como...** ao lado de "Guardar projeto na biblioteca": grava com outro nome e o original fica como estava.

## 4. Exportar

- **Descarregar relatório (Word):** relatório completo da variante escolhida, com resumo, energia, análise comercial, sensibilidades, comparação de variantes e pressupostos, na língua ativa. Se correres antes os cenários de preços para essa variante, o P90/P50/P10 também entra.
- **Descarregar investment case (Excel):** todos os números, incluindo o despacho de 15 em 15 minutos do 1.º ano.
- **Descarregar projeto (.json):** os dados de entrada, para guardar ou partilhar fora da biblioteca.

## 5. Como validar e reportar

1. Compara com uma referência que conheças (por exemplo, o relatório GridCog do mesmo projeto): capex, produção PV, ganho do 1.º ano, VAL e TIR. Usa os mesmos pressupostos dos dois lados (taxa de desconto, duração, preços de aFRR, ofertas aceites).
2. Quando algo não bater certo, olha primeiro para o **Value stack** e para a **Energia no 1.º ano**. Normalmente a diferença está numa fonte de valor concreta.
3. Para reportar um problema ou uma sugestão, envia: nome do projeto e variante, a versão (fundo da página), o que esperavas e o que viste, e se possível o relatório Word ou o Excel.

## Limitações a ter presentes

- O despacho da bateria usa **previsão perfeita** de preços. Os ganhos de mercado são por isso um limite superior. Na operação real ficam tipicamente abaixo.
- Os preços dos serviços de sistema vêm da ENTSO-E para os últimos 12 meses e repetem-se nos anos seguintes com a escalada definida. Os preços de capacidade aFRR desceram muito desde junho de 2025. O campo "Ajuste dos preços de capacidade aFRR" serve para testar outros níveis.
- Com o modo rápido, os anos intermédios são interpolados.
