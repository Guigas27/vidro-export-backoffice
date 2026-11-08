"""Migra os dados do armazenamento JSON para o MySQL.

Uso (na pasta do projeto, com o .env apontando para o MySQL de destino):

    python -m tools.migrate_json_to_mysql --dry-run     # apenas valida
    python -m tools.migrate_json_to_mysql               # migra
    python -m tools.migrate_json_to_mysql --skip-existing

Garantias:
  * valida unicidade e chaves estrangeiras dos dados JSON antes de gravar;
  * preserva os IDs (os relacionamentos continuam válidos);
  * grava tudo em uma única transação MySQL (tudo ou nada);
  * por padrão, recusa migrar se o destino já tiver dados (evita duplicação);
    com --skip-existing, registros com o mesmo ID já presentes são comparados e ignorados.
"""
import argparse
import sys

from config import Config
from database import schema_def
from database.repositories.base_repository import normalize_text
from database.repositories.json_repository import JsonRepository
from database.repositories.mysql_repository import MySQLRepository


def validate(data):
    problems = []
    for table, rows in data.items():
        ids = set()
        for row in rows:
            if row["id"] in ids:
                problems.append(f"{table}: ID duplicado {row['id']}")
            ids.add(row["id"])
        for column in schema_def.TABLES[table]["unique"]:
            seen = {}
            for row in rows:
                value = row.get(column)
                if value is None:
                    continue
                key = normalize_text(value)
                if key in seen:
                    problems.append(f"{table}.{column}: valor duplicado '{value}' (IDs {seen[key]} e {row['id']})")
                seen[key] = row["id"]
    for (child, column), (parent, _rule) in schema_def.FOREIGN_KEYS.items():
        parent_ids = {r["id"] for r in data[parent]}
        for row in data[child]:
            if row.get(column) is not None and row[column] not in parent_ids:
                problems.append(f"{child}.{column}={row[column]} (ID {row['id']}) referencia registro inexistente em {parent}")
    return problems


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--json-dir", default=str(Config.JSON_DATA_DIR))
    parser.add_argument("--dry-run", action="store_true", help="Somente valida, não grava no MySQL.")
    parser.add_argument("--skip-existing", action="store_true", help="Ignora registros cujo ID já existe no destino.")
    args = parser.parse_args(argv)

    source = JsonRepository(args.json_dir)
    data = {t: source.list(t) for t in schema_def.TABLE_ORDER}
    print("Registros no JSON: " + ", ".join(f"{t}={len(r)}" for t, r in data.items()))

    problems = validate(data)
    if problems:
        print("\nProblemas de integridade encontrados — corrija antes de migrar:")
        for p in problems:
            print("  - " + p)
        return 2
    print("Validação de integridade: OK")
    if args.dry_run:
        return 0

    target = MySQLRepository(Config.DB_HOST, Config.DB_PORT, Config.DB_USER, Config.DB_PASSWORD, Config.DB_NAME)
    inserted = skipped = 0
    with target.transaction():
        if not args.skip_existing:
            busy = [t for t in schema_def.TABLE_ORDER if t != "configuracoes" and target.count(t) > 0]
            if busy:
                print(f"\nO banco de destino já possui dados em: {', '.join(busy)}.")
                print("Use --skip-existing para mesclar, ou migre para um banco vazio.")
                return 3
        for table in schema_def.TABLE_ORDER:
            for row in data[table]:
                if table == "configuracoes":
                    existing = target.find_one("configuracoes", chave=row["chave"])
                    if existing:
                        target.update("configuracoes", existing["id"], {"valor": row["valor"]})
                        skipped += 1
                        continue
                existing = target.get(table, row["id"])
                if existing is not None:
                    skipped += 1
                    continue
                target.insert(table, row)
                inserted += 1
    print(f"\nMigração concluída: {inserted} inserido(s), {skipped} já existente(s)/atualizado(s).")
    for table in schema_def.TABLE_ORDER:
        print(f"  {table}: JSON={len(data[table])}  MySQL={target.count(table)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
