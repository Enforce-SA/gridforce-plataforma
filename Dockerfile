# GridForce em contentor (Azure App Service ou outro alojamento)
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PORT=8000
WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 8000
# As chaves (ENTSOE_TOKEN, GRIDFORCE_LIB_TOKEN, GRIDFORCE_ENV, GRIDFORCE_LIB_FOLDER, APP_PASSWORD)
# entram como variáveis de ambiente do alojamento, nunca na imagem.
CMD streamlit run app.py --server.port=${PORT} --server.address=0.0.0.0 --server.headless=true \
    --browser.gatherUsageStats=false --server.enableXsrfProtection=true
