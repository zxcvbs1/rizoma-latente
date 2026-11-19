FROM python:3.12-slim

WORKDIR /app

# Instalar dependencias del sistema pesadas para compilación de Criptografía y Rust
RUN apt-get update && apt-get install -y \
    build-essential \
    libpq-dev \
    libssl-dev \
    libffi-dev \
    python3-dev \
    curl \
    pkg-config \
    rustc \
    cargo \
    && rm -rf /var/lib/apt/lists/*

# Copiar requerimientos e instalar con MÁXIMA VERBOSIDAD
COPY requirements.txt .
RUN pip install -vvv --no-cache-dir -r requirements.txt

# Copiar el código del proyecto
COPY . .

# Exponer el puerto de la API
EXPOSE 8000

CMD ["uvicorn", "apps.api.main:app", "--host", "0.0.0.0", "--port", "8000", "--reload", "--reload-dir", "/app"]
