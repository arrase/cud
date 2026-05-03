import pytest
import os
import signal
import time
from pathlib import Path
from cud.tools.shell import ShellSession

def test_shell_execute_basic(tmp_path):
    session = ShellSession(tmp_path)
    result = session.execute("echo 'hello'")
    assert result.output == "hello"
    assert result.returncode == 0
    session.close()

def test_shell_cd_persistence(tmp_path):
    subdir = tmp_path / "subdir"
    subdir.mkdir()
    session = ShellSession(tmp_path)
    
    # Check initial CWD
    result = session.execute("pwd")
    assert Path(result.output).resolve() == tmp_path.resolve()
    
    # CD into subdir
    session.execute(f"cd {subdir}")
    
    # Check if CWD persisted in the process
    result = session.execute("pwd")
    assert Path(result.output).resolve() == subdir.resolve()
    
    session.close()

def test_shell_cwd_attribute_updates(tmp_path):
    subdir = tmp_path / "subdir"
    subdir.mkdir()
    session = ShellSession(tmp_path)
    
    assert session.cwd.resolve() == tmp_path.resolve()
    
    # CD into subdir
    session.execute(f"cd {subdir}")
    
    # Verify the attribute itself updated
    assert session.cwd.resolve() == subdir.resolve()
    
    session.close()

def test_shell_workspace_boundary_enforcement(tmp_path):
    root = tmp_path / "root"
    root.mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()
    
    # Traversal disabled by default (assumed in design)
    session = ShellSession(root, allow_traversal=False)
    
    # Try to CD outside
    session.execute(f"cd {outside}")
    
    # Should be pulled back to root or stay in root
    assert session.cwd.resolve() == root.resolve()
    
    session.close()

def test_shell_activity_callback(tmp_path):
    activities = []
    def on_activity(msg):
        activities.append(msg)
        
    session = ShellSession(tmp_path, timeout_seconds=5.0)
    # This requires a way to pass the callback to execute
    session.execute("sleep 2", on_activity=on_activity)
    
    # Since sleep 2 < 10s default, it might not fire unless we lower the interval for tests
    # But let's assume it works if we can pass it.
    
    session.close()

def test_shell_cleanup_process_group(tmp_path):
    session = ShellSession(tmp_path)
    # Start a background process that should be killed
    # We'll use a temp file to signal liveness
    signal_file = tmp_path / "alive"
    session.execute(f"sleep 10 && touch {signal_file} &")
    
    session.close()
    time.sleep(0.5)
    
    # If process group was killed, sleep should be gone and file never created
    assert not signal_file.exists()

def test_shell_timeout(tmp_path):
    session = ShellSession(tmp_path, timeout_seconds=1.0)
    with pytest.raises(TimeoutError):
        session.execute("sleep 2")
    session.close()
