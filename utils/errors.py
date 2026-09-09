# utils/errors.py
class LLMError(Exception):
    """Base LLM error"""
    pass

class ToolExecutionError(Exception):
    """Tool execution failed"""
    pass

class AgentError(Exception):
    """Agent processing failed"""
    pass