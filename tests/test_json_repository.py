import json
import threading

import pytest

from database.exceptions import StorageCorruptedError
from database.repositories.json_repository import JOURNAL_NAME, JsonRepository
from database import schema_def
from tests.repository_contract import RepositoryContract, product


class TestJsonRepositoryContract(RepositoryContract):
    @pytest.fixture
    def repo(self, tmp_path):
        return JsonRepository(tmp_path / "data")


def test_files_created_automatically(tmp_path):
    JsonRepository(tmp_path / "novo")
    for name in schema_def.FILE_NAMES.values():
        doc = json.loads((tmp_path / "novo" / name).read_text(encoding="utf-8"))
        assert doc["registros"] == [] and doc["proximo_id"] == 1


def test_persistence_after_restart(tmp_path):
    repo = JsonRepository(tmp_path)
    rec = repo.insert("produtos", product("PERS"))
    del repo
    reopened = JsonRepository(tmp_path)
    assert reopened.get("produtos", rec["id"])["codigo"] == "PERS"
    assert reopened.insert("produtos", product("NEXT"))["id"] == rec["id"] + 1


def test_empty_file_is_reinitialized(tmp_path):
    JsonRepository(tmp_path)
    (tmp_path / "clientes.json").write_text("", encoding="utf-8")
    repo = JsonRepository(tmp_path)
    assert repo.list("clientes") == []


def test_missing_file_recreated(tmp_path):
    repo = JsonRepository(tmp_path)
    (tmp_path / "produtos.json").unlink()
    assert repo.list("produtos") == []
    assert (tmp_path / "produtos.json").exists()


def test_corrupted_file_restored_from_backup(tmp_path):
    repo = JsonRepository(tmp_path)
    repo.insert("produtos", product("A"))
    repo.insert("produtos", product("B"))  # gera .bak contendo "A"
    (tmp_path / "produtos.json").write_text("{ corrompido", encoding="utf-8")
    fresh = JsonRepository(tmp_path)
    assert [p["codigo"] for p in fresh.list("produtos")] == ["A"]
    assert list(tmp_path.glob("produtos.json.corrompido-*"))


def test_corrupted_without_backup_raises(tmp_path):
    repo = JsonRepository(tmp_path)
    (tmp_path / "clientes.json").write_text("[not json", encoding="utf-8")
    with pytest.raises(StorageCorruptedError):
        repo.list("clientes")


def test_interrupted_commit_is_replayed(tmp_path):
    repo = JsonRepository(tmp_path)
    doc = {"tabela": "produtos", "versao": 1, "proximo_id": 8,
           "registros": [{**{k: None for k in schema_def.fields_of("produtos")}, **product("JRN"), "id": 7,
                          "custo_unitario": "2.5"}]}
    (tmp_path / JOURNAL_NAME).write_text(json.dumps({"completo": True, "arquivos": {"produtos": json.dumps(doc)}}))
    fresh = JsonRepository(tmp_path)
    assert fresh.get("produtos", 7)["codigo"] == "JRN"
    assert not (tmp_path / JOURNAL_NAME).exists()


def test_no_temp_files_left(tmp_path):
    repo = JsonRepository(tmp_path)
    repo.insert("produtos", product())
    assert not list(tmp_path.glob("*.tmp"))


def test_concurrent_inserts_keep_unique_ids(tmp_path):
    repo = JsonRepository(tmp_path)
    errors = []

    def worker(n):
        try:
            for i in range(10):
                repo.insert("clientes", {"nome": f"C{n}-{i}", "pais": "BR", "cidade": "SP"})
        except Exception as exc:  # pragma: no cover
            errors.append(exc)

    threads = [threading.Thread(target=worker, args=(n,)) for n in range(5)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert not errors
    rows = JsonRepository(tmp_path).list("clientes")
    assert len(rows) == 50 and len({r["id"] for r in rows}) == 50


def test_two_instances_share_lock(tmp_path):
    a, b = JsonRepository(tmp_path), JsonRepository(tmp_path)
    a.insert("produtos", product("A"))
    b.insert("produtos", product("B"))
    assert {p["codigo"] for p in a.list("produtos")} == {"A", "B"}
