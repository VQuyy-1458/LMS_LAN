param(
    [Parameter(Mandatory=$true)][ValidateRange(1,65535)][int]$Port,
    [Parameter(Mandatory=$true)][string]$PythonPath,
    [Parameter(Mandatory=$true)][ValidatePattern('^LMS_LAN-Run-[a-f0-9]{12}-[0-9]+$')][string]$RuleName,
    [switch]$CheckOnly
)
$ErrorActionPreference='Stop'
$rule=Get-NetFirewallRule -Name $RuleName -ErrorAction SilentlyContinue
if($rule){
    $portFilter=$rule | Get-NetFirewallPortFilter
    $addressFilter=$rule | Get-NetFirewallAddressFilter
    $applicationFilter=$rule | Get-NetFirewallApplicationFilter
    if($rule.Enabled -eq 'True' -and $rule.Direction -eq 'Inbound' -and $rule.Action -eq 'Allow' -and $rule.Profile -eq 'Any' -and $portFilter.LocalPort -eq [string]$Port -and $portFilter.Protocol -eq 'TCP' -and $addressFilter.RemoteAddress -eq 'LocalSubnet' -and $applicationFilter.Program -eq $PythonPath){exit 0}
}
if($CheckOnly){exit 2}
$identity=[Security.Principal.WindowsIdentity]::GetCurrent()
$principal=New-Object Security.Principal.WindowsPrincipal($identity)
if(-not $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)){
    $arguments=@('-NoProfile','-ExecutionPolicy','Bypass','-File',('"'+$PSCommandPath+'"'),'-Port',[string]$Port,'-PythonPath',('"'+$PythonPath+'"'),'-RuleName',$RuleName)
    try{
        $child=Start-Process -FilePath 'powershell.exe' -ArgumentList $arguments -Verb RunAs -WindowStyle Hidden -Wait -PassThru
        exit $child.ExitCode
    }catch{Write-Error 'Firewall permission was not granted.';exit 1}
}
if(-not (Test-Path -LiteralPath $PythonPath -PathType Leaf)){throw 'Python executable not found.'}
if($rule){Remove-NetFirewallRule -Name $RuleName}
# Allow this Python executable and TCP port only, from the local subnet.
# Include the current network even when Windows classifies it as Public.
New-NetFirewallRule -Name $RuleName -DisplayName "LMS_LAN - Web LAN ($Port)" -Direction Inbound -Action Allow -Enabled True -Protocol TCP -LocalPort $Port -RemoteAddress LocalSubnet -Profile Any -Program $PythonPath | Out-Null
exit 0
