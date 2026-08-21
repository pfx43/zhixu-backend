import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from app.services.llm.llm_config import create_base_api, load_llm_settings


class LlmConfigurationTests(unittest.TestCase):
    def test_process_environment_can_construct_base_api_without_tina_env(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            missing_env = Path(temp_dir) / "missing-tina.env"
            with patch.dict(
                os.environ,
                {
                    "LLM_API_KEY": "runtime-key",
                    "BASE_URL": "https://llm.example.test/v1",
                    "MODEL_NAME": "runtime-model",
                },
                clear=False,
            ):
                llm = create_base_api(env_path=missing_env)

        self.assertEqual(llm.base_url, "https://llm.example.test/v1")
        self.assertEqual(llm.model, "runtime-model")

    def test_tina_env_is_used_when_process_environment_is_absent(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            env_path = Path(temp_dir) / "tina.env"
            env_path.write_text(
                "LLM_API_KEY=file-key\n"
                "BASE_URL=https://file.example.test/v1\n"
                "MODEL_NAME=file-model\n",
                encoding="utf-8",
            )
            with patch.dict(os.environ, {}, clear=True):
                settings = load_llm_settings(env_path=env_path)

        self.assertTrue(settings.is_ready)
        self.assertEqual(settings.api_key, "file-key")
        self.assertEqual(settings.base_url, "https://file.example.test/v1")
        self.assertEqual(settings.model_name, "file-model")

    def test_process_environment_configures_llm_without_tina_env(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            missing_env = Path(temp_dir) / "missing-tina.env"
            with patch.dict(
                os.environ,
                {
                    "LLM_API_KEY": "runtime-key",
                    "BASE_URL": "https://llm.example.test/v1",
                    "MODEL_NAME": "runtime-model",
                },
                clear=False,
            ):
                settings = load_llm_settings(env_path=missing_env)

        self.assertTrue(settings.is_ready)
        self.assertEqual(settings.api_key, "runtime-key")
        self.assertEqual(settings.base_url, "https://llm.example.test/v1")
        self.assertEqual(settings.model_name, "runtime-model")

    def test_process_environment_overrides_tina_env(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            env_path = Path(temp_dir) / "tina.env"
            env_path.write_text(
                "LLM_API_KEY=file-key\n"
                "BASE_URL=https://file.example.test/v1\n"
                "MODEL_NAME=file-model\n",
                encoding="utf-8",
            )
            with patch.dict(
                os.environ,
                {
                    "LLM_API_KEY": "runtime-key",
                    "BASE_URL": "https://runtime.example.test/v1",
                    "MODEL_NAME": "runtime-model",
                },
                clear=False,
            ):
                settings = load_llm_settings(env_path=env_path)

        self.assertEqual(settings.api_key, "runtime-key")
        self.assertEqual(settings.base_url, "https://runtime.example.test/v1")
        self.assertEqual(settings.model_name, "runtime-model")


if __name__ == "__main__":
    unittest.main()
