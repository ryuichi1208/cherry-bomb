from cherry_bomb.agent.prompts import SRE_SYSTEM_PROMPT, build_system_prompt


class TestBuildSystemPrompt:
    def test_without_additional_context(self) -> None:
        result = build_system_prompt()
        assert result == SRE_SYSTEM_PROMPT

    def test_with_none_context(self) -> None:
        result = build_system_prompt(additional_context=None)
        assert result == SRE_SYSTEM_PROMPT

    def test_with_additional_context(self) -> None:
        context = "インシデント #123: CPU使用率が90%を超過"
        result = build_system_prompt(additional_context=context)
        assert SRE_SYSTEM_PROMPT in result
        assert "## 追加コンテキスト" in result
        assert context in result

    def test_with_empty_string_context(self) -> None:
        """空文字列はfalsyなので追加されない"""
        result = build_system_prompt(additional_context="")
        assert result == SRE_SYSTEM_PROMPT

    def test_prompt_contains_key_sections(self) -> None:
        """システムプロンプトに主要セクションが含まれていることを確認"""
        assert "cherry-bomb" in SRE_SYSTEM_PROMPT
        assert "## 役割" in SRE_SYSTEM_PROMPT
        assert "## 行動指針" in SRE_SYSTEM_PROMPT
        assert "## 応答スタイル" in SRE_SYSTEM_PROMPT
        assert "## ツールの使い方" in SRE_SYSTEM_PROMPT

    def test_prompt_safety_first(self) -> None:
        """安全性に関する記述が含まれていることを確認"""
        assert "安全性最優先" in SRE_SYSTEM_PROMPT
        assert "承認" in SRE_SYSTEM_PROMPT
