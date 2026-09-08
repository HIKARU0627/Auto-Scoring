"""Tests for `auto_scoring.api.secret_redaction` -- the one rule for "a
configuration value must not be published" (Issue #97, review rounds 1/2).

The rule is a length threshold over this app's own variable namespace, not a
list of "the secret-looking variables". The leak that prompted it was a key
in ``AUTO_SCORING_VERTEX_PROJECT`` -- a variable no name-based list would
have covered -- reaching the sidecar log through the request URL the Vertex
adapter builds from it.
"""

from __future__ import annotations

from auto_scoring.api.secret_redaction import REDACTED, configuration_secrets, redact


class TestConfigurationSecrets:
    def test_a_long_value_is_a_secret_whatever_variable_it_came_from(self) -> None:
        assert configuration_secrets(
            {"AUTO_SCORING_VERTEX_PROJECT": "sk-pasted-into-the-wrong-variable"}
        ) == ("sk-pasted-into-the-wrong-variable",)

    def test_a_credential_variable_is_a_secret_however_short_its_value(self) -> None:
        assert configuration_secrets({"AUTO_SCORING_OPENAI_API_KEY": "short"}) == ("short",)

    def test_short_structural_values_are_left_alone(self) -> None:
        """A log with ``v1``, ``0.0`` and ``global`` scrubbed out of every
        line it appears in is not a log any more -- and none of these is a
        credential anyone could paste by accident and lose."""
        assert (
            configuration_secrets(
                {
                    "AUTO_SCORING_AI_GRADING_PROMPT_VERSION": "v1",
                    "AUTO_SCORING_AI_GRADING_TEMPERATURE": "0.0",
                    "AUTO_SCORING_VERTEX_LOCATION": "global",
                    "AUTO_SCORING_CODEX_EXECUTABLE": "codex",
                }
            )
            == ()
        )

    def test_other_processes_configuration_is_not_scanned(self) -> None:
        """Only this app's namespace. Scrubbing `PATH` or a shell variable
        out of every line would wreck the log to protect something this
        process never sent anywhere."""
        assert configuration_secrets({"PATH": "/usr/local/bin:/usr/bin", "HOME": "/root"}) == ()

    def test_blank_values_never_become_a_pattern(self) -> None:
        """An empty or whitespace-only value must not turn into a scrub
        pattern -- replacing "" would rewrite every character of every
        line."""
        assert configuration_secrets({"AUTO_SCORING_OPENAI_API_KEY": "   "}) == ()

    def test_longest_first_so_nothing_is_half_replaced(self) -> None:
        secrets = configuration_secrets(
            {
                "AUTO_SCORING_OPENROUTER_MODEL": "vendor/model-name",
                "AUTO_SCORING_GEMINI_MODEL": "vendor/model",
            }
        )
        assert secrets == ("vendor/model-name", "vendor/model")


class TestRedact:
    def test_replaces_every_occurrence_of_every_secret(self) -> None:
        text = "url=https://host/projects/alpha-secret/models/beta-secret:run"

        assert redact(text, ("alpha-secret", "beta-secret")) == (
            f"url=https://host/projects/{REDACTED}/models/{REDACTED}:run"
        )

    def test_a_longer_secret_containing_a_shorter_one_is_replaced_whole(self) -> None:
        """`configuration_secrets` orders longest first for this: replacing
        the short one first would leave the rest of the long one behind, in
        the log, next to a ``***`` that makes it look handled."""
        secrets = configuration_secrets(
            {
                "AUTO_SCORING_OPENROUTER_MODEL": "vendor/model-name",
                "AUTO_SCORING_GEMINI_MODEL": "vendor/model",
            }
        )

        assert redact("using vendor/model-name today", secrets) == f"using {REDACTED} today"

    def test_no_secrets_leaves_the_text_untouched(self) -> None:
        assert redact("nothing to hide", ()) == "nothing to hide"
