#!/usr/bin/perl
use strict;
use warnings;

# Inserta el bloque de validacion de telval (modo AstDB, sin AGI de
# lookup por-llamada) justo antes de CADA Dial() real en macros.conf.
# Pensado para un AsterVoIP recien instalado ("limpio"): asume que la
# linea de Dial() todavia no fue customizada por nadie, y que aparece
# EXACTAMENTE 2 veces en el archivo (macro-dialout y
# macro-dialout-discadores) -- confirmado identico en los 3 clientes
# reales integrados hasta ahora (Resermap, Dyktel, Medimas), a pesar de
# que cada uno tenia contexto DISTINTO alrededor.
#
# Idempotente: si el marcador ya esta presente en el archivo, no hace
# nada (seguro de correr de nuevo). Si la linea ancla no aparece
# EXACTAMENTE 2 veces (y el marcador no esta), ABORTA sin tocar nada --
# un AsterVoIP ya customizado necesita el flujo manual de siempre
# (ver docs/PRUEBA_AGI_LXC1324.md, bitacora de cada cliente real), no
# este script.
#
# Uso: perl telvalDialplanInstall.pl /etc/asterisk/partesextensions/macros.conf

my $file = $ARGV[0] or die "Uso: $0 <path a macros.conf>\n";

my $marker = "; TELVAL INTEGRATION (ver docs/ONBOARDING_CLIENTE.md) -- no editar a mano, usar telvalDialplanInstall.pl";

my $anchor = <<'ANCHOR';
same => n,Dial(${Trunk}/${Prefix}${Numero},${Tods},${Ods}M(${macroCRM}))
ANCHOR

my $block = <<"BLOCK";
$marker
same => n,Set(TelvalProvider=\${DB(\${Trunk}/telvalProvider)})
same => n,Set(TelvalProviderPrefix=\${DB(\${Trunk}/telvalProviderPrefix)})
same => n,GotoIf(\$["\${TelvalProvider}" = ""]?telval_skip)
same => n,GotoIf(\$["\${TelvalProviderPrefix}" != ""]?telval_wholesale)
same => n,AGI(agi://telval.centraltelefonica.com.ar:4573/validate,\${Prefix}\${Numero},11,\${TelvalProvider})
same => n,GotoIf(\$["\${TELVAL_DIAL}" = ""]?telval_skip)
same => n,Set(Prefix=)
same => n,Set(Numero=\${TELVAL_DIAL})
same => n,Goto(telval_skip)
same => n(telval_wholesale),AGI(agi://telval.centraltelefonica.com.ar:4573/validate,\${Numero},11,\${TelvalProvider},\${TelvalProviderPrefix})
same => n,GotoIf(\$["\${TELVAL_DIAL}" = ""]?telval_skip)
same => n,Set(Numero=\${TELVAL_DIAL})
same => n(telval_skip),Dial(\${Trunk}/\${Prefix}\${Numero},\${Tods},\${Ods}M(\${macroCRM}))
BLOCK

open(my $fh, '<', $file) or die "No se pudo leer $file: $!\n";
local $/;
my $content = <$fh>;
close $fh;

if (index($content, $marker) != -1) {
    print "OK: ya aplicado (marcador presente), sin cambios\n";
    exit 0;
}

my $count = () = $content =~ /\Q$anchor\E/g;
if ($count != 2) {
    die "ABORTADO: la linea de Dial() aparece $count veces (se esperaban exactamente 2 -- macro-dialout y macro-dialout-discadores). Este AsterVoIP no parece estar \"limpio\"; usar el flujo manual (backup + diff + aprobacion) en vez de este script.\n";
}

my $backup = "$file.bak_telval_" . time();
open(my $bfh, '>', $backup) or die "No se pudo hacer backup de $file: $!\n";
print $bfh $content;
close $bfh;

$content =~ s/\Q$anchor\E/$block/g;

open(my $out, '>', $file) or die "No se pudo escribir $file: $!\n";
print $out $content;
close $out;

print "OK: bloque de telval insertado en 2 lugares (macro-dialout y macro-dialout-discadores)\n";
