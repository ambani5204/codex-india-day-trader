$ErrorActionPreference='Stop'
Set-Location $PSScriptRoot
py -3 -m unittest discover -s tests -v
if ($LASTEXITCODE -ne 0) { throw 'Tests failed' }
Write-Host 'Skills installed locally in .agents/skills/. Open this directory in VS Code Codex.'
Write-Host 'Optional global: Copy-Item .agents/skills/trader-* "$HOME/.agents/skills/" -Recurse -Force'
