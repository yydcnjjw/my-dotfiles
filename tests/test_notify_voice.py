import json
import importlib.util
import importlib.machinery
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import types
import unittest
from unittest import mock
from urllib import error


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "dot_local" / "bin" / "executable_notify-voice"
LOCAL_NOTIFY_SCRIPT = ROOT / "dot_local" / "bin" / "executable_local-notify"
REMOTE_NOTIFY_SCRIPT = ROOT / "dot_local" / "bin" / "executable_remote-notify"
OPENCODE_NOTIFY_SCRIPT = ROOT / "dot_local" / "bin" / "executable_opencode-notify"
GEMINI_NOTIFY_SCRIPT = ROOT / "dot_gemini" / "executable_notify.sh"


def load_module():
    loader = importlib.machinery.SourceFileLoader("notify_voice", str(SCRIPT))
    spec = importlib.util.spec_from_file_location("notify_voice", SCRIPT, loader=loader)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


class NotifyVoicePureLogicTest(unittest.TestCase):
    def setUp(self):
        self.module = load_module()

    def test_cache_key_includes_text_and_tts_parameters(self):
        first = self.module.cache_key("通知があります", "http://localhost:8000/tts", "wav")
        second = self.module.cache_key("通知があります", "http://localhost:9000/tts", "wav")
        self.assertNotEqual(first, second)
        self.assertEqual(len(first), 64)

    def test_cache_dir_uses_xdg_cache_home(self):
        with tempfile.TemporaryDirectory() as tmp:
            env = {"XDG_CACHE_HOME": tmp}
            self.assertEqual(self.module.cache_dir(env), Path(tmp) / "notify-voice")

    def test_cache_dir_falls_back_to_home_cache(self):
        env = {"HOME": "/tmp/example-home"}
        self.assertEqual(self.module.cache_dir(env), Path("/tmp/example-home/.cache/notify-voice"))

    def test_prune_cache_keeps_newest_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp)
            for index in range(55):
                path = directory / f"{index:02d}.wav"
                path.write_bytes(b"audio")
                os.utime(path, (index, index))

            self.module.prune_cache(directory, max_files=50)

            remaining = sorted(path.name for path in directory.iterdir())
            self.assertEqual(len(remaining), 50)
            self.assertEqual(remaining[0], "05.wav")
            self.assertEqual(remaining[-1], "54.wav")

    def test_prune_cache_skips_temp_files_and_still_limits_final_audio_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp)
            for index in range(55):
                path = directory / f"{index:02d}.wav"
                path.write_bytes(b"audio")
                os.utime(path, (index, index))

            ignored_path = directory / "note.mp3"
            ignored_path.write_bytes(b"legacy")

            temp_path = directory / ".voice.wav.random.tmp"
            temp_path.write_bytes(b"partial")
            os.utime(temp_path, (0, 0))

            self.module.prune_cache(directory, max_files=50)

            remaining_audio = sorted(path.name for path in directory.glob("*.wav"))
            self.assertEqual(len(remaining_audio), 50)
            self.assertEqual(remaining_audio[0], "05.wav")
            self.assertEqual(remaining_audio[-1], "54.wav")
            self.assertTrue(temp_path.exists())
            self.assertTrue(ignored_path.exists())

    def test_player_command_uses_first_available_builtin_player(self):
        command = self.module.player_command(lambda name: "/usr/bin/mpv" if name == "mpv" else None)
        self.assertEqual(command, ["mpv", "--no-terminal", "--really-quiet"])

    def test_player_command_falls_back_to_aplay(self):
        command = self.module.player_command(lambda name: "/usr/bin/aplay" if name == "aplay" else None)
        self.assertEqual(command, ["aplay", "-q"])

    def test_prompt_contains_summary_body_and_japanese_instruction(self):
        prompt = self.module.build_polish_prompt("OpenCode - Notification", "Task finished")
        self.assertIn("OpenCode - Notification", prompt)
        self.assertIn("Task finished", prompt)
        self.assertIn("日本語", prompt)
        self.assertIn("簡潔", prompt)

    def test_build_github_models_request_contains_model_and_messages(self):
        payload = self.module.build_github_models_request(
            "gpt-4o-mini",
            "OpenCode - Notification",
            "Task finished",
        )
        body = json.loads(payload.decode("utf-8"))
        self.assertEqual(body["model"], "gpt-4o-mini")
        self.assertEqual(body["temperature"], 0.2)
        self.assertEqual(body["messages"][0]["role"], "system")
        self.assertIn("short Japanese sentence", body["messages"][0]["content"])
        self.assertIn("speech", body["messages"][0]["content"])
        self.assertEqual(body["messages"][1]["role"], "user")
        self.assertIn("OpenCode - Notification", body["messages"][1]["content"])
        self.assertIn("Task finished", body["messages"][1]["content"])
        self.assertIn("日本語", body["messages"][1]["content"])
        self.assertIn("簡潔", body["messages"][1]["content"])

    def test_github_models_request_posts_json_with_expected_headers(self):
        response = object()
        with mock.patch("urllib.request.urlopen", return_value=response) as urlopen:
            result = self.module.github_models_request(b'{"model":"gpt-4o-mini"}', "token")

        self.assertIs(result, response)
        urlopen.assert_called_once()

        req = urlopen.call_args.args[0]
        self.assertEqual(req.full_url, "https://models.inference.ai.azure.com/chat/completions")
        self.assertEqual(req.get_method(), "POST")
        self.assertEqual(req.get_header("Authorization"), "Bearer token")
        self.assertEqual(req.get_header("Content-type"), "application/json")
        self.assertEqual(req.get_header("Accept"), "application/json")
        self.assertEqual(urlopen.call_args.kwargs["timeout"], 8)

    def test_clean_spoken_text_uses_fallback_for_empty_output(self):
        self.assertEqual(self.module.clean_spoken_text("\n  \n"), self.module.FALLBACK_TEXT)

    def test_clean_spoken_text_returns_first_non_empty_line(self):
        self.assertEqual(self.module.clean_spoken_text("完了しました。\n説明"), "完了しました。")

    def test_audio_path_uses_wav_extension(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = self.module.audio_path(Path(tmp), "abc123")
            self.assertEqual(path, Path(tmp) / "abc123.wav")

    def test_build_local_tts_request_contains_fixed_payload(self):
        payload = self.module.build_local_tts_request("アンタ、バカなの？")
        body = json.loads(payload.decode("utf-8"))
        self.assertEqual(
            body,
            {
                "text": "アンタ、バカなの？",
                "lang": "Japanese",
                "translate": False,
            },
        )

    def test_local_tts_request_posts_json_to_default_url(self):
        response = object()
        with mock.patch("urllib.request.urlopen", return_value=response) as urlopen:
            result = self.module.local_tts_request(b'{"text":"a"}')

        self.assertIs(result, response)
        urlopen.assert_called_once()

        req = urlopen.call_args.args[0]
        self.assertEqual(req.full_url, "http://localhost:8000/tts")
        self.assertEqual(req.get_method(), "POST")
        self.assertEqual(req.get_header("Content-type"), "application/json")
        self.assertEqual(urlopen.call_args.kwargs["timeout"], self.module.LOCAL_TTS_TIMEOUT_SECONDS)

    def test_local_tts_request_uses_env_override_url(self):
        response = object()
        with mock.patch.dict(os.environ, {"NOTIFY_VOICE_TTS_URL": "http://localhost:9000/custom"}, clear=True), \
             mock.patch("urllib.request.urlopen", return_value=response) as urlopen:
            self.module.local_tts_request(b'{"text":"a"}')

        req = urlopen.call_args.args[0]
        self.assertEqual(req.full_url, "http://localhost:9000/custom")

    def test_synthesize_to_file_writes_wav_and_removes_partial_temp_file_on_error(self):
        class BrokenResponse:
            status = 200

            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc, traceback):
                return False

            def read(self):
                return b""

            def getheader(self, name, default=None):
                return default

        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "voice.wav"
            with mock.patch.object(self.module, "local_tts_request", return_value=BrokenResponse()):
                self.assertFalse(self.module.synthesize_to_file("text", path))

            self.assertFalse(path.exists())
            self.assertEqual(list(Path(tmp).iterdir()), [])

    def test_synthesize_to_file_uses_unique_temp_paths_for_local_tts(self):
        temp_paths = [
            Path("/tmp/notify-voice-first.tmp"),
            Path("/tmp/notify-voice-second.tmp"),
        ]
        named_tempfile_paths = []
        replace_calls = []

        class FakeResponse:
            status = 200

            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc, traceback):
                return False

            def read(self):
                return b"RIFF....WAVEfmt "

            def getheader(self, name, default=None):
                if name.lower() == "content-type":
                    return "audio/wav"
                return default

        class FakeNamedTemporaryFile:
            def __init__(self, path):
                self.name = str(path)
                self.closed = False

            def close(self):
                self.closed = True
                named_tempfile_paths.append(Path(self.name))
                Path(self.name).write_bytes(b"")

        def fake_local_tts_request(_payload):
            return FakeResponse()

        def fake_named_temporary_file(*args, **kwargs):
            return FakeNamedTemporaryFile(temp_paths[len(named_tempfile_paths)])

        def fake_replace(src, dst):
            src_path = Path(src)
            dst_path = Path(dst)
            replace_calls.append((src_path, dst_path))
            dst_path.write_bytes(src_path.read_bytes())
            src_path.unlink()

        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "voice.wav"
            with mock.patch.object(self.module, "local_tts_request", side_effect=fake_local_tts_request, create=True), \
                 mock.patch("tempfile.NamedTemporaryFile", side_effect=fake_named_temporary_file), \
                 mock.patch("os.replace", side_effect=fake_replace):
                self.assertTrue(self.module.synthesize_to_file("text", path))
                self.assertTrue(self.module.synthesize_to_file("text", path))

            self.assertEqual(path.read_bytes(), b"RIFF....WAVEfmt ")
            self.assertEqual(named_tempfile_paths, temp_paths)
            self.assertEqual(len(replace_calls), 2)
            self.assertEqual(replace_calls[0], (temp_paths[0], path))
            self.assertEqual(replace_calls[1], (temp_paths[1], path))
            self.assertNotEqual(replace_calls[0][0], replace_calls[1][0])
            self.assertEqual([entry.name for entry in Path(tmp).iterdir()], ["voice.wav"])

    def test_synthesize_to_file_accepts_wav_content_type_and_valid_header(self):
        class ValidWavResponse:
            status = 200

            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc, traceback):
                return False

            def read(self):
                return b"RIFF\x24\x00\x00\x00WAVEfmt "

            def getheader(self, name, default=None):
                if name.lower() == "content-type":
                    return "audio/x-wav"
                return default

        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "voice.wav"
            with mock.patch.object(self.module, "local_tts_request", return_value=ValidWavResponse()):
                self.assertTrue(self.module.synthesize_to_file("text", path))

            self.assertEqual(path.read_bytes(), b"RIFF\x24\x00\x00\x00WAVEfmt ")

    def test_synthesize_to_file_rejects_non_wav_content(self):
        class InvalidWavResponse:
            status = 200

            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc, traceback):
                return False

            def read(self):
                return b'{"audio":"not-wav"}'

            def getheader(self, name, default=None):
                if name.lower() == "content-type":
                    return "application/json"
                return default

        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "voice.wav"
            with mock.patch.object(self.module, "local_tts_request", return_value=InvalidWavResponse()):
                self.assertFalse(self.module.synthesize_to_file("text", path))

            self.assertFalse(path.exists())
            self.assertEqual(list(Path(tmp).iterdir()), [])

    def test_synthesize_to_file_rejects_missing_content_type(self):
        class MissingContentTypeResponse:
            status = 200

            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc, traceback):
                return False

            def read(self):
                return b"RIFF\x24\x00\x00\x00WAVEfmt "

            def getheader(self, name, default=None):
                return default

        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "voice.wav"
            with mock.patch.object(self.module, "local_tts_request", return_value=MissingContentTypeResponse()):
                self.assertFalse(self.module.synthesize_to_file("text", path))

            self.assertFalse(path.exists())
            self.assertEqual(list(Path(tmp).iterdir()), [])

    def test_synthesize_to_file_rejects_fake_wav_content_type_with_invalid_body(self):
        class FakeWavResponse:
            status = 200

            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc, traceback):
                return False

            def read(self):
                return b"NOTW\x24\x00\x00\x00NOPEfmt "

            def getheader(self, name, default=None):
                if name.lower() == "content-type":
                    return "audio/wav"
                return default

        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "voice.wav"
            with mock.patch.object(self.module, "local_tts_request", return_value=FakeWavResponse()):
                self.assertFalse(self.module.synthesize_to_file("text", path))

            self.assertFalse(path.exists())
            self.assertEqual(list(Path(tmp).iterdir()), [])

    def test_synthesize_to_file_falls_back_for_empty_local_tts_body(self):
        class EmptyResponse:
            status = 200

            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc, traceback):
                return False

            def read(self):
                return b""

            def getheader(self, name, default=None):
                return default

        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "voice.wav"
            with mock.patch.object(self.module, "local_tts_request", return_value=EmptyResponse()):
                self.assertFalse(self.module.synthesize_to_file("text", path))

            self.assertFalse(path.exists())

    def test_synthesize_to_file_returns_false_for_non_2xx_response(self):
        class ErrorResponse:
            status = 503

            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc, traceback):
                return False

            def read(self):
                return b"RIFF....WAVEfmt "

            def getheader(self, name, default=None):
                return default

        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "voice.wav"
            with mock.patch.object(self.module, "local_tts_request", return_value=ErrorResponse()):
                self.assertFalse(self.module.synthesize_to_file("text", path))

            self.assertFalse(path.exists())

    def test_synthesize_to_file_returns_false_for_http_error(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "voice.wav"
            with mock.patch.object(
                self.module,
                "local_tts_request",
                side_effect=error.HTTPError(
                    self.module.DEFAULT_TTS_URL,
                    500,
                    "boom",
                    hdrs=None,
                    fp=None,
                ),
            ):
                self.assertFalse(self.module.synthesize_to_file("text", path))

            self.assertFalse(path.exists())

    def test_notify_voice_uses_tts_url_for_cache_key(self):
        with tempfile.TemporaryDirectory() as tmp, \
             mock.patch.dict(os.environ, {"XDG_CACHE_HOME": tmp, "NOTIFY_VOICE_TTS_URL": "http://localhost:9000/tts"}, clear=True), \
             mock.patch.object(self.module, "polish_text", return_value="完了しました。"), \
             mock.patch.object(self.module, "synthesize_to_file", return_value=True) as synthesize_to_file, \
             mock.patch.object(self.module, "play_audio", return_value=True):
            expected_path = self.module.audio_path(
                self.module.cache_dir(),
                self.module.cache_key("完了しました。", "http://localhost:9000/tts", self.module.DEFAULT_AUDIO_FORMAT),
            )
            result = self.module.notify_voice("summary", "body")

        self.assertEqual(result, 0)
        self.assertEqual(synthesize_to_file.call_args.args, ("完了しました。", expected_path))

    def test_extract_model_text_reads_first_choice_content(self):
        response = {
            "choices": [
                {
                    "message": {
                        "content": "完了しました。"
                    }
                }
            ]
        }
        self.assertEqual(self.module.extract_model_text(response), "完了しました。")

    def test_extract_model_text_falls_back_for_missing_content(self):
        self.assertEqual(self.module.extract_model_text({}), self.module.FALLBACK_TEXT)

    def test_polish_text_uses_fallback_without_github_token(self):
        with mock.patch.dict(os.environ, {}, clear=True):
            self.assertEqual(self.module.polish_text("summary", "body"), self.module.FALLBACK_TEXT)

    def test_polish_text_uses_response_from_github_models(self):
        payload = json.dumps(
            {
                "choices": [
                    {
                        "message": {
                            "content": "完了しました。"
                        }
                    }
                ]
            }
        ).encode("utf-8")

        class FakeResponse:
            status = 200

            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc, traceback):
                return False

            def read(self):
                return payload

        with mock.patch.dict(
            os.environ,
            {
                "GITHUB_TOKEN": "token",
                "NOTIFY_VOICE_TEXT_MODEL": "gpt-4o-mini",
            },
            clear=True,
        ), mock.patch.object(self.module, "github_models_request", return_value=FakeResponse()) as github_models_request:
            self.assertEqual(self.module.polish_text("summary", "body"), "完了しました。")
            request_payload = github_models_request.call_args.args[0]
            request_body = json.loads(request_payload.decode("utf-8"))
            self.assertEqual(request_body["model"], "gpt-4o-mini")

    def test_polish_text_falls_back_for_non_2xx_response(self):
        class FakeResponse:
            status = 500

            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc, traceback):
                return False

            def read(self):
                return b'{"error":"boom"}'

        with mock.patch.dict(os.environ, {"GITHUB_TOKEN": "token"}, clear=True), \
             mock.patch.object(self.module, "github_models_request", return_value=FakeResponse()):
            self.assertEqual(self.module.polish_text("summary", "body"), self.module.FALLBACK_TEXT)

    def test_polish_text_falls_back_for_invalid_json(self):
        class FakeResponse:
            status = 200

            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc, traceback):
                return False

            def read(self):
                return b"not-json"

        with mock.patch.dict(os.environ, {"GITHUB_TOKEN": "token"}, clear=True), \
             mock.patch.object(self.module, "github_models_request", return_value=FakeResponse()):
            self.assertEqual(self.module.polish_text("summary", "body"), self.module.FALLBACK_TEXT)

    def test_polish_text_falls_back_for_http_error(self):
        with mock.patch.dict(os.environ, {"GITHUB_TOKEN": "token"}, clear=True), \
             mock.patch.object(
                 self.module,
                 "github_models_request",
                 side_effect=error.HTTPError(
                     self.module.GITHUB_MODELS_URL,
                     500,
                     "boom",
                     hdrs=None,
                     fp=None,
                 ),
              ):
            self.assertEqual(self.module.polish_text("summary", "body"), self.module.FALLBACK_TEXT)


class StubCommandTestCase(unittest.TestCase):
    def write_stub(self, path, content):
        path.write_text(content, encoding="utf-8")
        path.chmod(0o755)

    def read_log_lines(self, path):
        return path.read_text(encoding="utf-8").splitlines()


class LocalNotifyIntegrationTest(StubCommandTestCase):

    def run_local_notify_with_voice_stub(self, voice_exit_code):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            bin_dir = tmp_path / "bin"
            bin_dir.mkdir()

            notify_send_log = tmp_path / "notify-send.log"
            notify_voice_log = tmp_path / "notify-voice.log"

            self.write_stub(
                bin_dir / "notify-send",
                "#!/bin/sh\n"
                "{\n"
                "  printf 'argc=%s\\n' \"$#\"\n"
                "  for arg in \"$@\"; do\n"
                "    printf 'arg=%s\\n' \"$arg\"\n"
                "  done\n"
                "} >> \"$TEST_NOTIFY_SEND_LOG\"\n",
            )
            self.write_stub(
                bin_dir / "notify-voice",
                "#!/bin/sh\n"
                "{\n"
                "  printf 'argc=%s\\n' \"$#\"\n"
                "  for arg in \"$@\"; do\n"
                "    printf 'arg=%s\\n' \"$arg\"\n"
                "  done\n"
                "} >> \"$TEST_NOTIFY_VOICE_LOG\"\n"
                f"exit {voice_exit_code}\n",
            )
            self.write_stub(
                bin_dir / "grep",
                "#!/bin/sh\n"
                "exit 1\n",
            )

            env = os.environ.copy()
            env.update(
                {
                    "PATH": f"{bin_dir}:/usr/bin:/bin",
                    "NOTIFY_VOICE_ENABLED": "1",
                    "NOTIFY_VOICE_TIMEOUT": "1",
                    "TEST_NOTIFY_SEND_LOG": str(notify_send_log),
                    "TEST_NOTIFY_VOICE_LOG": str(notify_voice_log),
                    "XDG_RUNTIME_DIR": str(tmp_path / "runtime"),
                    "DBUS_SESSION_BUS_ADDRESS": "unix:path=/tmp/test-bus",
                }
            )

            result = subprocess.run(
                [str(LOCAL_NOTIFY_SCRIPT), "test summary", "test body"],
                capture_output=True,
                text=True,
                env=env,
                check=False,
            )

            return result, self.read_log_lines(notify_voice_log), self.read_log_lines(notify_send_log)

    def test_local_notify_calls_notify_send_after_successful_voice(self):
        result, voice_log, send_log = self.run_local_notify_with_voice_stub(0)

        self.assertEqual(result.returncode, 0)
        self.assertEqual(result.stderr, "")
        self.assertEqual(voice_log, ["argc=2", "arg=test summary", "arg=test body"])
        self.assertEqual(send_log, ["argc=2", "arg=test summary", "arg=test body"])

    def test_local_notify_calls_notify_send_after_failed_voice(self):
        result, voice_log, send_log = self.run_local_notify_with_voice_stub(1)

        self.assertEqual(result.returncode, 0)
        self.assertEqual(result.stderr, "")
        self.assertEqual(voice_log, ["argc=2", "arg=test summary", "arg=test body"])
        self.assertEqual(send_log, ["argc=2", "arg=test summary", "arg=test body"])

    def test_local_notify_skips_voice_before_wsl_notification(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            bin_dir = tmp_path / "bin"
            bin_dir.mkdir()

            voice_log = tmp_path / "notify-voice.log"
            pwsh_log = tmp_path / "pwsh.log"
            pwsh_path = tmp_path / "pwsh.exe"

            self.write_stub(
                bin_dir / "notify-voice",
                "#!/bin/sh\n"
                "{\n"
                "  printf 'argc=%s\\n' \"$#\"\n"
                "  for arg in \"$@\"; do\n"
                "    printf 'arg=%s\\n' \"$arg\"\n"
                "  done\n"
                "} >> \"$TEST_NOTIFY_VOICE_LOG\"\n",
            )
            self.write_stub(
                bin_dir / "grep",
                "#!/bin/sh\n"
                "exit 0\n",
            )
            self.write_stub(
                pwsh_path,
                "#!/bin/sh\n"
                "{\n"
                "  printf 'argc=%s\\n' \"$#\"\n"
                "  for arg in \"$@\"; do\n"
                "    printf 'arg=%s\\n' \"$arg\"\n"
                "  done\n"
                "} >> \"$TEST_PWSH_LOG\"\n"
                "exit 0\n",
            )

            env = os.environ.copy()
            env.update(
                {
                    "PATH": f"{bin_dir}:/usr/bin:/bin",
                    "LOCAL_NOTIFY_PWSH": str(pwsh_path),
                    "NOTIFY_VOICE_ENABLED": "1",
                    "NOTIFY_VOICE_TIMEOUT": "1",
                    "TEST_NOTIFY_VOICE_LOG": str(voice_log),
                    "TEST_PWSH_LOG": str(pwsh_log),
                }
            )

            result = subprocess.run(
                [str(LOCAL_NOTIFY_SCRIPT), "test summary", "test body"],
                capture_output=True,
                text=True,
                env=env,
                check=False,
            )

            self.assertEqual(result.returncode, 0)
            self.assertEqual(result.stderr, "")
            self.assertFalse(voice_log.exists())
            self.assertTrue(self.read_log_lines(pwsh_log))

    def test_local_notify_skips_voice_when_wsl_notification_fails(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            bin_dir = tmp_path / "bin"
            bin_dir.mkdir()

            voice_log = tmp_path / "notify-voice.log"
            pwsh_log = tmp_path / "pwsh.log"
            pwsh_path = tmp_path / "pwsh.exe"

            self.write_stub(
                bin_dir / "notify-voice",
                "#!/bin/sh\n"
                "{\n"
                "  printf 'argc=%s\\n' \"$#\"\n"
                "  for arg in \"$@\"; do\n"
                "    printf 'arg=%s\\n' \"$arg\"\n"
                "  done\n"
                "} >> \"$TEST_NOTIFY_VOICE_LOG\"\n",
            )
            self.write_stub(
                bin_dir / "grep",
                "#!/bin/sh\n"
                "exit 0\n",
            )
            self.write_stub(
                pwsh_path,
                "#!/bin/sh\n"
                "{\n"
                "  printf 'argc=%s\\n' \"$#\"\n"
                "  for arg in \"$@\"; do\n"
                "    printf 'arg=%s\\n' \"$arg\"\n"
                "  done\n"
                "} >> \"$TEST_PWSH_LOG\"\n"
                "exit 1\n",
            )

            env = os.environ.copy()
            env.update(
                {
                    "PATH": f"{bin_dir}:/usr/bin:/bin",
                    "LOCAL_NOTIFY_PWSH": str(pwsh_path),
                    "NOTIFY_VOICE_ENABLED": "1",
                    "NOTIFY_VOICE_TIMEOUT": "1",
                    "TEST_NOTIFY_VOICE_LOG": str(voice_log),
                    "TEST_PWSH_LOG": str(pwsh_log),
                }
            )

            result = subprocess.run(
                [str(LOCAL_NOTIFY_SCRIPT), "test summary", "test body"],
                capture_output=True,
                text=True,
                env=env,
                check=False,
            )

            self.assertNotEqual(result.returncode, 0)
            self.assertFalse(voice_log.exists())
            self.assertTrue(self.read_log_lines(pwsh_log))


class NotificationRoutingIntegrationTest(StubCommandTestCase):
    def write_logging_stub(self, path, log_env_var):
        self.write_stub(
            path,
            "#!/bin/sh\n"
            "{\n"
            "  printf 'argc=%s\\n' \"$#\"\n"
            "  for arg in \"$@\"; do\n"
            "    printf 'arg=%s\\n' \"$arg\"\n"
            "  done\n"
            f"}} >> \"${log_env_var}\"\n",
        )

    def build_notify_env(self, bin_dir, extra_env=None):
        env = os.environ.copy()
        env.update(
            {
                "PATH": f"{bin_dir}:/usr/bin:/bin",
            }
        )
        if extra_env:
            env.update(extra_env)
        return env

    def test_remote_notify_passes_arguments_to_remote_local_notify_command(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            bin_dir = tmp_path / "bin"
            bin_dir.mkdir()

            ssh_log = tmp_path / "ssh.log"
            self.write_logging_stub(bin_dir / "ssh", "TEST_SSH_LOG")

            env = self.build_notify_env(
                bin_dir,
                {
                    "TEST_SSH_LOG": str(ssh_log),
                },
            )

            result = subprocess.run(
                [
                    str(REMOTE_NOTIFY_SCRIPT),
                    "--host",
                    "desktop-host",
                    "-a",
                    "OpenCode",
                    "-u",
                    "critical",
                    "-i",
                    "dialog-information",
                    "-t",
                    "5000",
                    "build finished",
                    "line with 'quote'",
                ],
                capture_output=True,
                text=True,
                env=env,
                check=False,
            )

            self.assertEqual(result.returncode, 0)
            self.assertEqual(result.stdout, "")
            self.assertEqual(result.stderr, "")
            self.assertEqual(
                self.read_log_lines(ssh_log),
                [
                    "argc=3",
                    "arg=--",
                    "arg=desktop-host",
                    "arg=PATH=\"$HOME/.local/bin:$PATH\"; export PATH; exec local-notify '-a' 'OpenCode' '-u' 'critical' '-i' 'dialog-information' '-t' '5000' 'build finished' 'line with '\\''quote'\\'''",
                ],
            )

    def test_opencode_notify_routes_to_remote_notify_when_host_is_set(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            bin_dir = tmp_path / "bin"
            bin_dir.mkdir()

            remote_log = tmp_path / "remote.log"
            local_log = tmp_path / "local.log"
            self.write_logging_stub(bin_dir / "remote-notify", "TEST_REMOTE_NOTIFY_LOG")
            self.write_logging_stub(bin_dir / "local-notify", "TEST_LOCAL_NOTIFY_LOG")

            env = self.build_notify_env(
                bin_dir,
                {
                    "REMOTE_NOTIFY_HOST": "desktop-host",
                    "TEST_REMOTE_NOTIFY_LOG": str(remote_log),
                    "TEST_LOCAL_NOTIFY_LOG": str(local_log),
                },
            )

            result = subprocess.run(
                [str(OPENCODE_NOTIFY_SCRIPT), "TaskComplete", "Build passed"],
                capture_output=True,
                text=True,
                env=env,
                check=False,
            )

            self.assertEqual(result.returncode, 0)
            self.assertEqual(result.stdout, "")
            self.assertEqual(result.stderr, "")
            self.assertEqual(
                self.read_log_lines(remote_log),
                ["argc=4", "arg=-a", "arg=OpenCode", "arg=OpenCode - TaskComplete", "arg=Build passed"],
            )
            self.assertFalse(local_log.exists())

    def test_opencode_notify_routes_to_local_notify_when_host_is_not_set(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            bin_dir = tmp_path / "bin"
            bin_dir.mkdir()

            remote_log = tmp_path / "remote.log"
            local_log = tmp_path / "local.log"
            self.write_logging_stub(bin_dir / "remote-notify", "TEST_REMOTE_NOTIFY_LOG")
            self.write_logging_stub(bin_dir / "local-notify", "TEST_LOCAL_NOTIFY_LOG")

            env = self.build_notify_env(
                bin_dir,
                {
                    "TEST_REMOTE_NOTIFY_LOG": str(remote_log),
                    "TEST_LOCAL_NOTIFY_LOG": str(local_log),
                },
            )

            result = subprocess.run(
                [str(OPENCODE_NOTIFY_SCRIPT), "TaskComplete", "Build passed"],
                capture_output=True,
                text=True,
                env=env,
                check=False,
            )

            self.assertEqual(result.returncode, 0)
            self.assertEqual(result.stdout, "")
            self.assertEqual(result.stderr, "")
            self.assertEqual(
                self.read_log_lines(local_log),
                ["argc=4", "arg=-a", "arg=OpenCode", "arg=OpenCode - TaskComplete", "arg=Build passed"],
            )
            self.assertFalse(remote_log.exists())

    def write_fake_jq(self, path):
        self.write_stub(
            path,
            "#!/usr/bin/env python3\n"
            "import json\n"
            "import sys\n"
            "\n"
            "args = sys.argv[1:]\n"
            "expr = args[-1]\n"
            "data = json.load(sys.stdin)\n"
            "if expr == '.notification_type // \"Notification\"':\n"
            "    value = data.get('notification_type', 'Notification')\n"
            "elif expr == '.message // \"No message provided\"':\n"
            "    value = data.get('message', 'No message provided')\n"
            "elif expr == '.details // empty':\n"
            "    value = data.get('details', '')\n"
            "elif expr == '.tool_name // empty':\n"
            "    value = data.get('tool_name', '')\n"
            "else:\n"
            "    raise SystemExit(f'unsupported jq expression: {expr}')\n"
            "if value is None:\n"
            "    value = ''\n"
            "if isinstance(value, (dict, list)):\n"
            "    sys.stdout.write(json.dumps(value))\n"
            "else:\n"
            "    sys.stdout.write(str(value))\n",
        )

    def test_gemini_notify_routes_to_remote_notify_when_host_is_set(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            bin_dir = tmp_path / "bin"
            bin_dir.mkdir()

            remote_log = tmp_path / "remote.log"
            local_log = tmp_path / "local.log"
            self.write_logging_stub(bin_dir / "remote-notify", "TEST_REMOTE_NOTIFY_LOG")
            self.write_logging_stub(bin_dir / "local-notify", "TEST_LOCAL_NOTIFY_LOG")
            self.write_fake_jq(bin_dir / "jq")

            env = self.build_notify_env(
                bin_dir,
                {
                    "REMOTE_NOTIFY_HOST": "desktop-host",
                    "TEST_REMOTE_NOTIFY_LOG": str(remote_log),
                    "TEST_LOCAL_NOTIFY_LOG": str(local_log),
                },
            )

            result = subprocess.run(
                [str(GEMINI_NOTIFY_SCRIPT)],
                input='{"notification_type":"TaskComplete","message":"Build passed"}',
                capture_output=True,
                text=True,
                env=env,
                check=False,
            )

            self.assertEqual(result.returncode, 0)
            self.assertEqual(result.stdout, "")
            self.assertEqual(result.stderr, "")
            self.assertEqual(
                self.read_log_lines(remote_log),
                ["argc=4", "arg=-a", "arg=Gemini", "arg=Gemini - TaskComplete", "arg=Build passed"],
            )
            self.assertFalse(local_log.exists())

    def test_gemini_notify_routes_to_local_notify_when_host_is_not_set(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            bin_dir = tmp_path / "bin"
            bin_dir.mkdir()

            remote_log = tmp_path / "remote.log"
            local_log = tmp_path / "local.log"
            self.write_logging_stub(bin_dir / "remote-notify", "TEST_REMOTE_NOTIFY_LOG")
            self.write_logging_stub(bin_dir / "local-notify", "TEST_LOCAL_NOTIFY_LOG")
            self.write_fake_jq(bin_dir / "jq")

            env = self.build_notify_env(
                bin_dir,
                {
                    "TEST_REMOTE_NOTIFY_LOG": str(remote_log),
                    "TEST_LOCAL_NOTIFY_LOG": str(local_log),
                },
            )

            result = subprocess.run(
                [str(GEMINI_NOTIFY_SCRIPT)],
                input='{"notification_type":"TaskComplete","message":"Build passed"}',
                capture_output=True,
                text=True,
                env=env,
                check=False,
            )

            self.assertEqual(result.returncode, 0)
            self.assertEqual(result.stdout, "")
            self.assertEqual(result.stderr, "")
            self.assertEqual(
                self.read_log_lines(local_log),
                ["argc=4", "arg=-a", "arg=Gemini", "arg=Gemini - TaskComplete", "arg=Build passed"],
            )
            self.assertFalse(remote_log.exists())


if __name__ == "__main__":
    unittest.main()
