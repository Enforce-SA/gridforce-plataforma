# GridForce

Plataforma interna de dimensionamento e simulação de PV e baterias em Portugal
(autoconsumo, mercado diário OMIE, aFRR e tarifas de acesso ERSE).

## Estrutura

- `app.py`: interface web (Streamlit)
- `gridforce/project.py`: configuração de projeto e execução de todas as variantes
- `gridforce/dispatch.py`: otimização do despacho de 15 min (HiGHS)
- `gridforce/finance.py`: cashflows, VAL, TIR, payback
- `gridforce/tariffs.py`: tarifas de acesso ERSE e períodos horários
- `gridforce/data/`: OMIE, PVGIS, ENTSO-E (aFRR) e perfis de consumo tipo
- `run_demo_validation.py`: comparação com o caso de demonstração GridCog

## Correr localmente

```
pip install -r requirements.txt
streamlit run app.py
```

## Ambientes e versões

- **Produção**: ramo `main`, app https://gridforce-enforce.streamlit.app. Só recebe versões já testadas.
- **Qualidade**: ramo `qualidade`, segunda app no Streamlit (segredo `GRIDFORCE_ENV = "qualidade"`). Mostra um aviso de
  ambiente de testes e usa a pasta `projetos_qualidade` da biblioteca (`GRIDFORCE_LIB_FOLDER`), para os testes não
  mexerem nos projetos de Produção. Se a app for pública, definir `APP_PASSWORD`.
- Fluxo: cada melhoria vai primeiro para `qualidade`; depois de aprovada, junta-se a `main`, sobe-se o número em
  `gridforce/version.py`, regista-se em `CHANGELOG.md` e cria-se a etiqueta `vX.Y.Z` no GitHub.
- A versão e o histórico aparecem no fundo da aplicação.

## Publicar no Streamlit Community Cloud

1. O código está em Enforce-SA/gridforce-plataforma (público); os projetos em Enforce-SA/gridforce-projetos (privado).
2. Em https://share.streamlit.io, "Create app", escolher o repositório e `app.py`.
3. Em "Advanced settings > Secrets": `ENTSOE_TOKEN` (aFRR/mFRR) e `GRIDFORCE_LIB_TOKEN` (biblioteca de projetos).
4. Em "Sharing", restringir o acesso aos emails autorizados.
