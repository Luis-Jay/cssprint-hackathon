import json
import unittest

import httpx

from utils.llm_client import Settings, GeminiClient


def make_client(handler, **overrides):
    settings = Settings(gemini_api_key="test-key",
                        gemini_model_id="gemini-test",
                        gemini_thinking_budget="0", **overrides)
    http = httpx.Client(transport=httpx.MockTransport(handler))
    return GeminiClient(settings, http_client=http)


def reply(text, finish="STOP"):
    return httpx.Response(200, json={
        "candidates": [{"content": {"parts": [{"text": text}]},
                        "finishReason": finish}],
        "usageMetadata": {"promptTokenCount": 10, "candidatesTokenCount": 5},
    })


class GeminiClientTests(unittest.TestCase):
    def test_request_shape(self):
        seen = {}

        def handler(request):
            seen["url"] = str(request.url)
            seen["key"] = request.headers.get("x-goog-api-key")
            seen["body"] = json.loads(request.content)
            return reply('{"verdict": "recognized"}')

        client = make_client(handler)
        result = client.invoke_model(
            "Check this", system_prompt="You check IDs", max_tokens=512,
            attachments=[{"kind": "image", "media_type": "image/jpeg", "data": "QUJD"}],
        )

        self.assertEqual(result["content"], '{"verdict": "recognized"}')
        self.assertTrue(seen["url"].endswith("/models/gemini-test:generateContent"))
        self.assertNotIn("test-key", seen["url"])
        self.assertEqual(seen["key"], "test-key")
        parts = seen["body"]["contents"][0]["parts"]
        self.assertEqual(parts[0]["inline_data"]["mime_type"], "image/jpeg")
        self.assertEqual(parts[-1]["text"], "Check this")
        self.assertEqual(seen["body"]["systemInstruction"]["parts"][0]["text"],
                         "You check IDs")
        config = seen["body"]["generationConfig"]
        self.assertEqual(config["maxOutputTokens"], 512)
        self.assertEqual(config["thinkingConfig"], {"thinkingBudget": 0})

    def test_empty_answer_raises(self):
        client = make_client(lambda r: reply("", finish="MAX_TOKENS"))
        with self.assertRaises(Exception) as ctx:
            client.invoke_model("hi")
        self.assertIn("MAX_TOKENS", str(ctx.exception))

    def test_busy_model_falls_back(self):
        calls = []

        def handler(request):
            calls.append(request.url.path)
            if "gemini-test" in request.url.path:
                return httpx.Response(503, text="high demand")
            return reply("from fallback")

        client = make_client(handler, gemini_fallback_model_id="gemini-backup")
        self.assertEqual(client.invoke_model("hi")["content"], "from fallback")
        self.assertEqual(len(calls), 2)
        self.assertIn("gemini-backup", calls[1])

    def test_timeout_falls_back(self):
        def handler(request):
            if "gemini-test" in request.url.path:
                raise httpx.ReadTimeout("slow", request=request)
            return reply("from fallback")

        client = make_client(handler, gemini_fallback_model_id="gemini-backup")
        self.assertEqual(client.invoke_model("hi")["content"], "from fallback")

    def test_http_error_raises(self):
        client = make_client(lambda r: httpx.Response(429, text="quota exceeded"))
        with self.assertRaises(Exception) as ctx:
            client.invoke_model("hi")
        self.assertIn("429", str(ctx.exception))


if __name__ == "__main__":
    unittest.main()
