"""Build the small GitHub-backed Windows launcher."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BOOTSTRAP = Path(__file__).with_name("bootstrap.ps1")
OUTPUT = ROOT / "Кадр — встановити і запустити.bat"


def main() -> None:
    header = '''@echo off
setlocal
set "KADR_SELF=%~f0"
powershell.exe -NoProfile -ExecutionPolicy Bypass -Command "$raw=[IO.File]::ReadAllText($env:KADR_SELF,[Text.Encoding]::UTF8); $mark='@@KADR_PS@@'; $a=$raw.LastIndexOf($mark)+$mark.Length; if($a -lt $mark.Length){throw 'Invalid Kadr launcher'}; Invoke-Expression $raw.Substring($a)"
exit /b %errorlevel%
@@KADR_PS@@
'''
    OUTPUT.write_text(header + BOOTSTRAP.read_text(encoding="utf-8").rstrip() + "\n", encoding="utf-8", newline="\r\n")
    print(f"{OUTPUT}: {OUTPUT.stat().st_size:,} bytes")


if __name__ == "__main__":
    main()
