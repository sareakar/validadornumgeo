#!/usr/bin/perl
use strict;
use warnings;

# Sincroniza telval_provider/telval_provider_prefix de la tabla MySQL
# del cliente (id_proveedor o equivalente) hacia AstDB, para que el
# dialplan lea ${DB(SIP/<trunk>/telvalProvider)} directo en vez de
# llamar a telvalTrunkProvider.agi (que abre una conexion MySQL nueva
# POR LLAMADA -- medido ~20ms, notorio en discadores de alto volumen).
# Ver docs/PRUEBA_AGI_LXC1324.md y la tarea de Jira "Reemplazar el
# lookup MySQL por-llamada... por sync cron + AstDB".
#
# Pensado para correr por cron cada 1-2 min, como root (necesita acceso
# al socket de Asterisk para `asterisk -rx`). Idempotente: en cada
# corrida relee TODA la tabla y resincroniza altas y bajas -- no
# necesita recordar el estado anterior.
#
# Ventana de staleness: hasta el intervalo del cron entre un cambio en
# MySQL y que se refleje en AstDB. Aceptable porque el mapeo
# trunk->provider_key cambia rarisima vez.
#
# Ajustar DB_NAME/TABLE si el esquema del cliente usa otro nombre (ver
# el README de client_configs/<cliente>/ para lo que se encontro ahi).

use lib("/var/www/pbx/Phps/Comunes");
use dataDB;
use DBI;

my $DB_NAME = "asterisk";
my $TABLE   = "id_proveedor";
my $ASTERISK_BIN = "/usr/sbin/asterisk";
my $LOG = "/var/log/telval-trunk-sync.log";

sub log_msg {
    my ($msg) = @_;
    open(my $fh, '>>', $LOG) or return;
    my @t = localtime;
    printf $fh "%04d-%02d-%02d %02d:%02d:%02d %s\n",
        $t[5]+1900, $t[4]+1, $t[3], $t[2], $t[1], $t[0], $msg;
    close $fh;
}

sub ast_cli {
    my ($cmd) = @_;
    system($ASTERISK_BIN, '-rx', $cmd);
}

my %config = dameConfig();

my $dbh = DBI->connect(
    "DBI:mysql:$DB_NAME:" . $config{MySQLHost} . ':' . $config{MySQLPort},
    $config{MySQLUser},
    $config{MySQLPass},
    { RaiseError => 0, PrintError => 0 }
);

unless ($dbh) {
    log_msg("ERROR: no se pudo conectar a MySQL ($DB_NAME\@$config{MySQLHost})");
    exit 1;
}

my $sth = $dbh->prepare("SELECT name, telval_provider, telval_provider_prefix FROM $TABLE");
unless ($sth->execute) {
    log_msg("ERROR: query fallo en $TABLE");
    $dbh->disconnect;
    exit 1;
}

my $synced = 0;
while (my ($name, $provider, $prefix) = $sth->fetchrow_array) {
    $name     //= "";
    $provider //= "";
    $prefix   //= "";
    next if $name eq "";

    # Nombres/valores vienen de una tabla interna del panel, no de
    # input de usuario final -- igual se valida que sean "razonables"
    # antes de pasarlos a una CLI externa.
    next unless $name     =~ /^[A-Za-z0-9_.-]+$/;
    next unless $provider =~ /^[A-Za-z0-9_.-]*$/;
    next unless $prefix   =~ /^[A-Za-z0-9_.-]*$/;

    if ($provider ne "") {
        ast_cli("database put SIP/$name telvalProvider $provider");
    } else {
        ast_cli("database del SIP/$name telvalProvider");
    }

    if ($prefix ne "") {
        ast_cli("database put SIP/$name telvalProviderPrefix $prefix");
    } else {
        ast_cli("database del SIP/$name telvalProviderPrefix");
    }

    $synced++;
}

$sth->finish;
$dbh->disconnect;

log_msg("OK: $synced trunk(s) sincronizados");
