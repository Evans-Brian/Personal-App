# Keep the local journal available while this Windows user is signed in.
$ErrorActionPreference = 'Stop'
$journalRoot = $PSScriptRoot
$pythonExe = (Get-Command python -ErrorAction Stop).Source
$pythonWindowless = Join-Path (Split-Path $pythonExe) 'pythonw.exe'
if (-not (Test-Path -LiteralPath $pythonWindowless)) { throw 'pythonw.exe not found.' }
$journalUser = [System.Security.Principal.WindowsIdentity]::GetCurrent().Name
$action = New-ScheduledTaskAction -Execute $pythonWindowless -Argument ('"' + (Join-Path $journalRoot 'launcher.py') + '" --background') -WorkingDirectory $journalRoot
$login = New-ScheduledTaskTrigger -AtLogOn -User $journalUser
$recovery = New-ScheduledTaskTrigger -Once -At (Get-Date).AddMinutes(1) -RepetitionInterval (New-TimeSpan -Minutes 1)
$settings = New-ScheduledTaskSettingsSet -MultipleInstances IgnoreNew -ExecutionTimeLimit ([TimeSpan]::Zero) -StartWhenAvailable -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -RestartCount 3 -RestartInterval (New-TimeSpan -Minutes 1)
$principal = New-ScheduledTaskPrincipal -UserId $journalUser -LogonType Interactive -RunLevel Limited
Register-ScheduledTask -TaskName 'Personal Journal' -Action $action -Trigger @($login,$recovery) -Settings $settings -Principal $principal -Description 'Local journal on 127.0.0.1:8765; recovers stopped server while signed in.' -Force | Out-Null
Start-ScheduledTask -TaskName 'Personal Journal'
Write-Output 'Personal Journal registered with login startup and one-minute recovery.'
