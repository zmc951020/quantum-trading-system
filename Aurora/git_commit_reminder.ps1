param(
    [ValidateSet("check", "remind")]
    [string]$Action = "check"
)

$ProjectPath = $PSScriptRoot

function Get-GitStatus {
    Push-Location $ProjectPath
    try {
        $status = git status --porcelain 2>$null
        $branch = git branch --show-current 2>$null
        return @{
            HasChanges = $status.Count -gt 0
            ChangeCount = $status.Count
            Branch = $branch
        }
    } finally {
        Pop-Location
    }
}

Add-Type -AssemblyName PresentationFramework

$status = Get-GitStatus

if ($Action -eq "check") {
    if ($status.HasChanges) {
        Write-Host "[$(Get-Date -Format 'HH:mm:ss')] Found $($status.ChangeCount) uncommitted changes on branch: $($status.Branch)"
        $msg = "Branch: $($status.Branch)`nUncommitted changes: $($status.ChangeCount)`n`nDo you want to commit today's changes?"
        $result = [System.Windows.MessageBox]::Show($msg, "Git Commit Reminder", "YesNo", "Question")
        if ($result -eq "Yes") {
            Start-Process "code" -ArgumentList $ProjectPath
        }
    } else {
        Write-Host "[$(Get-Date -Format 'HH:mm:ss')] Working directory clean"
    }
} elseif ($Action -eq "remind") {
    $msg = "Branch: $($status.Branch)`nUncommitted changes: $($status.ChangeCount)`n`nDo you want to commit today's changes?"
    [System.Windows.MessageBox]::Show($msg, "Git Commit Reminder", "YesNo", "Question")
}
