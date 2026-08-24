"""中文：本模块负责实现“测试软件包”相关功能。

English: Initial package-level smoke test.
"""

from enterprise_rag import __version__


def test_package_version() -> None:
    """中文：该测试用于验证“软件包版本”相关行为。

    English: Ensure the installed package exposes the expected V0.3 RC2 version.
    """

    assert __version__ == "0.3.0rc2"
