# FC100E-2S-1.5G con Raspberry PLC 19R por RS-485

Este documento corresponde al **FC100E**, que tiene comunicación en las borneras
`A+` y `B-`. No corresponde al FC100 antiguo del manual V2.00 con conector RJ-11.

## Conexión física

Desenergice el PLC y el variador antes de cablear:

| PLC 19R, RS-485 1 | FC100E |
|---|---|
| `A1+` | `A+` |
| `B1-` | `B-` |

No hace falta conectar GND entre ambos equipos para esta interfaz de dos hilos. Use par
trenzado apantallado, con la pantalla a tierra en un solo extremo, y manténgalo separado
de los cables de red y motor. Para un único equipo y cable corto pruebe primero sin
terminación; en una línea larga coloque 120 ohm entre `A+` y `B-` en ambos extremos.

## Parámetros del FC100E

Con el motor detenido configure:

- `P0-02 = 2`: órdenes de marcha por comunicación.
- `P0-03 = 9`: frecuencia principal por comunicación.
- `PD-00 = 5`: 9600 bit/s.
- `PD-01 = 3`: 8 bits, sin paridad, 1 parada (8N1).
- `PD-02 = 1`: dirección Modbus 1.
- `PD-05 = 1`: protocolo Modbus estándar.
- Para las primeras pruebas deje `PD-04 = 0.0 s` (timeout deshabilitado).

Para verificar solamente el enlace puede configurar primero el grupo `PD` y dejar
`P0-02` en panel, de manera que una prueba de lectura no habilite el arranque.

## Primera prueba

La primera interfaz RS-485 del PLC 19R V6 normalmente es `/dev/ttySC2`:

```bash
sudo apt install python3-serial
python3 controlar_fc100.py leer 0x1001
python3 controlar_fc100.py estado
```

Después de confirmar la comunicación y configurar `P0-02=2`, `P0-03=9`:

```bash
python3 controlar_fc100.py frecuencia 5
python3 controlar_fc100.py directa
python3 controlar_fc100.py estado
python3 controlar_fc100.py parar
```

La opción `--maxima` debe coincidir con `P0-10`. Por ejemplo, si `P0-10=60 Hz`:

```bash
python3 controlar_fc100.py frecuencia 30 --maxima 60
```

Para probar el segundo RS-485 use `--puerto /dev/ttySC3`. Las opciones generales se
escriben antes de la acción.

## Seguridad

La parada de emergencia debe ser física y cableada; no debe depender de Python, Modbus
ni de la Raspberry Pi. Pruebe inicialmente con el motor desacoplado de la carga y no
conecte jamás `A+`/`B-` a los bornes de potencia.
