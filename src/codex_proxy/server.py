import json
import logging
import socket
from http.server import HTTPServer, BaseHTTPRequestHandler
from socketserver import ThreadingMixIn
from typing import Dict, cast

from .config import config
from .exceptions import ProxyError, ProviderError, ValidationError
from .providers.base import BaseProvider
from .providers.gemini import GeminiProvider
from .providers.zai import ZAIProvider
from .normalizer import RequestNormalizer
from .utils import json_loads
from .validator import RequestValidator
from . import ui as _ui

logger = logging.getLogger(__name__)


class ProviderRegistry:
    """Registry for AI model providers."""

    _providers: Dict[str, BaseProvider] = {}

    @classmethod
    def register(cls, prefix: str, provider: BaseProvider):
        cls._providers[prefix] = provider

    @classmethod
    def get_provider(cls, model_name: str) -> BaseProvider:
        for prefix, provider in cls._providers.items():
            if model_name.startswith(prefix):
                return provider
        # Default to ZAI if no match
        return cast(BaseProvider, cls._providers.get("zai"))

    @classmethod
    def initialize_from_config(cls):
        """Initialize provider registry from configuration."""
        cls._providers.clear()

        cls.register("gemini", GeminiProvider())
        cls.register("zai", ZAIProvider())

        for prefix, provider_key in config.model_prefixes.items():
            if prefix in cls._providers:
                continue
            if provider_key == "gemini":
                cls.register(prefix, GeminiProvider())
            elif provider_key == "zai":
                cls.register(prefix, ZAIProvider())


# Initialize registry
ProviderRegistry.initialize_from_config()


class ThreadedHTTPServer(ThreadingMixIn, HTTPServer):
    """Multi-threaded HTTP server with performance optimizations."""

    daemon_threads = True
    allow_reuse_address = True

    def server_bind(self):
        super().server_bind()
        try:
            self.socket.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
        except Exception as e:
            logger.warning(f"Failed to set TCP_NODELAY: {e}")


class ProxyRequestHandler(BaseHTTPRequestHandler):
    """Handles incoming Codex requests and routes them to appropriate providers."""

    def do_GET(self):
        if self.path in ("/", "/ui"):
            body = _ui.get_html()
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        elif self.path == "/config":
            body = json.dumps(_ui.get_current_config()).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        else:
            self.send_error(404, "Not found")

    def do_POST(self):
        try:
            self._handle_post()
        except ValidationError as e:
            logger.error(f"Validation error: {e}", exc_info=True)
            self.send_error(400, str(e))
        except ProviderError as e:
            logger.error(f"Provider error: {e}", exc_info=True)
            self.send_error(502, str(e))
        except (json.JSONDecodeError, KeyError, ValueError) as e:
            logger.error(f"Invalid request: {e}", exc_info=True)
            self.send_error(400, f"Invalid request: {e}")
        except ProxyError as e:
            logger.error(f"Proxy error: {e}", exc_info=True)
            self.send_error(500, str(e))
        except Exception as e:
            logger.critical(f"Unexpected error: {e}", exc_info=True)
            self.send_error(500, "Internal server error")

    def _handle_post(self):
        logger.info(f"POST {self.path}")

        # Config UI save endpoint
        if self.path == "/config":
            content_length = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(content_length) if content_length else b"{}"
            try:
                data = json_loads(body)
                result = _ui.apply_and_save(data)
                resp = json.dumps(result).encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(resp)))
                self.end_headers()
                self.wfile.write(resp)
            except (ValueError, TypeError) as e:
                err = json.dumps({"error": str(e)}).encode("utf-8")
                self.send_response(400)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(err)))
                self.end_headers()
                self.wfile.write(err)
            return

        if self.path not in (
            "/v1/responses",
            "/responses",
            "/v1/responses/compact",
            "/responses/compact",
        ):
            self.send_error(404, f"Endpoint {self.path} not supported.")
            return

        content_length = int(self.headers.get("Content-Length", 0))
        if content_length == 0:
            self.send_error(400, "Empty body")
            return

        body = self.rfile.read(content_length)
        if config.debug_mode:
            logger.debug(f"RAW REQUEST: {body.decode('utf-8', errors='replace')}")

        try:
            data = json_loads(body)
        except (json.JSONDecodeError, ValueError) as e:
            raise ValidationError(f"Invalid JSON: {e}")

        # Validate request
        RequestValidator.validate_request(data, self.path)

        # Attach context headers
        data["_headers"] = {
            "session_id": self.headers.get("session_id"),
            "x-openai-subagent": self.headers.get("x-openai-subagent"),
            "x-codex-turn-state": self.headers.get("x-codex-turn-state"),
            "x-codex-personality": self.headers.get("x-codex-personality"),
        }

        # Normalize request if it's a standard responses call
        is_compact = "/compact" in self.path
        if not is_compact:
            data = RequestNormalizer.normalize(data)
            data["_is_responses_api"] = True

        # For compaction requests, use configured compaction_model to determine provider
        # This ensures compaction works regardless of what model the user has selected
        if is_compact:
            compaction_model = config.compaction_model
            if not compaction_model:
                compaction_model = (
                    config.models[0] if config.models else "gemini-2.5-flash-lite"
                )
            provider = ProviderRegistry.get_provider(compaction_model)
            provider.handle_compact(data, self)
        else:
            model = data.get("model", "")
            provider = ProviderRegistry.get_provider(model)
            provider.handle_request(data, self)

        self.close_connection = True

    def do_OPTIONS(self):
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, Authorization")
        self.end_headers()

    def log_message(self, format, *args):
        """Override to suppress default logging to stdout."""
        pass


def run_server():
    server_address = (config.host, config.port)
    httpd = ThreadedHTTPServer(server_address, ProxyRequestHandler)
    logger.info(f"Listening on {config.host}:{config.port}")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        logger.info("Shutting down")
        httpd.server_close()


if __name__ == "__main__":
    run_server()
