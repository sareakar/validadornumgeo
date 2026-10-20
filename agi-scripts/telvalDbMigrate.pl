#!/usr/bin/perl
use strict;
use warnings;

# Agrega las columnas telval_provider/telval_provider_prefix a la tabla
# de trunks (id_proveedor por default) si todavia no existen. Idempotente:
# si ya estan, no hace nada y termina en 0. Pensado para correr una vez
# al integrar un cliente nuevo (ver docs/ONBOARDING_CLIENTE.md).
#
# NO asigna ningun provider_key -- eso requiere confirmar el formato
# real del trunk con llamadas de prueba (ver seccion 3.1 del onboarding),
# es una decision humana, no se puede automatizar a ciegas.
#
# Uso: perl telvalDbMigrate.pl [DB] [TABLA]
#   (default: asterisk / id_proveedor)

use lib("/var/www/pbx/Phps/Comunes");
use dataDB;
use DBI;

my $DB_NAME = $ARGV[0] || "asterisk";
my $TABLE   = $ARGV[1] || "id_proveedor";

my %config = dameConfig();

my $dbh = DBI->connect(
    "DBI:mysql:$DB_NAME:" . $config{MySQLHost} . ':' . $config{MySQLPort},
    $config{MySQLUser},
    $config{MySQLPass},
    { RaiseError => 1, PrintError => 0 }
) or die "ERROR: no se pudo conectar a MySQL ($DB_NAME\@$config{MySQLHost}): $DBI::errstr\n";

my $cols = $dbh->selectall_hashref("SHOW COLUMNS FROM $TABLE", "Field");

my $changed = 0;

unless (exists $cols->{telval_provider}) {
    $dbh->do("ALTER TABLE $TABLE ADD COLUMN telval_provider VARCHAR(40) NOT NULL DEFAULT ''");
    print "CHANGED: agregada columna telval_provider\n";
    $changed = 1;
}

unless (exists $cols->{telval_provider_prefix}) {
    $dbh->do("ALTER TABLE $TABLE ADD COLUMN telval_provider_prefix VARCHAR(20) NOT NULL DEFAULT ''");
    print "CHANGED: agregada columna telval_provider_prefix\n";
    $changed = 1;
}

$dbh->disconnect;

print $changed ? "OK: migracion aplicada\n" : "OK: ya estaba migrado, sin cambios\n";
exit 0;
