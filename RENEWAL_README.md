# Building Law Checker — OpenCrab Core v2 Renewal

Original `app.py` and `building_law_checker.py` are deliberately preserved. The new entry point is `app_v2.py`.

## Run

```bash
pip install -r requirements.txt
streamlit run app_v2.py
```

## Architecture

- `building_law_checker.py`: legacy VWorld address/land-use query functions (reused)
- `law_core_v2.py`: **offline policy adapter** built from the saved OpenCrab Core v2 decision policy. Four priorities: REQUIRED / CONDITIONAL / LOW_PRIORITY / UNKNOWN. Outputs law → condition → design impact → action.
- `app_v2.py`: new UI, separates external data, topic routing, and *non-binding* arithmetic preview
- `tests/test_core_v2.py`: deterministic unit tests (no API key necessary)

## QA / Safety

```bash
python -m unittest discover -s tests -v
python -m py_compile app_v2.py law_core_v2.py
```

This release **does not** provide live OpenCrab API calls or authoritative legal determinations. The OpenCrab pack ID is a provenance reference, not an API credential.

### Known limitations

- Official law/ordinance amendments are NOT automatically synced.
- Land-use API failure is UNKNOWN, not "not applicable".
- Old road-slope and simplistic north-daylight calculations are intentionally not used.
- Parking rounding and use-specific area exceptions require legal source validation.
- FAR-counted area must be supplied correctly; total gross floor area may differ.
- No legal OK/NG; numbers are illustrative until sources, exceptions, and calculation rules are validated.
- Do not commit API keys or .env; rotate any previously exposed secrets.
