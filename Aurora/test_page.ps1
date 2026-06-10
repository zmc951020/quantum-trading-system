$r = Invoke-WebRequest -Uri 'http://127.0.0.1:5002/' -UseBasicParsing
$lines = $r.Content -split "`n"
$lines[0..30]
