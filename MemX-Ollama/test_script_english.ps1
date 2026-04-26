# Test script
Write-Host "Testing PowerShell script execution..."
Write-Host "Current directory: $(Get-Location)"

# Check if file exists
if (Test-Path "main.py") {
    Write-Host "main.py file exists"
} else {
    Write-Host "main.py file does not exist"
}

Read-Host "Press Enter to exit..."