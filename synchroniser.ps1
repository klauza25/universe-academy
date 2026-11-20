# Synchronisation planifiée : migrations puis classeurs Google.
#
#   .\synchroniser.ps1                  # récupère, analyse et écrit en base
#   .\synchroniser.ps1 -SansEcrire      # récupère et analyse seulement
#   .\synchroniser.ps1 -Credentials C:\chemin\service-account.json
#
# À appeler depuis le Planificateur de tâches Windows (voir
# docs/SYNCHRONISATION_GOOGLE.md). Chaque passage est ajouté à
# synchronisation.log, archivé dans synchronisation.log.1 au-delà de 5 Mo.
# Deux passages ne peuvent pas se chevaucher ; sans compte de service, la
# synchronisation tente l'export public des feuilles (à partager en lecture).

param(
    [switch]$SansEcrire,
    [string]$Credentials
)

$ErrorActionPreference = 'Continue'
Set-Location $PSScriptRoot

$journal = Join-Path $PSScriptRoot 'synchronisation.log'
$tailleMax = 5MB

function Ecrire-Journal {
    param([string]$Message)
    $Message *>> $journal
}

function Passer-Journal {
    if (-not (Test-Path $journal)) { return }
    if ((Get-Item $journal).Length -ge $tailleMax) {
        Move-Item -Path $journal -Destination "$journal.1" -Force
    }
}

function Resoudre-Chemin {
    param([string]$Chemin)
    if (-not $Chemin) { return $Chemin }
    if ($Chemin.StartsWith('~')) {
        $reste = $Chemin.Substring(1).TrimStart('\', '/')
        $Chemin = Join-Path $HOME $reste
    }
    return [Environment]::ExpandEnvironmentVariables($Chemin)
}

Passer-Journal

$debut = Get-Date
Ecrire-Journal ('===== {0} =====' -f $debut.ToString('yyyy-MM-dd HH:mm:ss'))
if ($SansEcrire) {
    Ecrire-Journal 'Mode : prévisualisation (aucune écriture en base).'
}

$python = Join-Path $PSScriptRoot '.venv\Scripts\python.exe'
if (-not (Test-Path $python)) { $python = 'python' }
if (-not (Get-Command $python -ErrorAction SilentlyContinue)) {
    Ecrire-Journal 'Python introuvable : synchronisation annulée.'
    exit 1
}

# Un seul passage à la fois : une synchronisation lente ne doit pas être
# rejointe par le déclenchement suivant.
$mutex = New-Object System.Threading.Mutex(
    $false, 'Local\UniversAcademySynchronisation')
$verrou = $false
try {
    try {
        $verrou = $mutex.WaitOne(0)
    } catch [System.Threading.AbandonedMutexException] {
        # Le passage précédent s'est arrêté sans rendre le verrou : on le
        # reprend, le système nous en donne la propriété.
        $verrou = $true
    }

    if (-not $verrou) {
        Ecrire-Journal 'Un passage est déjà en cours : celui-ci est ignoré.'
        exit 0
    }

    & $python manage.py migrer *>> $journal
    if ($LASTEXITCODE -ne 0) {
        Ecrire-Journal 'Migrations en échec : arrêt de la synchronisation.'
        exit $LASTEXITCODE
    }

    $identifiants = Resoudre-Chemin $Credentials
    if (-not $identifiants) {
        $identifiants = Resoudre-Chemin $env:GOOGLE_APPLICATION_CREDENTIALS
    }
    if (-not $identifiants) {
        $identifiants = Join-Path $HOME '.config\academy\service-account.json'
    }

    $arguments = @('manage.py', 'synchroniser_classeurs')
    if (Test-Path -LiteralPath $identifiants -PathType Leaf) {
        $arguments += @('--credentials', $identifiants)
    } else {
        Ecrire-Journal ("Compte de service absent : {0}" -f $identifiants)
        Ecrire-Journal 'Tentative en export public : les feuilles doivent être partagées en lecture.'
    }
    if (-not $SansEcrire) { $arguments += '--ecrire' }

    & $python @arguments *>> $journal
    $code = $LASTEXITCODE
    $duree = [int]((Get-Date) - $debut).TotalSeconds

    if ($code -eq 0) {
        Ecrire-Journal ("Terminé en {0} s." -f $duree)
    } else {
        Ecrire-Journal ("Échec (code {0}) après {1} s." -f $code, $duree)
    }
    exit $code
}
finally {
    if ($verrou) { $mutex.ReleaseMutex() }
    $mutex.Dispose()
}
