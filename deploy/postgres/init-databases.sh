#!/bin/bash
# По базе и пользователю на каждый сервис. Физически один инстанс, но семь
# изолированных баз: в чужие данные сервис не попадёт даже случайно.
set -euo pipefail

create_user() {
  local user="$1" pass="$2"
  psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname postgres <<-SQL
	DO \$\$
	BEGIN
	  IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = '${user}') THEN
	    CREATE USER ${user} WITH PASSWORD '${pass}';
	  END IF;
	END
	\$\$;
	SQL
}

create_db() {
  local name="$1" user="$2" pass="$3"
  create_user "$user" "$pass"
  psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname postgres <<-SQL
	CREATE DATABASE ${name} OWNER ${user};
	REVOKE ALL ON DATABASE ${name} FROM PUBLIC;
	GRANT ALL PRIVILEGES ON DATABASE ${name} TO ${user};
	SQL
  psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "${name}" \
    -c "CREATE EXTENSION IF NOT EXISTS btree_gist" >/dev/null
  echo "  ✓ ${name} (владелец ${user})"
}

echo "Создание баз данных сервисов:"
create_db core_db      core_user      core_pass
create_db client_db    client_user    client_pass
create_db booking_db   booking_user   booking_pass
create_db catalog_db   catalog_user   catalog_pass
create_db inventory_db inventory_user inventory_pass
create_db billing_db   billing_user   billing_pass
create_db analytics_db analytics_user analytics_pass
create_db keycloak     keycloak_user  keycloak_pass
create_db core_db_test    core_user      core_pass
create_db catalog_db_test catalog_user   catalog_pass
create_db client_db_test  client_user    client_pass
create_db billing_db_test billing_user   billing_pass
create_db analytics_db_test analytics_user analytics_pass
create_db booking_db_test booking_user   booking_pass
create_db inventory_db_test inventory_user inventory_pass
echo "Готово."
