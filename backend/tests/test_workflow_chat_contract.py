"""Model request settings configured in workflow nodes reach the provider."""
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

from fastapi import HTTPException

from app.schemas.chat import ChatRequest
from app.services.chat.service import ChatService


class WorkflowChatContract(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        provider = SimpleNamespace(api_key="fixture", is_active=True, protocol="openai", base_url="https://model.test/v1", name="test")
        self.provider_patch = patch("app.services.chat.service.ModelProviderRepository.get_by_id", return_value=provider)
        self.provider_patch.start()
        self.addCleanup(self.provider_patch.stop)

    async def test_stop_words_reach_provider(self):
        response = MagicMock(status_code=200)
        response.json.return_value = {"choices": [{"message": {"content": "answer"}}]}
        client = AsyncMock()
        client.post.return_value = response
        client.__aenter__.return_value = client
        req = ChatRequest(provider_id=1, model="test", message="hi", stop_words=["END", "STOP"])
        with patch("app.services.chat.service.httpx.AsyncClient", return_value=client):
            await ChatService.send_chat(None, req)
        self.assertEqual(client.post.call_args.kwargs["json"]["stop"], ["END", "STOP"])

    async def test_provider_status_preserved_for_retry_decision(self):
        client = AsyncMock()
        client.post.return_value = MagicMock(status_code=429, text="rate limited")
        client.__aenter__.return_value = client
        with patch("app.services.chat.service.httpx.AsyncClient", return_value=client):
            with self.assertRaises(HTTPException) as error:
                await ChatService.send_chat(None, ChatRequest(provider_id=1, model="test", message="hi"))
        self.assertEqual(error.exception.status_code, 429)
        self.assertIn("rate limited", error.exception.detail)

    async def test_no_stop_setting_omits_provider_parameter(self):
        response = MagicMock(status_code=200)
        response.json.return_value = {"choices": [{"message": {"content": "answer"}}]}
        client = AsyncMock()
        client.post.return_value = response
        client.__aenter__.return_value = client
        with patch("app.services.chat.service.httpx.AsyncClient", return_value=client):
            await ChatService.send_chat(None, ChatRequest(provider_id=1, model="test", message="hi"))
        self.assertNotIn("stop", client.post.call_args.kwargs["json"])


if __name__ == "__main__":
    unittest.main()
