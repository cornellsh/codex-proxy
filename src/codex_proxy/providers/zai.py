import time
import logging
import requests
from typing import Dict, Any
from .base import BaseProvider
from ..utils import create_session, json_loads, json_dumps
from ..config import config
from .zai_stream import stream_responses_loop

logger = logging.getLogger(__name__)


class ZAIProvider(BaseProvider):
    """Provider for Z.AI GLM models."""

    def __init__(self):
        self.session = create_session()

    def handle_request(self, data: Dict[str, Any], handler: Any) -> None:
        """Entry point for Z.AI requests."""
        payload = self._prepare_payload(data)
        self._transform_payload(payload)
        self._execute_request(payload, data, handler)

    def _prepare_payload(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Create a clean payload with only supported parameters."""
        payload = {
            "model": data.get("model"),
            "messages": data.get("messages", []),
            "stream": data.get("stream", False),
        }
        if "tools" in data:
            payload["tools"] = data["tools"]
        if "tool_choice" in data:
            payload["tool_choice"] = data["tool_choice"]
        if "temperature" in data:
            payload["temperature"] = data["temperature"]
        if "top_p" in data:
            payload["top_p"] = data["top_p"]
        if "max_tokens" in data:
            payload["max_tokens"] = data["max_tokens"]
        return payload

    def _transform_payload(self, payload: Dict[str, Any]) -> None:
        """Apply Z.AI specific transformations."""
        # 1. Fix Roles
        for m in payload.get("messages", []):
            if m.get("role") == "developer":
                m["role"] = "system"

        # 2. Transform and Clean Tools
        if "tools" in payload and payload["tools"]:
            transformed_tools = []
            for tool in payload["tools"]:
                ttype = tool.get("type")
                if ttype == "function":
                    # Remove non-standard "strict" property
                    if "strict" in tool:
                        del tool["strict"]
                    transformed_tools.append(tool)
                elif ttype == "web_search":
                    # Transform Codex web_search to Z.AI format
                    transformed_tools.append(
                        {
                            "type": "web_search",
                            "web_search": {
                                "enable": True,
                                "search_engine": "search_pro_jina",
                            },
                        }
                    )
                # Drop retrieval for now as it needs knowledge_id

            payload["tools"] = transformed_tools

    def _execute_request(
        self, payload: Dict[str, Any], original_data: Dict[str, Any], handler: Any
    ) -> None:
        """Perform the actual API call and handle response."""
        auth_header = handler.headers.get("Authorization")
        if config.z_ai_api_key:
            auth_header = f"Bearer {config.z_ai_api_key}"

        stream = payload.get("stream", False)

        try:
            with self.session.post(
                config.z_ai_url,
                json=payload,
                headers={"Authorization": auth_header} if auth_header else {},
                stream=stream,
                timeout=(config.request_timeout_connect, config.request_timeout_read),
            ) as resp:
                logger.info("Z.AI response status: %s", resp.status_code)
                if stream:
                    self._handle_stream_response(resp, payload, handler)
                else:
                    self._handle_sync_response(resp, original_data, handler)
        except Exception as e:
            logger.error(f"ZAI Request failed: {e}")
            raise e

    def _handle_stream_response(
        self, resp: requests.Response, payload: Dict[str, Any], handler: Any
    ) -> None:
        """Manage streaming response forwarding."""
        handler.send_response(resp.status_code)
        handler.send_header("Content-Type", "text/event-stream; charset=utf-8")
        handler.send_header("Connection", "keep-alive")
        handler.end_headers()

        created_ts = int(time.time())
        stream_responses_loop(resp, handler, payload["model"], created_ts, payload)

    def _handle_sync_response(
        self, resp: requests.Response, original_data: Dict[str, Any], handler: Any
    ) -> None:
        """Manage synchronous response forwarding."""
        handler.send_response(resp.status_code)
        handler.send_header("Content-Type", "application/json")
        handler.end_headers()

        if original_data.get("_is_responses_api") and resp.status_code == 200:
            try:
                self._write_mapped_response(resp, handler)
                return
            except Exception as e:
                logger.warning(f"Failed to map ZAI response: {e}")

        handler.wfile.write(resp.content)

    def _write_mapped_response(self, resp: requests.Response, handler: Any) -> None:
        """Map ZAI standard chat response to Codex Responses API format."""
        z_data = resp.json()
        choice = z_data["choices"][0]
        message = choice["message"]
        usage = z_data.get("usage", {})

        # Map tool calls if present
        output_items = []
        if "tool_calls" in message:
            for tc in message["tool_calls"]:
                item = {
                    "id": tc.get("id"),
                    "type": "function_call",
                    "status": "completed",
                    "name": tc["function"]["name"],
                    "arguments": json_dumps(tc["function"]["arguments"]),
                    "call_id": tc.get("id"),
                }
                # Parity with Gemini shell mapping
                if item["name"] in ("shell", "container.exec", "shell_command"):
                    item["type"] = "local_shell_call"
                    try:
                        args = tc["function"]["arguments"]
                        if isinstance(args, str):
                            args = json_loads(args)
                        item["action"] = {
                            "type": "exec",
                            "command": args.get("command", []),
                        }
                    except (ValueError, TypeError, KeyError):
                        pass
                output_items.append(item)

        # Map content if present
        if message.get("content"):
            output_items.append(
                {
                    "id": f"msg_{int(time.time() * 1000)}",
                    "type": "message",
                    "role": "assistant",
                    "status": "completed",
                    "content": [{"type": "text", "text": message["content"]}],
                }
            )

        resp_obj = {
            "id": f"zai_{z_data.get('id')}",
            "object": "response",
            "created": z_data.get("created"),
            "model": z_data.get("model"),
            "status": "completed",
            "usage": {
                "prompt_tokens": usage.get("prompt_tokens", 0),
                "completion_tokens": usage.get("completion_tokens", 0),
                "total_tokens": usage.get("total_tokens", 0),
            },
            "output": output_items,
        }
        handler.wfile.write(json_dumps(resp_obj))

    def handle_compact(self, data: Dict[str, Any], handler: Any) -> None:
        """Handle context compaction using configured compaction model."""
        compaction_model = data.get(
            "model", config.models[0] if config.models else "glm-4.6"
        )

        messages = data.get("input", [])
        compaction_prompt = data.get(
            "instructions", "Summarize the conversation history concisely."
        )

        messages.append(
            {
                "role": "user",
                "content": f"Perform context compaction. instructions: {compaction_prompt}",
            }
        )

        payload = {
            "model": compaction_model,
            "messages": messages,
            "stream": False,
            "temperature": config.compaction_temperature,
            "max_tokens": config.request_timeout_read,
        }

        auth_header = handler.headers.get("Authorization")
        if not auth_header and config.z_ai_api_key:
            auth_header = f"Bearer {config.z_ai_api_key}"

        try:
            with self.session.post(
                config.z_ai_url,
                json=payload,
                headers={"Authorization": auth_header} if auth_header else {},
                timeout=(config.request_timeout_connect, config.request_timeout_read),
            ) as resp:
                if resp.status_code != 200:
                    logger.error(f"Compaction request failed: {resp.status_code}")
                    handler.send_error(resp.status_code, resp.text)
                    return

                z_data = resp.json()
                choice = z_data.get("choices", [{}])[0]
                final_text = choice.get("message", {}).get("content", "")

                result = {
                    "output": [{"type": "compaction", "encrypted_content": final_text}]
                }

                handler.send_response(200)
                handler.send_header("Content-Type", "application/json")
                handler.end_headers()
                handler.wfile.write(json_dumps(result))

        except Exception as e:
            logger.error(f"Compaction failed: {e}")
            handler.send_error(500, str(e))
