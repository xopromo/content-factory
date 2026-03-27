"""
Threads Comment Agent - автоматический комментариатор для Threads
"""

from .agent import ThreadsCommentAgent
from .models import LocalLLM
from .threads_connector import ThreadsConnector, ThreadsSearcher

__version__ = "0.1.0"
__author__ = "Your Name"

__all__ = [
    "ThreadsCommentAgent",
    "LocalLLM",
    "ThreadsConnector",
    "ThreadsSearcher",
]
