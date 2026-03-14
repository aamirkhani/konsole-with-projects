"""Tests for the new modules: FindMyMouse, PasteAsPlainText, Peek, ShortcutGuide,
VideoConferenceMute, Workspaces, AlwaysOnTop, EnvVars."""

import os
import sys
import json
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

# ---------------------------------------------------------------------------
# FindMyMouse
# ---------------------------------------------------------------------------

from powertoys.modules.findmymouse.engine import FindMyMouseEngine, get_screen_size


def test_findmymouse_engine_defaults():
    eng = FindMyMouseEngine()
    assert eng.spotlight_radius == 100
    assert 0 < eng.overlay_opacity <= 1.0
    assert eng.animation_duration_ms > 0


def test_get_screen_size_returns_positive():
    w, h = get_screen_size()
    assert w > 0
    assert h > 0


def test_findmymouse_get_cursor_may_return_none_or_tuple():
    eng = FindMyMouseEngine()
    pos = eng.get_cursor_position()
    # Without X11, returns None; with X11, returns tuple
    assert pos is None or (isinstance(pos, tuple) and len(pos) == 2)


# ---------------------------------------------------------------------------
# PasteAsPlainText
# ---------------------------------------------------------------------------

from powertoys.modules.pasteplain.engine import (
    PastePlainEngine, strip_html, strip_markdown, normalize_whitespace
)


def test_strip_html_basic():
    result = strip_html("<b>Hello</b> <i>World</i>")
    assert "Hello" in result
    assert "World" in result
    assert "<b>" not in result


def test_strip_html_entities():
    result = strip_html("&amp; &lt; &gt; &quot;")
    assert "&" in result
    assert "<" in result
    assert ">" in result
    assert '"' in result


def test_strip_html_block_tags_become_newlines():
    result = strip_html("<p>First</p><p>Second</p>")
    assert "First" in result
    assert "Second" in result


def test_strip_html_br():
    result = strip_html("Line1<br>Line2")
    assert "\n" in result


def test_strip_markdown_headers():
    result = strip_markdown("# Title\n## Sub\nText")
    assert "Title" in result
    assert "#" not in result


def test_strip_markdown_bold():
    result = strip_markdown("**bold** text")
    assert "bold" in result
    assert "**" not in result


def test_strip_markdown_links():
    result = strip_markdown("[Link text](https://example.com)")
    assert "Link text" in result
    assert "https://example.com" not in result
    assert "[" not in result


def test_normalize_whitespace():
    text = "  hello  \n  world  "
    result = normalize_whitespace(text)
    assert result.endswith("world")
    assert not result.startswith(" ")


def test_normalize_whitespace_collapse_blank_lines():
    text = "line1\n\n\n\nline2"
    result = normalize_whitespace(text, collapse_lines=True)
    # Should have at most one blank line
    assert "\n\n\n" not in result


def test_paste_plain_engine_process():
    eng = PastePlainEngine()
    eng.strip_html_tags = True
    eng.strip_markdown_syntax = True
    result = eng.process("<b>**hello**</b>")
    assert "hello" in result
    assert "<b>" not in result
    assert "**" not in result


def test_paste_plain_engine_html_only():
    eng = PastePlainEngine()
    eng.strip_html_tags = True
    eng.strip_markdown_syntax = False
    result = eng.process("<em>*text*</em>")
    assert "*text*" in result
    assert "<em>" not in result


# ---------------------------------------------------------------------------
# Peek
# ---------------------------------------------------------------------------

from powertoys.modules.peek.engine import (
    PeekEngine, classify_file, FileInfo, read_text_preview, _human_size
)


def test_human_size():
    assert "B" in _human_size(500)
    assert "KB" in _human_size(2048)
    assert "MB" in _human_size(2 * 1024 * 1024)
    assert "GB" in _human_size(2 * 1024 ** 3)


def test_classify_text_file():
    with tempfile.NamedTemporaryFile(suffix=".txt", delete=False, mode="w") as f:
        f.write("hello world")
        name = f.name
    try:
        info = classify_file(Path(name))
        assert info.category == "text"
        assert info.size > 0
    finally:
        os.unlink(name)


def test_classify_python_file():
    with tempfile.NamedTemporaryFile(suffix=".py", delete=False, mode="w") as f:
        f.write("print('hi')")
        name = f.name
    try:
        info = classify_file(Path(name))
        assert info.category == "text"
    finally:
        os.unlink(name)


def test_classify_json_file():
    with tempfile.NamedTemporaryFile(suffix=".json", delete=False, mode="w") as f:
        f.write('{"key": "value"}')
        name = f.name
    try:
        info = classify_file(Path(name))
        assert info.category == "text"
    finally:
        os.unlink(name)


def test_read_text_preview():
    with tempfile.NamedTemporaryFile(suffix=".txt", delete=False, mode="w") as f:
        f.write("hello\nworld\n")
        name = f.name
    try:
        content = read_text_preview(Path(name))
        assert "hello" in content
        assert "world" in content
    finally:
        os.unlink(name)


def test_read_text_preview_max_chars():
    with tempfile.NamedTemporaryFile(suffix=".txt", delete=False, mode="w") as f:
        f.write("A" * 1000)
        name = f.name
    try:
        content = read_text_preview(Path(name), max_chars=100)
        assert len(content) <= 100
    finally:
        os.unlink(name)


def test_peek_engine_open_with_default_missing_file():
    eng = PeekEngine()
    result = eng.open_with_default(Path("/nonexistent/file.txt"))
    # Either True (xdg-open launched) or False (not found)
    assert isinstance(result, bool)


# ---------------------------------------------------------------------------
# ShortcutGuide
# ---------------------------------------------------------------------------

from powertoys.modules.shortcutguide.engine import (
    ShortcutGuideEngine, ShortcutEntry, BUILTIN_SHORTCUTS,
    get_categories, get_contexts
)


def test_builtin_shortcuts_not_empty():
    assert len(BUILTIN_SHORTCUTS) > 10


def test_all_shortcuts_have_keys_and_desc():
    for s in BUILTIN_SHORTCUTS:
        assert s.keys
        assert s.description


def test_get_categories():
    cats = get_categories()
    assert "All" in cats
    assert len(cats) > 1


def test_get_contexts():
    ctxs = get_contexts()
    assert "All" in ctxs


def test_shortcut_guide_search():
    eng = ShortcutGuideEngine()
    results = eng.search("copy")
    assert len(results) > 0
    for r in results:
        assert "copy" in r.keys.lower() or "copy" in r.description.lower()


def test_shortcut_guide_filter_category():
    eng = ShortcutGuideEngine()
    results = eng.filter(category="Terminal")
    assert all(r.category == "Terminal" for r in results)


def test_shortcut_guide_filter_all():
    eng = ShortcutGuideEngine()
    results = eng.filter(category="All", context="All")
    assert len(results) == len(BUILTIN_SHORTCUTS)


def test_shortcut_guide_add_custom():
    eng = ShortcutGuideEngine()
    entry = ShortcutEntry(keys="Ctrl+Q", description="Quit application", category="Custom")
    eng.add_custom(entry)
    assert len(eng._custom) == 1
    assert eng.all_shortcuts[-1].keys == "Ctrl+Q"


def test_shortcut_guide_remove_custom():
    eng = ShortcutGuideEngine()
    entry = ShortcutEntry(keys="Ctrl+Q", description="Quit", category="Custom")
    eng.add_custom(entry)
    eng.remove_custom(0)
    assert len(eng._custom) == 0


def test_shortcut_guide_search_empty_query():
    eng = ShortcutGuideEngine()
    results = eng.search("")
    assert len(results) > 0


# ---------------------------------------------------------------------------
# VideoConferenceMute
# ---------------------------------------------------------------------------

from powertoys.modules.videomute.engine import VideoMuteEngine, list_cameras


def test_video_mute_engine_defaults():
    eng = VideoMuteEngine()
    assert not eng.mic_muted
    assert not eng.cam_blocked


def test_list_cameras_returns_list():
    cams = list_cameras()
    assert isinstance(cams, list)
    # All should be /dev/video* paths
    for cam in cams:
        assert cam.startswith("/dev/video")


def test_get_microphones_returns_list():
    eng = VideoMuteEngine()
    mics = eng.get_microphones()
    assert isinstance(mics, list)


def test_get_cameras_returns_list():
    eng = VideoMuteEngine()
    cams = eng.get_cameras()
    assert isinstance(cams, list)


def test_get_active_cameras_returns_list():
    eng = VideoMuteEngine()
    active = eng.get_active_cameras()
    assert isinstance(active, list)


# ---------------------------------------------------------------------------
# Workspaces
# ---------------------------------------------------------------------------

from powertoys.modules.workspaces.engine import (
    WorkspacesEngine, Workspace, WindowState, capture_window_layout
)


def test_workspace_to_dict_from_dict():
    ws = Workspace(name="Test", description="My workspace")
    ws.windows.append(WindowState(
        window_id="0x1", title="Terminal", pid=100,
        x=0, y=0, width=800, height=600
    ))
    d = ws.to_dict()
    assert d["name"] == "Test"
    assert len(d["windows"]) == 1
    ws2 = Workspace.from_dict(d)
    assert ws2.name == "Test"
    assert ws2.windows[0].title == "Terminal"


def test_workspaces_engine_save_restore(tmp_path):
    import powertoys.modules.workspaces.engine as eng_mod
    original_file = eng_mod.WORKSPACES_FILE
    eng_mod.WORKSPACES_FILE = tmp_path / "workspaces.json"
    try:
        eng = WorkspacesEngine()
        assert eng.workspaces == []

        # Manually add a workspace
        ws = Workspace(name="Dev", description="Dev layout")
        eng._workspaces.append(ws)
        eng._save()

        # Reload
        eng2 = WorkspacesEngine()
        assert len(eng2.workspaces) == 1
        assert eng2.workspaces[0].name == "Dev"
    finally:
        eng_mod.WORKSPACES_FILE = original_file


def test_workspaces_engine_delete(tmp_path):
    import powertoys.modules.workspaces.engine as eng_mod
    original_file = eng_mod.WORKSPACES_FILE
    eng_mod.WORKSPACES_FILE = tmp_path / "workspaces.json"
    try:
        eng = WorkspacesEngine()
        eng._workspaces.append(Workspace(name="A"))
        eng._workspaces.append(Workspace(name="B"))
        eng._save()
        eng.delete("A")
        assert len(eng.workspaces) == 1
        assert eng.workspaces[0].name == "B"
    finally:
        eng_mod.WORKSPACES_FILE = original_file


def test_workspaces_engine_rename(tmp_path):
    import powertoys.modules.workspaces.engine as eng_mod
    original_file = eng_mod.WORKSPACES_FILE
    eng_mod.WORKSPACES_FILE = tmp_path / "workspaces.json"
    try:
        eng = WorkspacesEngine()
        eng._workspaces.append(Workspace(name="Old"))
        eng._save()
        eng.rename("Old", "New")
        assert eng.workspaces[0].name == "New"
    finally:
        eng_mod.WORKSPACES_FILE = original_file


def test_capture_window_layout_returns_list():
    windows = capture_window_layout()
    assert isinstance(windows, list)


def test_window_state_fields():
    ws = WindowState(
        window_id="0x1", title="Test", pid=1234,
        x=10, y=20, width=800, height=600
    )
    assert ws.window_id == "0x1"
    assert ws.title == "Test"
    assert ws.x == 10
    assert ws.width == 800


# ---------------------------------------------------------------------------
# AlwaysOnTop
# ---------------------------------------------------------------------------

from powertoys.modules.alwaysontop.engine import (
    AlwaysOnTopEngine, ManagedWindow, list_windows
)


def test_always_on_top_engine_defaults():
    eng = AlwaysOnTopEngine()
    assert eng.pinned_count == 0


def test_always_on_top_list_windows_returns_list():
    windows = list_windows()
    assert isinstance(windows, list)


def test_always_on_top_pin_unpin():
    eng = AlwaysOnTopEngine()
    w = ManagedWindow(window_id="0xfake", title="Test", pid=0)
    # set_window_on_top will fail (no real window), but the data structure is testable
    # We just verify the engine doesn't crash
    # Without X11, wmctrl returns None so ok=False
    result = eng.pin(w)
    assert isinstance(result, bool)


def test_always_on_top_toggle():
    eng = AlwaysOnTopEngine()
    w = ManagedWindow(window_id="0xfake", title="Test", pid=0)
    result = eng.toggle(w)
    assert isinstance(result, bool)


def test_always_on_top_unpin_all():
    eng = AlwaysOnTopEngine()
    eng.unpin_all()
    assert eng.pinned_count == 0


# ---------------------------------------------------------------------------
# EnvVars
# ---------------------------------------------------------------------------

from powertoys.modules.envvars.engine import EnvVarsEngine, EnvVar


def test_envvar_validate_valid():
    v = EnvVar(name="MY_VAR", value="hello")
    assert v.validate() is None


def test_envvar_validate_empty_name():
    v = EnvVar(name="", value="hello")
    assert v.validate() is not None


def test_envvar_validate_invalid_name():
    v = EnvVar(name="123BAD", value="hello")
    assert v.validate() is not None


def test_envvar_validate_underscore_start():
    v = EnvVar(name="_OK_VAR", value="hello")
    assert v.validate() is None


def test_envvar_is_path_var():
    v = EnvVar(name="PATH", value="/usr/bin")
    assert v.is_path_var

    v2 = EnvVar(name="HOME", value="/root")
    assert not v2.is_path_var


def test_envvar_modified():
    v = EnvVar(name="X", value="new", original_value="old")
    assert v.modified

    v2 = EnvVar(name="X", value="same", original_value="same")
    assert not v2.modified


def test_envvars_engine_loads_session():
    eng = EnvVarsEngine()
    # Should have at least PATH and HOME
    names = [v.name for v in eng.get_all("session")]
    assert "PATH" in names


def test_envvars_engine_search():
    eng = EnvVarsEngine()
    results = eng.search("PATH")
    assert len(results) > 0
    for r in results:
        assert "path" in r.name.lower() or "path" in r.value.lower()


def test_envvars_engine_get_path_entries():
    eng = EnvVarsEngine()
    entries = eng.get_path_entries()
    assert isinstance(entries, list)
    assert len(entries) > 0


def test_envvars_engine_set_session():
    eng = EnvVarsEngine()
    eng.set_session("_PT_TEST_VAR_", "test_value")
    results = eng.search("_PT_TEST_VAR_")
    assert len(results) > 0
    assert results[0].value == "test_value"
    eng.delete_session("_PT_TEST_VAR_")


def test_envvars_engine_delete_session():
    eng = EnvVarsEngine()
    eng.set_session("_PT_DELETE_TEST_", "val")
    eng.delete_session("_PT_DELETE_TEST_")
    results = eng.search("_PT_DELETE_TEST_")
    assert all(r.name != "_PT_DELETE_TEST_" for r in results)


def test_envvars_engine_export_shell():
    eng = EnvVarsEngine()
    var = EnvVar(name="HELLO", value="world")
    script = eng.export_as_shell([var])
    assert "export HELLO=" in script
    assert "world" in script


def test_envvars_save_to_profile_tmp(tmp_path):
    eng = EnvVarsEngine()
    target = tmp_path / "testprofile"
    target.write_text("")
    var = EnvVar(name="MY_TEST_VAR", value="42", source="profile")
    err = eng.save_to_profile(var, profile_file=target)
    assert err is None
    content = target.read_text()
    assert "MY_TEST_VAR" in content
    assert "42" in content


def test_envvars_save_to_profile_disabled(tmp_path):
    eng = EnvVarsEngine()
    target = tmp_path / "testprofile"
    target.write_text("")
    var = EnvVar(name="DISABLED_VAR", value="x", source="profile", enabled=False)
    err = eng.save_to_profile(var, profile_file=target)
    assert err is None
    content = target.read_text()
    assert "DISABLED_VAR" not in content


def test_envvars_parse_shell_exports(tmp_path):
    profile = tmp_path / ".profile"
    profile.write_text(
        'export FOO="bar"\nexport BAZ=qux\n# comment\nexport WITH_SPACE="hello world"\n'
    )
    eng = EnvVarsEngine()
    results = dict(eng._parse_shell_exports(profile))
    assert results.get("FOO") == "bar"
    assert results.get("BAZ") == "qux"
    assert results.get("WITH_SPACE") == "hello world"


def test_envvars_parse_etc_environment(tmp_path):
    env_file = tmp_path / "environment"
    env_file.write_text("PATH=/usr/bin:/bin\nLANG=en_US.UTF-8\n# comment\n\n")
    eng = EnvVarsEngine()
    results = dict(eng._parse_etc_environment(env_file))
    assert results.get("PATH") == "/usr/bin:/bin"
    assert results.get("LANG") == "en_US.UTF-8"
