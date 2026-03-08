from open_uplift.providers.base import SessionProvider
from open_uplift.providers.claude_code import ClaudeCodeProvider
from open_uplift.providers.codex import CodexProvider

_BUILTIN_PROVIDERS: list[SessionProvider] = [ClaudeCodeProvider(), CodexProvider()]


def get_all_providers() -> list[SessionProvider]:
    """Return all registered session providers."""
    return list(_BUILTIN_PROVIDERS)


# Backward compatibility
ALL_PROVIDERS = _BUILTIN_PROVIDERS
