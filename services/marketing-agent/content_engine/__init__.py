"""
文件路径: d:\库文件\桌面\Summer_Intern\c_marketing_agent\content_engine\__init__.py
功能描述: 内容引擎模块导出
"""

from .templates import ContentTemplate, get_template, INSTALLMENT_TEMPLATES, BENEFIT_TEMPLATES, ACTIVITY_TEMPLATES
from .generator import GeneratedContent, ContentGenerator, content_generator

__all__ = [
    "ContentTemplate",
    "GeneratedContent",
    "ContentGenerator",
    "get_template",
    "INSTALLMENT_TEMPLATES",
    "BENEFIT_TEMPLATES",
    "ACTIVITY_TEMPLATES",
    "content_generator",
]