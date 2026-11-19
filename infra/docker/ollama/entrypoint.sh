#!/bin/bash

# Iniciar Ollama en segundo plano
ollama serve &

# Esperar a que el servidor responda
echo "Esperando a que el daemon de Ollama inicie..."
until ollama list > /dev/null 2>&1; do
  sleep 2
done

# Descargar el modelo
echo "Descargando modelo nomic-embed-text..."
ollama pull nomic-embed-text

echo "Ollama está listo y el modelo ha sido descargado."

# Mantener el proceso en primer plano
wait
