# Copyright 2026 MSPbots.ai
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
"""Process settings. Holds no credentials: those arrive per request as headers."""

from pydantic_settings import BaseSettings, SettingsConfigDict

# Default API host for Sentry SaaS; self-hosted instances override via
# X-Sentry-Base-URL. API_PATH is the versioned REST root under that host.
DEFAULT_BASE_URL = "https://sentry.io"
API_PATH = "/api/0"
DEFAULT_PAGE_SIZE = 50
# Sentry's own documented cap for paginated list endpoints.
MAX_PAGE_SIZE = 100


class Settings(BaseSettings):
    # extra="ignore": the runtime injects variables this project does not declare.
    model_config = SettingsConfigDict(extra="ignore")

    mcp_http_port: int = 8080
    mcp_http_host: str = "0.0.0.0"
    log_level: str = "INFO"


def get_settings() -> Settings:
    return Settings()
