import unittest

from services.ai import (
    _coerce_ai_payload,
    contains_crisis_language,
    fallback_comeback_response,
)


class AiServiceTests(unittest.TestCase):
    def test_crisis_language_detects_self_harm(self):
        self.assertTrue(contains_crisis_language("я не хочу жить"))
        self.assertTrue(contains_crisis_language("I might kill myself"))

    def test_fallback_uses_existing_task_as_next_action(self):
        payload = fallback_comeback_response(
            user_profile={
                "goal": {"title": "найти первую IT работу", "why": "нужна независимость"},
                "profile": {"blocker_pattern": "стыд"},
            },
            active_tasks=[{"text": "отправить одно резюме"}],
            trigger={"blocker": "страх"},
        )

        self.assertEqual(payload["next_action"], "отправить одно резюме")
        self.assertIn("найти первую IT работу", payload["message"])
        self.assertIn("Готов", payload["message"])

    def test_coerce_ai_payload_reads_json(self):
        fallback = {"message": "fallback", "next_action": "fallback", "source": "fallback"}
        payload = _coerce_ai_payload(
            '{"message": "Сделай один шаг. Готов?", "next_action": "открыть IDE"}',
            fallback,
        )

        self.assertEqual(payload["source"], "groq")
        self.assertEqual(payload["next_action"], "открыть IDE")


if __name__ == "__main__":
    unittest.main()
