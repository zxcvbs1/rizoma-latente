from celery import Celery
import os

# Configuración de Celery usando Redis como broker y backend
CELERY_BROKER_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")
CELERY_RESULT_BACKEND = os.getenv("REDIS_URL", "redis://localhost:6379/0")

celery_app = Celery(
    "rizoma_worker",
    broker=CELERY_BROKER_URL,
    backend=CELERY_RESULT_BACKEND,
    include=["apps.worker.tasks"] # Importante para registrar las tareas
)

# Configuración de tareas periódicas (Beat)
celery_app.conf.beat_schedule = {
    "nightly-mass-decay": {
        "task": "apps.worker.tasks.nightly_decay",
        "schedule": 86400.0, # Una vez cada 24 horas
    },
}

celery_app.conf.timezone = "UTC"
