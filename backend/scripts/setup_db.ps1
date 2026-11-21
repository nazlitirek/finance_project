# BIST Intelligence - veritabani kurulumu (bir kez calistirin)
#
# backend\.env icindeki DATABASE_URL ve TEST_DATABASE_URL bilgilerini okur,
# PostgreSQL'de uygulama kullanicisini ve iki veritabanini (ana + test) olusturur.
# "postgres" yonetici sifresi sorulur; bu sifre hicbir yere kaydedilmez.

$ErrorActionPreference = "Stop"
$backend = Split-Path -Parent $PSScriptRoot
$envFile = Join-Path $backend ".env"
if (-not (Test-Path $envFile)) { throw ".env bulunamadi: $envFile (.env.example dosyasini kopyalayin)" }

function Read-DbUrl([string]$key) {
    $line = Get-Content $envFile -Encoding UTF8 | Where-Object { $_ -match "^$key=" } | Select-Object -First 1
    if (-not $line) { throw "$key .env icinde yok" }
    $url = $line.Substring($key.Length + 1)
    if ($url -notmatch '^postgresql(\+\w+)?://([^:]+):([^@]+)@([^:/]+)(:(\d+))?/(.+)$') { throw "$key bicimi taninmadi" }
    $port = if ($Matches[6]) { $Matches[6] } else { "5432" }
    return @{ User = $Matches[2]; Password = $Matches[3]; Host = $Matches[4]; Port = $port; Db = $Matches[7] }
}

$main = Read-DbUrl "DATABASE_URL"
$test = Read-DbUrl "TEST_DATABASE_URL"
if ($main.User -ne $test.User) { throw "Ana ve test veritabani ayni kullaniciyi kullanmali" }

$psql = "C:\Program Files\PostgreSQL\18\bin\psql.exe"
if (-not (Test-Path $psql)) { $psql = "psql" }

$user = $main.User
$pw = $main.Password.Replace("'", "''")
$sql = @"
DO `$`$ BEGIN
  IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = '$user') THEN
    CREATE ROLE $user LOGIN PASSWORD '$pw';
  ELSE
    ALTER ROLE $user WITH LOGIN PASSWORD '$pw';
  END IF;
END `$`$;
SELECT 'CREATE DATABASE $($main.Db) OWNER $user ENCODING ''UTF8'' TEMPLATE template0'
  WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname = '$($main.Db)') \gexec
SELECT 'CREATE DATABASE $($test.Db) OWNER $user ENCODING ''UTF8'' TEMPLATE template0'
  WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname = '$($test.Db)') \gexec
"@

$secure = Read-Host "PostgreSQL 'postgres' kullanicisinin sifresi" -AsSecureString
$env:PGPASSWORD = [Runtime.InteropServices.Marshal]::PtrToStringBSTR(
    [Runtime.InteropServices.Marshal]::SecureStringToBSTR($secure))
try {
    $sql | & $psql -h $main.Host -p $main.Port -U postgres -d postgres -v ON_ERROR_STOP=1
    if ($LASTEXITCODE -ne 0) { throw "psql hata verdi (cikis kodu $LASTEXITCODE)" }

    # pg_trgm uzantisi (hizli isim aramasi icin) - yonetici olarak her iki veritabaninda
    foreach ($db in @($main.Db, $test.Db)) {
        "CREATE EXTENSION IF NOT EXISTS pg_trgm;" | & $psql -h $main.Host -p $main.Port -U postgres -d $db -v ON_ERROR_STOP=1
        if ($LASTEXITCODE -ne 0) { throw "pg_trgm olusturulamadi ($db)" }
    }
} finally {
    Remove-Item Env:PGPASSWORD -ErrorAction SilentlyContinue
}

Write-Host ""
Write-Host "Tamam: kullanici '$user', veritabanlari '$($main.Db)' ve '$($test.Db)' hazir."
