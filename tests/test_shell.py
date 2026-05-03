import pytest
import os
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

def test_shell_timeout(tmp_path):
    session = ShellSession(tmp_path, timeout_seconds=1.0)
    with pytest.raises(TimeoutError):
        session.execute("sleep 2")
    session.close()
