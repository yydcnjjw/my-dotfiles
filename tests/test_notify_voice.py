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
import warnings
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "dot_local" / "bin" / "executable_notify-voice"
LOCAL_NOTIFY_SCRIPT = ROOT / "dot_local" / "bin" / "executable_local-notify"
REMOTE_NOTIFY_SCRIPT = ROOT / "dot_local" / "bin" / "executable_remote-notify"
AGENT_NOTIFY_SCRIPT = ROOT / "dot_local" / "bin" / "executable_agent-notify"
OPENCODE_NOTIFY_SCRIPT = ROOT / "dot_local" / "bin" / "executable_opencode-notify"
CODEX_NOTIFY_SCRIPT = ROOT / "dot_local" / "bin" / "executable_codex-notify"
GEMINI_NOTIFY_SCRIPT = ROOT / "dot_local" / "bin" / "executable_gemini-notify"
GEMINI_SETTINGS = ROOT / "dot_gemini" / "settings.json"
EXPECTED_FALLBACK_TEXTS = [
    "ほら、ちゃんと確認しなさいよ！",
    "ちょっと、早く確認しなさいってば！",
    "べつにあんたのためじゃないけど、ちゃんと見なさいよ！",
    "ほら、通知なんだからさっさと確認しなさいよ！",
    "なによ、気づいてるならちゃんと確認しなさいよ！",
]


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

    def test_polish_cache_key_includes_summary_body_model_base_url_and_prompt_version(self):
        first = self.module.polish_cache_key("title", "body", "GPT-5 mini", "http://one.test", "v1")
        second = self.module.polish_cache_key("title", "body", "GPT-4.1", "http://one.test", "v1")
        third = self.module.polish_cache_key("title", "body", "GPT-5 mini", "http://two.test", "v1")
        fourth = self.module.polish_cache_key("title", "body", "GPT-5 mini", "http://one.test", "v2")
        self.assertNotEqual(first, second)
        self.assertNotEqual(first, third)
        self.assertNotEqual(first, fourth)
        self.assertEqual(len(first), 64)

    def test_polish_cache_path_uses_txt_extension(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = self.module.polish_cache_path(Path(tmp), "abc123")
            self.assertEqual(path, Path(tmp) / "abc123.txt")

    def test_debug_log_path_uses_cache_dir(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = self.module.debug_log_path(Path(tmp))
            self.assertEqual(path, Path(tmp) / "debug.log")

    def test_debug_log_appends_single_line_entries(self):
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp)
            self.module.append_debug_log(directory, "first event")
            self.module.append_debug_log(directory, "second event")

            lines = self.module.debug_log_path(directory).read_text(encoding="utf-8").splitlines()
            self.assertEqual(len(lines), 2)
            self.assertIn("notify-voice: first event", lines[0])
            self.assertIn("notify-voice: second event", lines[1])

    def test_trim_debug_log_keeps_latest_content_when_over_limit(self):
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp)
            log_path = self.module.debug_log_path(directory)
            log_path.write_text("old\n" + ("x" * 80) + "\nnew\n", encoding="utf-8")

            self.module.trim_debug_log(directory, max_bytes=32)

            content = log_path.read_text(encoding="utf-8")
            self.assertIn("new\n", content)
            self.assertLessEqual(log_path.stat().st_size, 32)

    def test_append_debug_log_ignores_write_failures(self):
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp)
            with mock.patch.object(Path, "open", side_effect=OSError("disk full")):
                self.module.append_debug_log(directory, "event")

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

    def test_prune_cache_limits_text_cache_without_affecting_audio_cache(self):
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp)
            for index in range(55):
                audio_path = directory / f"audio-{index:02d}.wav"
                text_path = directory / f"text-{index:02d}.txt"
                audio_path.write_bytes(b"audio")
                text_path.write_text("text", encoding="utf-8")
                os.utime(audio_path, (index, index))
                os.utime(text_path, (index, index))

            self.module.prune_cache(directory, max_files=50)

            remaining_audio = sorted(path.name for path in directory.glob("*.wav"))
            remaining_text = sorted(path.name for path in directory.glob("*.txt"))
            self.assertEqual(len(remaining_audio), 50)
            self.assertEqual(len(remaining_text), 50)
            self.assertEqual(remaining_audio[0], "audio-05.wav")
            self.assertEqual(remaining_audio[-1], "audio-54.wav")
            self.assertEqual(remaining_text[0], "text-05.txt")
            self.assertEqual(remaining_text[-1], "text-54.txt")

    def test_prune_cache_ignores_files_that_disappear_during_pruning(self):
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp)
            for index in range(55):
                path = directory / f"{index:02d}.wav"
                path.write_bytes(b"audio")
                os.utime(path, (index, index))

            original_stat = Path.stat
            deleted = False

            def stat_with_disappearing_file(path, *args, **kwargs):
                nonlocal deleted
                if path.name == "00.wav" and not deleted:
                    deleted = True
                    path.unlink()
                    raise FileNotFoundError(path)
                return original_stat(path, *args, **kwargs)

            with mock.patch.object(Path, "stat", stat_with_disappearing_file):
                self.module.prune_cache(directory, max_files=50)

            remaining_audio = sorted(path.name for path in directory.glob("*.wav"))
            self.assertEqual(len(remaining_audio), 50)

    def test_player_command_uses_first_available_builtin_player(self):
        command = self.module.player_command(lambda name: "/usr/bin/mpv" if name == "mpv" else None)
        self.assertEqual(command, ["mpv", "--no-terminal", "--really-quiet"])

    def test_player_command_falls_back_to_aplay(self):
        command = self.module.player_command(lambda name: "/usr/bin/aplay" if name == "aplay" else None)
        self.assertEqual(command, ["aplay", "-q"])

    def test_build_copilot_prompt_contains_summary_body_output_and_tone_style_constraints(self):
        prompt = self.module.build_copilot_prompt("OpenCode - Notification", "Task finished")
        self.assertIn("OpenCode - Notification", prompt)
        self.assertIn("Task finished", prompt)
        self.assertIn("日本語", prompt)
        self.assertIn("1文", prompt)
        self.assertIn("本文のみ", prompt)
        self.assertIn("少しツンデレ", prompt)
        self.assertIn("軽くたしなめる", prompt)
        self.assertIn("大げさになりすぎない", prompt)
        self.assertIn("決まり文句", prompt)

    def test_openai_timeout_seconds_uses_default_for_invalid_values(self):
        self.assertEqual(self.module.openai_timeout_seconds({}), 15)
        self.assertEqual(
            self.module.openai_timeout_seconds({"NOTIFY_VOICE_OPENAI_TIMEOUT": "abc"}),
            15,
        )
        self.assertEqual(
            self.module.openai_timeout_seconds({"NOTIFY_VOICE_OPENAI_TIMEOUT": "0"}),
            15,
        )
        self.assertEqual(
            self.module.openai_timeout_seconds({"NOTIFY_VOICE_OPENAI_TIMEOUT": "7"}),
            7,
        )

    def test_openai_base_url_and_model_use_defaults(self):
        self.assertEqual(self.module.openai_base_url({}), "http://10.30.254.33:7777")
        self.assertEqual(self.module.openai_model({}), "gpt-5.4-mini")

    def test_openai_chat_completions_url_uses_base_url(self):
        self.assertEqual(
            self.module.openai_chat_completions_url({}),
            "http://10.30.254.33:7777/v1/chat/completions",
        )
        self.assertEqual(
            self.module.openai_chat_completions_url({"NOTIFY_VOICE_OPENAI_BASE_URL": "http://example.test/api/"}),
            "http://example.test/api/v1/chat/completions",
        )

    def test_build_openai_chat_completions_request_contains_model_and_message(self):
        payload = json.loads(
            self.module.build_openai_chat_completions_request(
                "gpt-5.4-mini",
                "prompt text",
            ).decode("utf-8")
        )
        self.assertEqual(
            payload,
            {
                "model": "gpt-5.4-mini",
                "messages": [
                    {
                        "role": "user",
                        "content": "prompt text",
                    },
                ],
            },
        )

    def test_fallback_texts_match_expected_pool(self):
        self.assertEqual(len(self.module.FALLBACK_TEXTS), 5)
        self.assertCountEqual(self.module.FALLBACK_TEXTS, EXPECTED_FALLBACK_TEXTS)

    def test_is_fallback_text_accepts_legacy_single_fallback_text(self):
        self.assertTrue(self.module.is_fallback_text("通知があります"))

    def test_select_fallback_text_returns_value_from_pool(self):
        text = self.module.select_fallback_text()
        self.assertIn(text, self.module.FALLBACK_TEXTS)
        self.assertEqual(self.module._last_fallback_text, text)

    def test_select_fallback_text_avoids_repeating_previous_text(self):
        previous_text = "ほら、ちゃんと確認しなさいよ！"
        selected_text = "なによ、気づいてるならちゃんと確認しなさいよ！"
        self.module._last_fallback_text = previous_text

        with mock.patch.object(
            self.module,
            "FALLBACK_TEXTS",
            [previous_text, selected_text],
            create=True,
        ):
            text = self.module.select_fallback_text()

        self.assertEqual(text, selected_text)
        self.assertIn(text, self.module.FALLBACK_TEXTS)
        self.assertEqual(self.module._last_fallback_text, selected_text)

    def test_select_fallback_text_uses_random_choice_with_previous_text_removed(self):
        previous_text = "ほら、ちゃんと確認しなさいよ！"
        selected_text = "ちょっと、早く確認しなさいってば！"
        self.module._last_fallback_text = previous_text

        with mock.patch.object(
            self.module,
            "FALLBACK_TEXTS",
            [previous_text, selected_text, "なによ、気づいてるならちゃんと確認しなさいよ！"],
            create=True,
        ), mock.patch.object(self.module.random, "choice", return_value=selected_text) as choice:
            text = self.module.select_fallback_text()

        choice.assert_called_once_with(
            [selected_text, "なによ、気づいてるならちゃんと確認しなさいよ！"]
        )
        self.assertEqual(text, selected_text)
        self.assertEqual(self.module._last_fallback_text, selected_text)

    def test_clean_spoken_text_returns_empty_spoken_text_sentinel_for_empty_output(self):
        self.assertIs(self.module.clean_spoken_text("\n  \n"), self.module.EMPTY_SPOKEN_TEXT)

    def test_clean_spoken_text_returns_first_non_empty_line(self):
        self.assertEqual(self.module.clean_spoken_text("完了しました。\n説明"), "完了しました。")

    def test_extract_openai_chat_content_reads_message_content(self):
        payload = {
            "choices": [
                {
                    "message": {
                        "content": "ビルドが完了しました。",
                    }
                }
            ],
        }
        self.assertEqual(
            self.module.extract_openai_chat_content(payload),
            "ビルドが完了しました。",
        )

    def test_extract_openai_chat_content_joins_multiple_choices(self):
        payload = {
            "choices": [
                {
                    "message": {
                        "content": "ビルドが完了しました。",
                    }
                },
                {
                    "message": {
                        "content": "確認してください。",
                    }
                },
            ]
        }
        self.assertEqual(
            self.module.extract_openai_chat_content(payload),
            "ビルドが完了しました。\n確認してください。",
        )

    def test_extract_openai_chat_content_returns_none_when_missing_text(self):
        self.assertIsNone(self.module.extract_openai_chat_content({"choices": []}))

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
        with mock.patch.dict(os.environ, {}, clear=True), \
             mock.patch("urllib.request.urlopen", return_value=response) as urlopen:
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
            self.assertEqual(
                [entry.name for entry in Path(tmp).iterdir() if entry.name != self.module.DEBUG_LOG_NAME],
                [],
            )

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
            self.assertEqual(
                [entry.name for entry in Path(tmp).iterdir() if entry.name != self.module.DEBUG_LOG_NAME],
                [],
            )

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
            self.assertEqual(
                [entry.name for entry in Path(tmp).iterdir() if entry.name != self.module.DEBUG_LOG_NAME],
                [],
            )

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
            self.assertEqual(
                [entry.name for entry in Path(tmp).iterdir() if entry.name != self.module.DEBUG_LOG_NAME],
                [],
            )

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
        class CloseTrackingBody:
            def __init__(self):
                self.closed = False

            def close(self):
                self.closed = True

        response_body = CloseTrackingBody()

        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "voice.wav"
            with mock.patch.object(
                self.module,
                "local_tts_request",
                side_effect=self.module.error.HTTPError(
                    self.module.DEFAULT_TTS_URL,
                    500,
                    "boom",
                    hdrs=None,
                    fp=response_body,
                ),
            ):
                with warnings.catch_warnings(record=True) as caught:
                    warnings.simplefilter("always", ResourceWarning)
                    self.assertFalse(self.module.synthesize_to_file("text", path))

            self.assertFalse(path.exists())
            self.assertTrue(response_body.closed)
            resource_warnings = [
                warning for warning in caught if issubclass(warning.category, ResourceWarning)
            ]
            self.assertEqual(resource_warnings, [])

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

    def test_notify_voice_continues_when_debug_log_write_fails(self):
        with tempfile.TemporaryDirectory() as tmp, \
             mock.patch.dict(os.environ, {"XDG_CACHE_HOME": tmp}, clear=True), \
             mock.patch.object(self.module, "polish_text", return_value="完了しました。"), \
             mock.patch.object(self.module, "synthesize_to_file", return_value=True), \
             mock.patch.object(self.module, "play_audio", return_value=True), \
             mock.patch.object(
                 self.module,
                 "append_debug_log",
                 side_effect=OSError("disk full"),
                 create=True,
             ) as append_debug_log:
            self.assertEqual(self.module.notify_voice("summary", "body"), 0)

        self.assertGreaterEqual(append_debug_log.call_count, 1)

    def test_polish_text_uses_stdout_from_openai_chat_completions(self):
        class FakeResponse:
            status = 200

            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc, traceback):
                return False

            def read(self):
                return json.dumps(
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

            def getheader(self, name, default=None):
                if name.lower() == "content-type":
                    return "application/json"
                return default

        with tempfile.TemporaryDirectory() as tmp:
            with mock.patch.dict(os.environ, {"XDG_CACHE_HOME": tmp}, clear=True), \
                 mock.patch("urllib.request.urlopen", return_value=FakeResponse()) as urlopen:
                    self.assertEqual(self.module.polish_text("summary", "body"), "完了しました。")

        urlopen.assert_called_once()
        req = urlopen.call_args.args[0]
        self.assertEqual(req.full_url, "http://10.30.254.33:7777/v1/chat/completions")
        self.assertEqual(req.get_method(), "POST")
        self.assertEqual(req.get_header("Content-type"), "application/json")
        self.assertEqual(urlopen.call_args.kwargs["timeout"], 15)

    def test_polish_text_uses_cached_text_without_running_openai_request(self):
        with tempfile.TemporaryDirectory() as tmp:
            cache_dir = Path(tmp) / "notify-voice"
            cache_dir.mkdir()
            cache_path = self.module.polish_cache_path(
                cache_dir,
                self.module.polish_cache_key(
                    "summary",
                    "body",
                    "gpt-5.4-mini",
                    "http://10.30.254.33:7777",
                    self.module.PROMPT_VERSION,
                ),
            )
            cache_path.write_text("完了しました。", encoding="utf-8")

            with mock.patch.dict(os.environ, {"XDG_CACHE_HOME": tmp}, clear=True), \
                 mock.patch("urllib.request.urlopen") as urlopen:
                self.assertEqual(self.module.polish_text("summary", "body"), "完了しました。")

            urlopen.assert_not_called()

    def test_polish_text_writes_debug_log_for_cache_hit(self):
        with tempfile.TemporaryDirectory() as tmp:
            cache_dir = Path(tmp) / "notify-voice"
            cache_dir.mkdir()
            cache_path = self.module.polish_cache_path(
                cache_dir,
                self.module.polish_cache_key(
                    "summary",
                    "body",
                    "gpt-5.4-mini",
                    "http://10.30.254.33:7777",
                    self.module.PROMPT_VERSION,
                ),
            )
            cache_path.write_text("完了しました。", encoding="utf-8")

            with mock.patch.dict(os.environ, {"XDG_CACHE_HOME": tmp}, clear=True):
                self.assertEqual(self.module.polish_text("summary", "body"), "完了しました。")

            log_text = (cache_dir / "debug.log").read_text(encoding="utf-8")
            self.assertIn("polish cache hit", log_text)

    def test_polish_text_writes_successful_result_to_cache(self):
        class FakeResponse:
            status = 200

            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc, traceback):
                return False

            def read(self):
                return json.dumps(
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

            def getheader(self, name, default=None):
                if name.lower() == "content-type":
                    return "application/json"
                return default

        with tempfile.TemporaryDirectory() as tmp:
            with mock.patch.dict(os.environ, {"XDG_CACHE_HOME": tmp}, clear=True), \
                 mock.patch("urllib.request.urlopen", return_value=FakeResponse()):
                self.assertEqual(self.module.polish_text("summary", "body"), "完了しました。")

            cache_path = self.module.polish_cache_path(
                self.module.cache_dir({"XDG_CACHE_HOME": tmp}),
                self.module.polish_cache_key(
                    "summary",
                    "body",
                    "gpt-5.4-mini",
                    "http://10.30.254.33:7777",
                    self.module.PROMPT_VERSION,
                ),
            )
            self.assertEqual(cache_path.read_text(encoding="utf-8"), "完了しました。")

    def test_polish_text_writes_debug_log_for_openai_success(self):
        class FakeResponse:
            status = 200

            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc, traceback):
                return False

            def read(self):
                return json.dumps(
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

            def getheader(self, name, default=None):
                return "application/json"

        with tempfile.TemporaryDirectory() as tmp:
            with mock.patch.dict(os.environ, {"XDG_CACHE_HOME": tmp}, clear=True), \
                 mock.patch("urllib.request.urlopen", return_value=FakeResponse()):
                self.assertEqual(self.module.polish_text("summary", "body"), "完了しました。")

            log_text = (Path(tmp) / "notify-voice" / "debug.log").read_text(encoding="utf-8")
            self.assertIn("openai chat success", log_text)
            self.assertIn('model="gpt-5.4-mini"', log_text)

    def test_polish_text_does_not_cache_fallback_after_openai_timeout(self):
        with tempfile.TemporaryDirectory() as tmp:
            with mock.patch.dict(os.environ, {"XDG_CACHE_HOME": tmp}, clear=True), \
                 mock.patch("urllib.request.urlopen", side_effect=TimeoutError("timed out")), \
                 mock.patch.object(
                     self.module,
                     "select_fallback_text",
                     return_value="なによ、気づいてるならちゃんと確認しなさいよ！",
                 ):
                self.assertEqual(
                    self.module.polish_text("summary", "body"),
                    "なによ、気づいてるならちゃんと確認しなさいよ！",
                )

            cache_path = self.module.polish_cache_path(
                self.module.cache_dir({"XDG_CACHE_HOME": tmp}),
                self.module.polish_cache_key(
                    "summary",
                    "body",
                    "gpt-5.4-mini",
                    "http://10.30.254.33:7777",
                    self.module.PROMPT_VERSION,
                ),
            )
            self.assertFalse(cache_path.exists())

    def test_polish_text_falls_back_when_openai_times_out(self):
        with tempfile.TemporaryDirectory() as tmp:
            with mock.patch.dict(os.environ, {"XDG_CACHE_HOME": tmp}, clear=True), \
                 mock.patch("urllib.request.urlopen", side_effect=TimeoutError("timed out")), \
                 mock.patch.object(
                     self.module,
                     "select_fallback_text",
                     return_value="ちょっと、早く確認しなさいってば！",
                 ) as select_fallback_text:
                self.assertEqual(
                    self.module.polish_text("summary", "body"),
                    "ちょっと、早く確認しなさいってば！",
                )

        select_fallback_text.assert_called_once_with()

    def test_polish_text_falls_back_when_openai_returns_invalid_json(self):
        class FakeResponse:
            status = 200

            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc, traceback):
                return False

            def read(self):
                return b"not-json"

            def getheader(self, name, default=None):
                return "application/json"

        with tempfile.TemporaryDirectory() as tmp:
            with mock.patch.dict(os.environ, {"XDG_CACHE_HOME": tmp}, clear=True), \
                 mock.patch("urllib.request.urlopen", return_value=FakeResponse()), \
                 mock.patch.object(
                     self.module,
                     "select_fallback_text",
                     return_value="ほら、ちゃんと確認しなさいよ！",
                 ):
                self.assertEqual(
                    self.module.polish_text("summary", "body"),
                    "ほら、ちゃんと確認しなさいよ！",
                )

    def test_polish_text_selects_fallback_once_when_cleaned_openai_text_is_empty(self):
        class FakeResponse:
            status = 200

            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc, traceback):
                return False

            def read(self):
                return json.dumps(
                    {
                        "choices": [
                            {
                                "message": {
                                    "content": '  ""  '
                                }
                            }
                        ]
                    }
                ).encode("utf-8")

            def getheader(self, name, default=None):
                return "application/json"

        with tempfile.TemporaryDirectory() as tmp:
            with mock.patch.dict(os.environ, {"XDG_CACHE_HOME": tmp}, clear=True), \
                 mock.patch("urllib.request.urlopen", return_value=FakeResponse()), \
                 mock.patch.object(
                     self.module,
                     "FALLBACK_TEXTS",
                     ["ほら、ちゃんと確認しなさいよ！", "ちょっと、早く確認しなさいってば！"],
                     create=True,
                 ), \
                 mock.patch.object(
                     self.module,
                     "select_fallback_text",
                     side_effect=[
                         "ほら、ちゃんと確認しなさいよ！",
                         "ちょっと、早く確認しなさいってば！",
                     ],
                 ) as select_fallback_text:
                self.assertEqual(
                    self.module.polish_text("summary", "body"),
                    "ほら、ちゃんと確認しなさいよ！",
                )

        select_fallback_text.assert_called_once_with()

    def test_polish_text_writes_debug_log_for_openai_timeout(self):
        with tempfile.TemporaryDirectory() as tmp:
            with mock.patch.dict(os.environ, {"XDG_CACHE_HOME": tmp}, clear=True), \
                 mock.patch("urllib.request.urlopen", side_effect=TimeoutError("timed out")), \
                 mock.patch.object(
                     self.module,
                     "select_fallback_text",
                     return_value="ほら、通知なんだからさっさと確認しなさいよ！",
                 ):
                self.assertEqual(
                    self.module.polish_text("summary", "body"),
                    "ほら、通知なんだからさっさと確認しなさいよ！",
                )

            log_text = (Path(tmp) / "notify-voice" / "debug.log").read_text(encoding="utf-8")
            self.assertIn("openai chat timeout", log_text)


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

    def install_agent_notify(self, bin_dir):
        target = bin_dir / "agent-notify"
        target.write_text(AGENT_NOTIFY_SCRIPT.read_text(encoding="utf-8"), encoding="utf-8")
        target.chmod(0o755)

    def codex_payload(self):
        return json.dumps(
            {
                "type": "agent-turn-complete",
                "thread-id": "019eba7e-3db9-7f62-a54d-2cf942466893",
                "turn-id": "019ec58d-2691-7981-8489-7ca9c0b5c012",
                "cwd": "/home/yydcnjjw/.local/share/chezmoi",
                "client": "codex-tui",
                "input-messages": [
                    "codex 通知显示的内容，不容易理解",
                    "增加通知日志",
                    "好",
                ],
                "last-assistant-message": "已增加通知日志，并已应用到当前机器。",
            },
            ensure_ascii=False,
        )

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

    def test_agent_notify_routes_to_remote_notify_when_host_is_set(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            bin_dir = tmp_path / "bin"
            bin_dir.mkdir()

            remote_log = tmp_path / "remote.log"
            local_log = tmp_path / "local.log"
            self.install_agent_notify(bin_dir)
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
                [str(AGENT_NOTIFY_SCRIPT), "-a", "Codex", "Build", "Done"],
                capture_output=True,
                text=True,
                env=env,
                check=False,
            )

            self.assertEqual(result.returncode, 0)
            self.assertEqual(result.stdout, "")
            self.assertEqual(result.stderr, "")
            self.assertEqual(self.read_log_lines(remote_log), ["argc=4", "arg=-a", "arg=Codex", "arg=Build", "arg=Done"])
            self.assertFalse(local_log.exists())

    def test_agent_notify_routes_to_local_notify_when_host_is_not_set(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            bin_dir = tmp_path / "bin"
            bin_dir.mkdir()

            remote_log = tmp_path / "remote.log"
            local_log = tmp_path / "local.log"
            self.install_agent_notify(bin_dir)
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
                [str(AGENT_NOTIFY_SCRIPT), "-a", "Codex", "Build", "Done"],
                capture_output=True,
                text=True,
                env=env,
                check=False,
            )

            self.assertEqual(result.returncode, 0)
            self.assertEqual(result.stdout, "")
            self.assertEqual(result.stderr, "")
            self.assertEqual(self.read_log_lines(local_log), ["argc=4", "arg=-a", "arg=Codex", "arg=Build", "arg=Done"])
            self.assertFalse(remote_log.exists())

    def test_agent_notify_writes_notification_log_for_each_route(self):
        cases = [
            ("remote", True, True),
            ("local", False, True),
            ("stdout", False, False),
        ]

        for expected_route, use_remote_host, install_local_notify in cases:
            with self.subTest(route=expected_route), tempfile.TemporaryDirectory() as tmp:
                tmp_path = Path(tmp)
                bin_dir = tmp_path / "bin"
                bin_dir.mkdir()

                cache_dir = tmp_path / "cache"
                remote_log = tmp_path / "remote.log"
                local_log = tmp_path / "local.log"
                self.write_logging_stub(bin_dir / "remote-notify", "TEST_REMOTE_NOTIFY_LOG")
                if install_local_notify:
                    self.write_logging_stub(bin_dir / "local-notify", "TEST_LOCAL_NOTIFY_LOG")

                extra_env = {
                    "XDG_CACHE_HOME": str(cache_dir),
                    "TEST_REMOTE_NOTIFY_LOG": str(remote_log),
                    "TEST_LOCAL_NOTIFY_LOG": str(local_log),
                }
                if use_remote_host:
                    extra_env["REMOTE_NOTIFY_HOST"] = "desktop-host"

                result = subprocess.run(
                    [str(AGENT_NOTIFY_SCRIPT), "-a", "Codex", "Build", "Done"],
                    capture_output=True,
                    text=True,
                    env=self.build_notify_env(bin_dir, extra_env),
                    check=False,
                )

                self.assertEqual(result.returncode, 0)
                self.assertEqual(result.stderr, "")
                if expected_route == "stdout":
                    self.assertEqual(result.stdout, "Notification: Build: Done\n")
                else:
                    self.assertEqual(result.stdout, "")

                notification_log = cache_dir / "agent-notify" / "notifications.log"
                lines = self.read_log_lines(notification_log)
                self.assertEqual(len(lines), 1)
                self.assertIn(f"route={expected_route}", lines[0])
                self.assertIn('app="Codex"', lines[0])
                self.assertIn('summary="Build"', lines[0])
                self.assertIn('message="Done"', lines[0])

    def test_agent_notify_continues_when_notification_log_write_fails(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            bin_dir = tmp_path / "bin"
            bin_dir.mkdir()

            cache_file = tmp_path / "cache-file"
            cache_file.write_text("not a directory", encoding="utf-8")
            local_log = tmp_path / "local.log"
            self.write_logging_stub(bin_dir / "local-notify", "TEST_LOCAL_NOTIFY_LOG")

            result = subprocess.run(
                [str(AGENT_NOTIFY_SCRIPT), "-a", "Codex", "Build", "Done"],
                capture_output=True,
                text=True,
                env=self.build_notify_env(
                    bin_dir,
                    {
                        "XDG_CACHE_HOME": str(cache_file),
                        "TEST_LOCAL_NOTIFY_LOG": str(local_log),
                    },
                ),
                check=False,
            )

            self.assertEqual(result.returncode, 0)
            self.assertEqual(result.stdout, "")
            self.assertEqual(result.stderr, "")
            self.assertEqual(self.read_log_lines(local_log), ["argc=4", "arg=-a", "arg=Codex", "arg=Build", "arg=Done"])

    def test_opencode_notify_routes_to_remote_notify_when_host_is_set(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            bin_dir = tmp_path / "bin"
            bin_dir.mkdir()

            remote_log = tmp_path / "remote.log"
            local_log = tmp_path / "local.log"
            self.install_agent_notify(bin_dir)
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

    def test_opencode_notify_delegates_to_agent_notify(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            bin_dir = tmp_path / "bin"
            bin_dir.mkdir()

            agent_log = tmp_path / "agent.log"
            self.write_logging_stub(bin_dir / "agent-notify", "TEST_AGENT_NOTIFY_LOG")

            env = self.build_notify_env(
                bin_dir,
                {
                    "TEST_AGENT_NOTIFY_LOG": str(agent_log),
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
                self.read_log_lines(agent_log),
                ["argc=4", "arg=-a", "arg=OpenCode", "arg=OpenCode - TaskComplete", "arg=Build passed"],
            )

    def test_opencode_notify_routes_to_local_notify_when_host_is_not_set(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            bin_dir = tmp_path / "bin"
            bin_dir.mkdir()

            remote_log = tmp_path / "remote.log"
            local_log = tmp_path / "local.log"
            self.install_agent_notify(bin_dir)
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

    def test_codex_notify_routes_to_remote_notify_when_host_is_set(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            bin_dir = tmp_path / "bin"
            bin_dir.mkdir()

            remote_log = tmp_path / "remote.log"
            local_log = tmp_path / "local.log"
            self.install_agent_notify(bin_dir)
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
                [str(CODEX_NOTIFY_SCRIPT), self.codex_payload()],
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
                [
                    "argc=4",
                    "arg=-a",
                    "arg=Codex",
                    "arg=agent-turn-complete",
                    "arg=好",
                    "",
                    "已增加通知日志，并已应用到当前机器。",
                ],
            )
            self.assertFalse(local_log.exists())

    def test_codex_notify_delegates_to_agent_notify(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            bin_dir = tmp_path / "bin"
            bin_dir.mkdir()

            agent_log = tmp_path / "agent.log"
            self.write_logging_stub(bin_dir / "agent-notify", "TEST_AGENT_NOTIFY_LOG")

            env = self.build_notify_env(
                bin_dir,
                {
                    "TEST_AGENT_NOTIFY_LOG": str(agent_log),
                },
            )

            result = subprocess.run(
                [str(CODEX_NOTIFY_SCRIPT), self.codex_payload()],
                capture_output=True,
                text=True,
                env=env,
                check=False,
            )

            self.assertEqual(result.returncode, 0)
            self.assertEqual(result.stdout, "")
            self.assertEqual(result.stderr, "")
            self.assertEqual(
                self.read_log_lines(agent_log),
                [
                    "argc=4",
                    "arg=-a",
                    "arg=Codex",
                    "arg=agent-turn-complete",
                    "arg=好",
                    "",
                    "已增加通知日志，并已应用到当前机器。",
                ],
            )

    def test_codex_notify_extracts_essential_fields_from_json_payload(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            bin_dir = tmp_path / "bin"
            bin_dir.mkdir()

            agent_log = tmp_path / "agent.log"
            self.write_logging_stub(bin_dir / "agent-notify", "TEST_AGENT_NOTIFY_LOG")

            result = subprocess.run(
                [str(CODEX_NOTIFY_SCRIPT), self.codex_payload()],
                capture_output=True,
                text=True,
                env=self.build_notify_env(
                    bin_dir,
                    {
                        "TEST_AGENT_NOTIFY_LOG": str(agent_log),
                    },
                ),
                check=False,
            )

            self.assertEqual(result.returncode, 0)
            self.assertEqual(result.stdout, "")
            self.assertEqual(result.stderr, "")
            self.assertEqual(
                self.read_log_lines(agent_log),
                [
                    "argc=4",
                    "arg=-a",
                    "arg=Codex",
                    "arg=agent-turn-complete",
                    "arg=好",
                    "",
                    "已增加通知日志，并已应用到当前机器。",
                ],
            )

    def test_codex_notify_uses_jq_for_json_payload(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            bin_dir = tmp_path / "bin"
            bin_dir.mkdir()

            agent_log = tmp_path / "agent.log"
            self.write_logging_stub(bin_dir / "agent-notify", "TEST_AGENT_NOTIFY_LOG")
            self.write_stub(bin_dir / "python3", "#!/bin/sh\nexit 127\n")

            payload = json.dumps(
                {
                    "type": "agent-turn-complete",
                    "cwd": "/home/yydcnjjw/.local/share/chezmoi",
                    "input-messages": ["使用 jq 解析"],
                    "last-assistant-message": "已切换为 jq。",
                },
                ensure_ascii=False,
            )

            result = subprocess.run(
                [str(CODEX_NOTIFY_SCRIPT), payload],
                capture_output=True,
                text=True,
                env=self.build_notify_env(
                    bin_dir,
                    {
                        "TEST_AGENT_NOTIFY_LOG": str(agent_log),
                    },
                ),
                check=False,
            )

            self.assertEqual(result.returncode, 0)
            self.assertEqual(result.stdout, "")
            self.assertEqual(result.stderr, "")
            self.assertEqual(
                self.read_log_lines(agent_log),
                [
                    "argc=4",
                    "arg=-a",
                    "arg=Codex",
                    "arg=agent-turn-complete",
                    "arg=使用 jq 解析",
                    "",
                    "已切换为 jq。",
                ],
            )

    def test_codex_notify_keeps_json_payload_notification_complete_for_mako(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            bin_dir = tmp_path / "bin"
            bin_dir.mkdir()

            agent_log = tmp_path / "agent.log"
            self.write_logging_stub(bin_dir / "agent-notify", "TEST_AGENT_NOTIFY_LOG")

            payload = json.dumps(
                {
                    "type": "agent-turn-complete",
                    "input-messages": [
                        "first request should not be shown",
                        "现在通知内容显示不全",
                    ],
                    "last-assistant-message": "这是一段很长的 assistant 回复内容，用来验证桌面通知不会继续展示过长正文。",
                },
                ensure_ascii=False,
            )

            result = subprocess.run(
                [str(CODEX_NOTIFY_SCRIPT), payload],
                capture_output=True,
                text=True,
                env=self.build_notify_env(
                    bin_dir,
                    {
                        "TEST_AGENT_NOTIFY_LOG": str(agent_log),
                    },
                ),
                check=False,
            )

            self.assertEqual(result.returncode, 0)
            self.assertEqual(result.stdout, "")
            self.assertEqual(result.stderr, "")
            self.assertEqual(
                self.read_log_lines(agent_log),
                [
                    "argc=4",
                    "arg=-a",
                    "arg=Codex",
                    "arg=agent-turn-complete",
                    "arg=现在通知内容显示不全",
                    "",
                    "这是一段很长的 assistant 回复内容，用来验证桌面通知不会继续展示过长正文。",
                ],
            )

    def test_codex_notify_routes_to_local_notify_when_host_is_not_set(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            bin_dir = tmp_path / "bin"
            bin_dir.mkdir()

            remote_log = tmp_path / "remote.log"
            local_log = tmp_path / "local.log"
            self.install_agent_notify(bin_dir)
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
                [str(CODEX_NOTIFY_SCRIPT), self.codex_payload()],
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
                [
                    "argc=4",
                    "arg=-a",
                    "arg=Codex",
                    "arg=agent-turn-complete",
                    "arg=好",
                    "",
                    "已增加通知日志，并已应用到当前机器。",
                ],
            )
            self.assertFalse(remote_log.exists())

    def test_codex_notify_prints_fallback_when_no_notifier_exists(self):
        with tempfile.TemporaryDirectory() as tmp:
            bin_dir = Path(tmp) / "bin"
            bin_dir.mkdir()
            self.install_agent_notify(bin_dir)

            env = self.build_notify_env(bin_dir)

            result = subprocess.run(
                [str(CODEX_NOTIFY_SCRIPT), self.codex_payload()],
                capture_output=True,
                text=True,
                env=env,
                check=False,
            )

            self.assertEqual(result.returncode, 0)
            self.assertEqual(
                result.stdout,
                "Notification: agent-turn-complete: 好\n\n已增加通知日志，并已应用到当前机器。\n",
            )
            self.assertEqual(result.stderr, "")

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
            "if '@tsv' in expr:\n"
            "    event = data.get('notification_type') or 'Notification'\n"
            "    message = data.get('message') or 'No message provided'\n"
            "    details = data.get('details') or {}\n"
            "    tool_name = details.get('tool_name', '') if isinstance(details, dict) else ''\n"
            "    if event == 'ToolPermission' and tool_name:\n"
            "        message = f'{message} ({tool_name})'\n"
            "    sys.stdout.write(f'{event}\\t{message}')\n"
            "    raise SystemExit(0)\n"
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
            self.install_agent_notify(bin_dir)
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

    def test_gemini_notify_delegates_to_agent_notify(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            bin_dir = tmp_path / "bin"
            bin_dir.mkdir()

            agent_log = tmp_path / "agent.log"
            self.write_logging_stub(bin_dir / "agent-notify", "TEST_AGENT_NOTIFY_LOG")
            self.write_fake_jq(bin_dir / "jq")

            env = self.build_notify_env(
                bin_dir,
                {
                    "TEST_AGENT_NOTIFY_LOG": str(agent_log),
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
                self.read_log_lines(agent_log),
                ["argc=4", "arg=-a", "arg=Gemini", "arg=Gemini - TaskComplete", "arg=Build passed"],
            )

    def test_gemini_notify_routes_to_local_notify_when_host_is_not_set(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            bin_dir = tmp_path / "bin"
            bin_dir.mkdir()

            remote_log = tmp_path / "remote.log"
            local_log = tmp_path / "local.log"
            self.install_agent_notify(bin_dir)
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

    def test_gemini_notify_uses_defaults_when_input_is_invalid_json(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            bin_dir = tmp_path / "bin"
            bin_dir.mkdir()

            agent_log = tmp_path / "agent.log"
            self.write_logging_stub(bin_dir / "agent-notify", "TEST_AGENT_NOTIFY_LOG")

            env = self.build_notify_env(
                bin_dir,
                {
                    "TEST_AGENT_NOTIFY_LOG": str(agent_log),
                },
            )

            result = subprocess.run(
                [str(GEMINI_NOTIFY_SCRIPT)],
                input='{"notification_type":',
                capture_output=True,
                text=True,
                env=env,
                check=False,
            )

            self.assertEqual(result.returncode, 0)
            self.assertEqual(result.stdout, "")
            self.assertEqual(result.stderr, "")
            self.assertEqual(
                self.read_log_lines(agent_log),
                ["argc=4", "arg=-a", "arg=Gemini", "arg=Gemini - Notification", "arg=No message provided"],
            )

    def test_gemini_settings_uses_local_bin_notify_hook(self):
        settings = json.loads(GEMINI_SETTINGS.read_text(encoding="utf-8"))
        command = settings["hooks"]["Notification"][0]["hooks"][0]["command"]
        self.assertEqual(command, "$HOME/.local/bin/gemini-notify")


if __name__ == "__main__":
    unittest.main()
