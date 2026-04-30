"""ClearFrame LLM providers."""

__all__ = ["OllamaProvider"]

def __getattr__(name: str):
    if name == "OllamaProvider":
        from clearframe.providers.ollama import OllamaProvider
        return OllamaProvider
    raise AttributeError(f"module 'clearframe.providers' has no attribute {name!r}")
