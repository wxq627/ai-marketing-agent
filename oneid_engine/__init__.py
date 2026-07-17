"""
OneID 统一融合引擎 — 模块二
=============================
将同一客户在不同业务系统中的多个标识符统一映射为全局唯一 OneID。

核心模块:
  - id_mapping_store  : 映射表存储与查询
  - id_resolver       : OneID 生成与解析算法
  - conflict_detector : ID 冲突检测与处理
  - router_id         : FastAPI REST 接口
"""

__version__ = "1.0.0"
