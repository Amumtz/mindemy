# app/tasks/__init__.py
"""
Celery tasks package.
"""

from .training_tasks import make_celery, register_train_task

__all__ = ["make_celery", "register_train_task"]