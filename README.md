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

## Publicar no Streamlit Community Cloud

1. Pôr esta pasta num repositório GitHub privado.
2. Em https://share.streamlit.io, "Create app", escolher o repositório e `app.py`.
3. Em "Advanced settings > Secrets", acrescentar `ENTSOE_TOKEN = "..."` para ativar o aFRR.
4. Em "Sharing", restringir o acesso aos emails autorizados.
