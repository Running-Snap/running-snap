from celery import Celery

celery_app = Celery(
    "running_diary",
    broker="redis://localhost:6379/0",
    backend="redis://localhost:6379/0",
    include=[
        "services.analysis",
        "services.bestcut",
        "services.cert",
        "services.coaching",
        "services.pose_video",
        "services.shortform",
        "services.matching",
        "services.ocr_classifier",
    ],
)

celery_app.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    timezone="Asia/Seoul",
    enable_utc=True,
    task_track_started=True,
    worker_prefetch_multiplier=1,   # 작업 1개씩만 가져옴 (공정 분배)
    task_acks_late=True,            # 작업 완료 후 ACK (재시작 시 재처리)
)
