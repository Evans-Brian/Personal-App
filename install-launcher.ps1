$ErrorActionPreference = 'Stop'
$journalRoot = $PSScriptRoot
$pythonExe = (Get-Command python -ErrorAction Stop).Source
$pythonWindowless = Join-Path (Split-Path $pythonExe) 'pythonw.exe'
if (-not (Test-Path -LiteralPath $pythonWindowless)) { throw 'pythonw.exe was not found beside Python.' }
$shortcutShell = New-Object -ComObject WScript.Shell
foreach ($destination in @(
    @{Folder=[Environment]::GetFolderPath('Desktop'); Arguments=''},
    @{Folder=[Environment]::GetFolderPath('Startup'); Arguments=' --background'}
)) {
    $shortcutPath = Join-Path $destination.Folder 'Personal Journal.lnk'
    $shortcut = $shortcutShell.CreateShortcut($shortcutPath)
    $shortcut.TargetPath = $pythonWindowless
    $shortcut.Arguments = '"' + (Join-Path $journalRoot 'launcher.py') + '"' + $destination.Arguments
    $shortcut.WorkingDirectory = $journalRoot
    $shortcut.WindowStyle = 7
    $shortcut.Description = 'Local personal journal — http://127.0.0.1:8765'
    $shortcut.Save()
    Write-Output $shortcutPath
}
