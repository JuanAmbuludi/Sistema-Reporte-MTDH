"""Revision dates follow source values, not process clocks or unrelated sections."""
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import subprocess

import pandas as pd

from src.revisions import Source, build, content_hash, first_revision, fingerprints


def test_row_order_compression_and_file_dates_do_not_change_content(tmp_path):
    path = tmp_path / "records.parquet"
    source = Source("records.parquet")
    rows = pd.DataFrame({"value": [3, 2, 3], "name": ["A", "B", "A"]})
    rows.to_parquet(path, compression="snappy", index=False)
    before = content_hash(path.read_bytes(), source)
    rows.iloc[::-1][["name", "value"]].to_parquet(path, compression="gzip", index=False)
    os.utime(path, (1, 1))
    assert content_hash(path.read_bytes(), source) == before
    rows.drop_duplicates().to_parquet(path, index=False)
    assert content_hash(path.read_bytes(), source) != before


def test_only_the_changed_section_advances_and_query_metadata_is_ignored(tmp_path):
    table = tmp_path / "shared.parquet"
    rows = pd.DataFrame({"seccion": ["bonos", "servicios"], "personas": [10, 20]})
    rows.to_parquet(table, index=False)
    specs = {"transferencias": [Source("shared.parquet", "seccion", ("bonos",))],
             "servicios": [Source("shared.parquet", "seccion", ("servicios",))]}
    initial = build(tmp_path, sources=specs, now="2026-10-01T00:00:00+00:00")
    for item in initial["areas"].values():
        item["actualizado_utc"] = "2026-10-01T00:00:00+00:00"
    assert build(tmp_path, sources=specs, previous=initial, now="2026-10-20T00:00:00+00:00") == initial
    rows.loc[0, "personas"] = 11
    rows.to_parquet(table, index=False)
    changed = build(tmp_path, sources=specs, previous=initial, now="2026-10-20T00:00:00+00:00")
    assert changed["areas"]["servicios"] == initial["areas"]["servicios"]
    assert changed["areas"]["transferencias"]["actualizado_utc"] == "2026-10-20T00:00:00+00:00"
    assert build(tmp_path, sources=specs, previous=changed, now="2026-10-30T00:00:00+00:00") == changed
    table.unlink()
    deleted = build(tmp_path, sources=specs, previous=changed, now="2026-10-30T00:00:00+00:00")
    assert deleted["areas"]["servicios"]["actualizado_utc"] == "2026-10-30T00:00:00+00:00"


def test_json_processing_dates_are_not_source_cuts():
    source = Source("source.json")
    source_data = {"generado_utc": "2026-10-01", "fecha_corte": "2026-09-30", "registros": [{"n": 7}]}
    before = content_hash(json.dumps(source_data).encode(), source)
    source_data["generado_utc"] = "2026-10-30"
    assert content_hash(json.dumps(source_data, indent=3).encode(), source) == before
    source_data["fecha_corte"] = "2026-10-30"
    assert content_hash(json.dumps(source_data).encode(), source) != before


def test_bootstrap_uses_last_content_changing_commit_not_reformat_date(tmp_path):
    def git(*args, env=None):
        return subprocess.run(["git", *args], cwd=tmp_path, check=True, capture_output=True, env=env)
    git("init")
    git("config", "user.name", "test")
    git("config", "user.email", "test@example.test")
    path = tmp_path / "source.json"
    source = Source("source.json")
    for n, date in [(5, "2026-10-01T10:00:00+00:00"), (6, "2026-10-03T10:00:00+00:00"),
                    (6, "2026-10-10T10:00:00+00:00")]:
        path.write_text(json.dumps({"n": n, "generado_utc": date}, indent=2))
        git("add", ".")
        env = {**os.environ, "GIT_AUTHOR_DATE": date, "GIT_COMMITTER_DATE": date}
        git("commit", "-m", date, env=env)
    actual, origin = first_revision(tmp_path, [source], fingerprints(tmp_path, [source]), "2026-10-30T00:00:00+00:00")
    assert actual == "2026-10-03T10:00:00+00:00"
    assert len(origin) == 40


def test_unknown_history_does_not_invent_update_date(tmp_path):
    (tmp_path / "source.json").write_text('{"n":5}')
    initial = build(tmp_path, sources={"one": [Source("source.json")]})
    assert initial["areas"]["one"]["actualizado_utc"] is None
