# =============================================================================
# CloudGuard AI — Windows equivalent of the Makefile
# =============================================================================
# Why this exists: `make` is not installed on Windows by default, and our founder develops
# on Windows 11. Rather than force a WSL/chocolatey detour on day one, we mirror the exact
# same targets. Both files MUST stay in sync — if you add a target to one, add it to both.
#
# Usage:  .\make.ps1 dev
# =============================================================================

param([Parameter(Position = 0)][string]$Target = "help")

# Windows defaults Python's file I/O to the legacy cp1252 codec. Our source files are UTF-8
# (the docstrings are full of →, ×, ⚠️), so tools that read source with the locale encoding —
# import-linter is one — crash with `'charmap' codec can't decode byte 0x8f`.
# Linux and our containers are UTF-8 already; this line only fixes the Windows host.
$env:PYTHONUTF8 = "1"

switch ($Target) {
  "help" {
    Write-Host "CloudGuard — available targets:"
    Write-Host "  dev         Start the full local stack"
    Write-Host "  down        Stop the stack (data preserved)"
    Write-Host "  clean       Stop the stack and DESTROY all data"
    Write-Host "  logs        Tail all logs"
    Write-Host "  shell       Shell into the api container"
    Write-Host "  migrate     Apply pending migrations"
    Write-Host "  migration   New migration:  .\make.ps1 migration 'add findings'"
    Write-Host "  lint        Lint python + typescript"
    Write-Host "  fmt         Auto-format everything"
    Write-Host "  typecheck   mypy --strict + tsc"
    Write-Host "  test        All backend tests"
    Write-Host "  test-unit   Fast tests only"
  }
  "dev"       { docker compose up --build }
  "down"      { docker compose down }
  "clean"     { docker compose down -v }
  "logs"      { docker compose logs -f }
  "shell"     { docker compose exec api /bin/bash }
  "migrate"   { docker compose exec api alembic upgrade head }
  "migration" { docker compose exec api alembic revision --autogenerate -m $args[0] }
  "downgrade" { docker compose exec api alembic downgrade -1 }
  "lint" {
    docker compose exec api ruff check .
    docker compose exec api black --check .
    Push-Location apps/web; npm run lint; Pop-Location
  }
  "fmt" {
    docker compose exec api ruff check --fix .
    docker compose exec api black .
    Push-Location apps/web; npm run format; Pop-Location
  }
  "typecheck" {
    docker compose exec api mypy packages/core apps/api
    Push-Location apps/web; npm run typecheck; Pop-Location
  }
  "test"      { docker compose exec api pytest -q }
  "test-unit" { docker compose exec api pytest -m "not integration" -q }
  "test-int"  { docker compose exec api pytest -m integration -q }
  default     { Write-Host "Unknown target '$Target'. Run: .\make.ps1 help" -ForegroundColor Red; exit 1 }
}
