import random
import shlex
import string

from pydantic import AliasChoices, Field
from pydantic_settings import (
    BaseSettings,
    CliSettingsSource,
    PydanticBaseSettingsSource,
    SettingsConfigDict,
)


def generate_random_credential(length: int = 8) -> str:
    chars = string.ascii_letters + string.digits
    return "".join(random.choice(chars) for _ in range(length))


class Settings(BaseSettings):
    forward: str = Field(description="Target address to forward (e.g., localhost:8080)")
    user: str = Field(
        default_factory=generate_random_credential, description="Basic auth username"
    )
    password: str = Field(
        default_factory=generate_random_credential,
        validation_alias=AliasChoices("password", "pass"),
        description="Basic auth password",
    )
    cloudflared: str = Field(
        default="", description="Path to cloudflared binary (default: auto-download)"
    )
    update_cloudflared: bool = Field(
        default=False, description="Update cloudflared to latest version"
    )
    qr: bool = Field(default=True, description="Display QR code with authenticated URL")
    verbose: bool = Field(default=False, description="Enable verbose logging")
    no_proxy: bool = Field(
        default=False, description="Disable proxy and Basic Auth (tunnel only)"
    )
    quiet: bool = Field(default=False, description="Suppress cloudflared tunnel logs")
    cloudflared_extra_args: str = Field(
        default="",
        description="Extra arguments passed to cloudflared (e.g., '--protocol http2')",
    )

    model_config = SettingsConfigDict(
        env_prefix="CQW_",
        env_prefix_target="all",
        case_sensitive=False,
        env_file=".env",
        extra="ignore",
    )

    @property
    def forward_url(self) -> str:
        if self.forward.startswith(("http://", "https://")):
            return self.forward
        return f"http://{self.forward}"

    @property
    def cloudflared_args_list(self) -> list[str]:
        if self.cloudflared_extra_args:
            return shlex.split(self.cloudflared_extra_args)
        return []


class CLISettings(Settings):
    model_config = SettingsConfigDict(
        cli_parse_args=True,
        cli_prog_name="cqw",
        cli_exit_on_error=True,
        cli_enforce_required=True,
        cli_shortcuts={
            "forward": "f",
            "verbose": "v",
        },
        cli_implicit_flags=True,
    )

    @classmethod
    def settings_customise_sources(
        cls,
        settings_cls: type[BaseSettings],
        init_settings: PydanticBaseSettingsSource,
        env_settings: PydanticBaseSettingsSource,
        dotenv_settings: PydanticBaseSettingsSource,
        file_secret_settings: PydanticBaseSettingsSource,
    ) -> tuple[PydanticBaseSettingsSource, ...]:
        return (
            init_settings,
            CliSettingsSource(
                settings_cls,
                cli_parse_args=True,
                cli_kebab_case=True,
            ),
            env_settings,
            dotenv_settings,
        )
