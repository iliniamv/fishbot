Param()

Write-Host "Running smoke test: import main"
try {
  python - <<'PY'
import importlib
try:
    import main  # simple import smoke
    print("OK: imported main")
except Exception as e:
    print("FAIL: exception importing main:", e)
    raise
PY
} catch {
  Write-Error "Smoke test failed."
  exit 1
}
