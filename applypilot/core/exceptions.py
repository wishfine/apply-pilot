class ApplyPilotError(Exception):
    """ApplyPilot 根异常"""

class ConfigurationError(ApplyPilotError):
    """配置加载异常"""

class DomainValidationError(ApplyPilotError):
    """领域模型校验异常"""

class StorageError(ApplyPilotError):
    """存储与数据库异常"""

class BrowserDriverError(ApplyPilotError, ValueError):
    """浏览器底层驱动异常"""

class AdapterError(ApplyPilotError):
    """适配器执行异常"""
